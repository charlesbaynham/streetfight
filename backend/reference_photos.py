"""The kit check at the door: a photo of a player, through the shot pipeline.

The admin photographs each player as they arrive and the picture goes through
**exactly** what a real shot goes through -- the same prompt, the same
screening/zoom exchange, the same aim marker (see
:func:`backend.ai_shot_review._review_image_data`, which this module calls
rather than reimplementing). Only the sink is different: the result is stored
against the ``User``, never as a ``Shot``, so it costs no ammo, moves no hit
points, writes no ticker entry and never appears in the admin queue.

What the review alone cannot say is whether the outfit decodes to *this*
player, so a second, purely deterministic step follows it: the reading is
scored against everyone in the game who has picked an outfit
(:func:`backend.shot_identification.rank_reference_candidates`) and the ranking
is folded into the stored payload as an ``identification`` section. That is the
answer the person at the door actually needs -- recognised as themselves, or
recognised as somebody else and fixable while there is still time.

The same two constraints as :mod:`backend.ai_shot_review` shape it: never hold
a database session across an ``await``, and never let a failure escape -- a
review that falls over is recorded as an ``error`` state and nothing else.
"""

import asyncio
import logging
from typing import Optional
from uuid import UUID

from . import ai_shot_review
from .asyncio_triggers import trigger_update_event
from .model import AI_REVIEW_STATE_DONE
from .model import AI_REVIEW_STATE_ERROR
from .model import AI_REVIEW_STATE_PENDING
from .shot_identification import rank_reference_candidates
from .vision_client import get_vision_client

logger = logging.getLogger(__name__)

STATE_PENDING = AI_REVIEW_STATE_PENDING
STATE_DONE = AI_REVIEW_STATE_DONE
STATE_ERROR = AI_REVIEW_STATE_ERROR

# asyncio only holds a weak reference to a running task, so keep our own or a
# review can be collected mid-flight.
_tasks = set()


def enqueue_review(user_id: UUID, client=None) -> Optional[asyncio.Task]:
    """Schedule a review of one player's reference photo.

    Returns None if the feature is not set up. Safe to call from a request
    handler: the admin at the door gets their confirmation back immediately and
    the verdict arrives over SSE.
    """
    client = client or get_vision_client()
    if client is None:
        logger.info(
            "Not reviewing the reference photo of user %s: no vision client "
            "configured (set OPENROUTER_API_KEY)",
            user_id,
        )
        return None

    try:
        task = asyncio.create_task(review_reference_photo(user_id, client))
    except RuntimeError:
        # No running loop -- e.g. a synchronous test harness. Nothing to review.
        logger.warning(
            "Not reviewing the reference photo of user %s: no running event loop",
            user_id,
        )
        return None

    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def _identification(user_id: UUID, review: dict) -> Optional[dict]:
    """Who this reading looks like, against everyone who has picked an outfit.

    ``None`` when there is nothing to rank against: the photographed player is
    in no game, or nobody in it has an identity slot yet. ``matches_expected``
    is ``None`` rather than ``False`` when the photographed player has no slot
    of their own -- the question is unanswerable, not answered no.
    """
    from .admin_interface import AdminInterface

    user = AdminInterface().get_user_model(user_id)
    if user.game_id is None:
        return None

    users = AdminInterface().get_users_for_game(user.game_id)
    ranked = rank_reference_candidates(users, review)
    if ranked is None:
        return None

    names = {u.id: u.name for u in users}
    return {
        "ranked": [
            {
                "user_id": str(candidate_id),
                "name": names.get(candidate_id),
                "probability": probability,
            }
            for candidate_id, probability in ranked.ranked
        ],
        "expected_user_id": str(user_id),
        "matches_expected": (
            None if user.identity_slot is None else ranked.best == user.id
        ),
        "confident": ranked.confident,
        "ambiguous": ranked.ambiguous,
        "inconsistent": ranked.inconsistent,
    }


async def review_reference_photo(user_id: UUID, client=None) -> None:
    """Review one player's reference photo and store the result. Never raises."""
    from .admin_interface import AdminInterface

    client = client or get_vision_client()
    if client is None:
        return

    try:
        AdminInterface().store_reference_review(user_id, STATE_PENDING)
        image_base64 = AdminInterface().get_reference_photo(user_id)
    except Exception:
        logger.exception("Could not load the reference photo of user %s", user_id)
        return

    state = STATE_DONE
    payload = None
    try:
        if not image_base64:
            raise ValueError("No reference photo stored for this player")
        async with ai_shot_review._get_semaphore():
            result = await ai_shot_review._review_image_data(image_base64, client)
        payload = result.to_dict()
        # Inside the guarded flow on purpose: a scoring bug is an errored kit
        # check, not an unhandled exception on the event loop.
        payload["identification"] = _identification(user_id, payload)
        logger.info(
            "Reference photo of user %s reviewed: %s", user_id, result.outcome_reason
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("Review of the reference photo of user %s failed", user_id)
        state = STATE_ERROR
        payload = str(e) or e.__class__.__name__

    try:
        game_id = AdminInterface().store_reference_review(user_id, state, payload)
    except Exception:
        logger.exception(
            "Could not store the review of the reference photo of user %s", user_id
        )
        return

    trigger_update_event("user", user_id)
    if game_id is not None:
        trigger_update_event("shots", game_id)
