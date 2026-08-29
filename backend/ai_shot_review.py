"""Running shot photos past a vision model, off the request path.

There is no task queue in this app, so the work happens as asyncio tasks on the
event loop. Two constraints shape the design:

* **Never hold a database session across an ``await``.** ``@db_scoped`` keeps
  its session on the interface instance, and an OpenRouter call takes seconds.
  So a review is: a short synchronous read, the network call with no session
  open, then a short synchronous write.
* **Never let a review affect the shot.** A failure is recorded as an ``error``
  state and nothing else. The queue must work exactly as it did before when the
  API key is missing or the model is down.
"""

import asyncio
import logging
import os
from typing import Optional
from uuid import UUID

from . import shot_auto_actions
from . import shot_vision
from .asyncio_triggers import trigger_update_event
from .image_processing import draw_aim_marker
from .image_processing import prepare_for_vision
from .image_processing import zoom_image
from .model import AI_REVIEW_STATE_DONE
from .model import AI_REVIEW_STATE_ERROR
from .model import AI_REVIEW_STATE_PENDING
from .vision_client import get_vision_client

logger = logging.getLogger(__name__)

STATE_PENDING = AI_REVIEW_STATE_PENDING
STATE_DONE = AI_REVIEW_STATE_DONE
STATE_ERROR = AI_REVIEW_STATE_ERROR

DEFAULT_CONCURRENCY = 2

# A vision call that errors or answers off-schema is usually having a bad
# moment rather than being stuck: the admin's own fix is to press "re-run
# review", so spend those attempts here first. Both failures arrive as an
# exception out of the pipeline, so one loop covers them.
REVIEW_ATTEMPTS = 3

# asyncio only holds a weak reference to a running task, so keep our own or a
# review can be collected mid-flight.
_tasks = set()
_semaphore: Optional[asyncio.Semaphore] = None


def _concurrency() -> int:
    raw = os.getenv("AI_SHOT_REVIEW_CONCURRENCY")
    if not raw:
        return DEFAULT_CONCURRENCY
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning(
            "Ignoring unparseable AI_SHOT_REVIEW_CONCURRENCY=%r; using %s",
            raw,
            DEFAULT_CONCURRENCY,
        )
        return DEFAULT_CONCURRENCY


def _get_semaphore() -> asyncio.Semaphore:
    """Bound the number of concurrent calls.

    Switching the toggle on with forty shots in the queue must not fire forty
    parallel requests at the API.
    """
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_concurrency())
    return _semaphore


def enqueue_review(shot_id: UUID, client=None) -> Optional[asyncio.Task]:
    """Schedule a review of one shot. Returns None if the feature is not set up.

    Safe to call from a request handler: it returns as soon as the task is
    created, so the player who fired the shot is not kept waiting.
    """
    client = client or get_vision_client()
    if client is None:
        logger.info(
            "Not reviewing shot %s: no vision client configured "
            "(set OPENROUTER_API_KEY)",
            shot_id,
        )
        return None

    try:
        task = asyncio.create_task(review_shot(shot_id, client))
    except RuntimeError:
        # No running loop -- e.g. a synchronous test harness. Nothing to review.
        logger.warning("Not reviewing shot %s: no running event loop", shot_id)
        return None

    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def enqueue_reviews(shot_ids, client=None) -> int:
    """Schedule reviews for a batch (the backlog). Returns how many started."""
    client = client or get_vision_client()
    if client is None:
        return 0
    return sum(1 for shot_id in shot_ids if enqueue_review(shot_id, client))


async def _review_image_data(
    image_base64: str,
    client,
    prompt: Optional[str] = None,
    zoom_mode: str = shot_vision.ZOOM_SCREENED,
    schema: Optional[dict] = None,
    tolerate_unparsed: bool = False,
) -> "shot_vision.ShotVisionResult":
    """One shot photo through the vision pipeline: marker, resize, review.

    The aim marker tells the model where the shot landed; the resize keeps the
    image bill sane. The zoom is cut from the *original*, not from the prepared
    image -- the resize has already discarded the camera resolution that makes
    a distant target readable, which is the only reason to zoom at all. It is
    spent only when the model's screening answer says the person fills less
    than half of the screen; ``zoom_mode`` (see ``shot_vision.ZOOM_*``) picks
    another shape of exchange for replay comparisons.
    """
    prepared = prepare_for_vision(draw_aim_marker(image_base64))

    def zoom_provider(level):
        # Each level compounds the factor against the original, so the second
        # zoom is ZOOM_FACTOR**2 into the camera's full resolution.
        return zoom_image(image_base64, factor=shot_vision.ZOOM_FACTOR**level)

    return await shot_vision.review_image(
        client,
        prepared,
        zoom_provider=zoom_provider,
        prompt=prompt,
        zoom_mode=zoom_mode,
        schema=schema,
        tolerate_unparsed=tolerate_unparsed,
    )


async def replay_shot_review(
    shot_id: UUID,
    client,
    prompt: Optional[str] = None,
    zoom_mode: str = shot_vision.ZOOM_SCREENED,
    schema: Optional[dict] = None,
) -> dict:
    """Review one shot on demand -- with a contract of its own if given -- and
    hand the reading straight back.

    ``prompt``, ``zoom_mode`` and ``schema`` are the three halves of what the
    workbench can vary: the wording, the shape of the exchange, and the shape
    of the reply. All three have to travel together, since a prompt asking a
    new question while the pipeline still asks for the old schema and sends the
    old follow-up turns is a prompt that has been overruled.

    Unlike :func:`review_shot` this stores nothing, fires no update events and
    runs no auto-actions: it is the admin replay workbench's scratch pad, not
    part of the game. The reply carries the full turn-by-turn transcript
    (``include_transcript=True``) so the workbench can show exactly what was
    sent and said back -- a live review's stored payload leaves it out -- and a
    reply that is not a standard reading comes back raw rather than as an
    error.
    """
    from .admin_interface import AdminInterface

    image_base64 = AdminInterface().get_shot_model(shot_id).image_base64
    async with _get_semaphore():
        result = await _review_image_data(
            image_base64,
            client,
            prompt=prompt,
            zoom_mode=zoom_mode,
            schema=schema,
            tolerate_unparsed=True,
        )
    return result.to_dict(include_transcript=True)


async def _review_with_retries(
    image_base64: str, client
) -> "shot_vision.ShotVisionResult":
    """:func:`_review_image_data` again on a transient failure, up to
    :data:`REVIEW_ATTEMPTS` times; the last failure is raised as its own.

    The semaphore is taken per attempt rather than around the loop, so a retry
    queues behind other shots instead of holding a slot open across all three.
    """
    for attempt in range(1, REVIEW_ATTEMPTS + 1):
        try:
            async with _get_semaphore():
                return await _review_image_data(image_base64, client)
        except asyncio.CancelledError:
            raise
        except Exception:
            if attempt == REVIEW_ATTEMPTS:
                raise
            logger.warning(
                "Vision attempt %s of %s failed; retrying",
                attempt,
                REVIEW_ATTEMPTS,
                exc_info=True,
            )


async def review_shot(shot_id: UUID, client=None) -> None:
    """Review one shot and store the result. Never raises."""
    from .admin_interface import AdminInterface

    client = client or get_vision_client()
    if client is None:
        return

    try:
        AdminInterface().store_shot_ai_review(shot_id, STATE_PENDING)
        image_base64 = AdminInterface().get_shot_model(shot_id).image_base64
    except Exception:
        logger.exception("Could not load shot %s for review", shot_id)
        return

    state = STATE_DONE
    payload = None
    try:
        result = await _review_with_retries(image_base64, client)
        payload = result.to_dict()
        logger.info(
            "Shot %s reviewed: %s (%s)", shot_id, result.outcome, result.outcome_reason
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("Review of shot %s failed", shot_id)
        state = STATE_ERROR
        payload = str(e) or e.__class__.__name__

    try:
        game_id, shooter_id = AdminInterface().store_shot_ai_review(
            shot_id, state, payload
        )
        # The shooter's shot history shows the AI's provisional verdict, so
        # nudge them as well as the admin queue
        trigger_update_event("user", shooter_id)
        trigger_update_event("shots", game_id)
    except Exception:
        logger.exception("Could not store the review of shot %s", shot_id)
        return

    # A completed review may have made the queue head resolvable. Guarded so
    # this function keeps its "never raises" contract.
    try:
        shot_auto_actions.process_queue_head(game_id)
    except Exception:
        logger.exception("Auto-action drain after reviewing shot %s failed", shot_id)
