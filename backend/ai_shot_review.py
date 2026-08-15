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

from . import shot_vision
from .asyncio_triggers import trigger_update_event
from .image_processing import draw_aim_marker
from .image_processing import prepare_for_vision
from .vision_client import get_vision_client

logger = logging.getLogger(__name__)

STATE_PENDING = "pending"
STATE_DONE = "done"
STATE_ERROR = "error"

DEFAULT_CONCURRENCY = 2

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
        async with _get_semaphore():
            # The aim marker tells the model where the shot landed; the resize
            # keeps the image bill sane.
            prepared = prepare_for_vision(draw_aim_marker(image_base64))
            result = await shot_vision.review_image(client, prepared)
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
        game_id = AdminInterface().store_shot_ai_review(shot_id, state, payload)
        trigger_update_event("shots", game_id)
    except Exception:
        logger.exception("Could not store the review of shot %s", shot_id)
