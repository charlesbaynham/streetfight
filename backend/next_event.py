"""The one thing the game says is coming next, and the clock that fires it.

A game carries at most one cue at a time: ``Game.next_event_kind`` /
``next_event_at`` / ``next_event_note``, set by an admin and cleared when the
cue fires or is cancelled. This module holds the vocabulary those columns are
written in, kept out of ``model.py`` so that nothing which only reads a cue has
to import the ORM, and the in-process timer that fires them.

The kinds are the two things that can be counted down to on the night:

``circle``
    The next circle becomes the exclusion circle when the clock runs out
    (:meth:`AdminInterface.promote_next_circle`), so everyone outside it has
    until then to get in.

``drop``
    A courier sets off with a crate when the clock runs out (M3.3), and the
    note is what is in it.

The strings are what reaches the players' phones on ``UserModel``, so they are
part of the wire format: a phone with an older bundle open will show a cue it
does not recognise as nothing at all rather than as a wrong one.

The timer is deliberately not durable. What *is* durable is ``next_event_at``
in the database, and :func:`sweep` rebuilds the timers from it at startup - so
a deploy in the middle of a countdown costs the players nothing, and a cue
whose moment passed while the process was down fires as soon as it is back.
That is the whole reason the deadline is a column rather than an asyncio
handle.
"""

import asyncio
import enum
import logging
import time
from typing import Dict
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class NextEventKind(str, enum.Enum):
    """What a cue is counting down to. A ``str`` enum so that FastAPI
    validates the admin's input against it while the column, the SSE payload
    and the frontend all still see a plain string."""

    CIRCLE = "circle"
    DROP = "drop"


KIND_CIRCLE = NextEventKind.CIRCLE.value
KIND_DROP = NextEventKind.DROP.value

EVENT_KINDS = (KIND_CIRCLE, KIND_DROP)

# A fired cue and the deadline the task was armed for are compared with this
# much slack: the float makes a round trip through the database, and nothing
# here cares about a tenth of a second.
DEADLINE_EPSILON_S = 0.5

# One pending task per game, so arming a second cue for the same game cancels
# the first rather than leaving two clocks racing. asyncio only holds a weak
# reference to a running task, so this dict is also what keeps them alive -
# the same trap asyncio_triggers._scheduled_tasks exists for.
_pending: Dict[UUID, asyncio.Task] = {}


def arm(game_id: UUID, at: float) -> Optional[asyncio.Task]:
    """Fire ``game_id``'s cue when the clock reaches ``at`` (epoch seconds).

    Replaces any timer already pending for that game. Returns None when there
    is no running event loop to schedule on - a synchronous test harness, or a
    CLI - which leaves the deadline in the database for :func:`sweep` to pick
    up rather than failing the write that set it.
    """
    disarm(game_id)

    delay = max(0.0, at - time.time())
    try:
        task = asyncio.create_task(_wait_then_fire(game_id, at, delay))
    except RuntimeError:
        logger.warning(
            "Not arming the cue for game %s: no running event loop", game_id
        )
        return None

    _pending[game_id] = task
    task.add_done_callback(lambda finished: _forget(game_id, finished))
    logger.info("Armed game %s's cue for %.1fs from now", game_id, delay)
    return task


def disarm(game_id: UUID) -> None:
    """Cancel the pending timer for a game, if there is one."""
    task = _pending.pop(game_id, None)
    if task is not None and not task.done():
        logger.info("Disarming game %s's cue", game_id)
        task.cancel()


def _forget(game_id: UUID, finished: asyncio.Task) -> None:
    # Only drop the entry if it is still *this* task: a re-arm during the
    # sleep has already replaced it, and its cancellation must not take the
    # new timer's place in the registry with it.
    if _pending.get(game_id) is finished:
        del _pending[game_id]


async def _wait_then_fire(game_id: UUID, at: float, delay: float) -> None:
    await asyncio.sleep(delay)
    fire(game_id, expected_at=at)


def fire(game_id: UUID, expected_at: Optional[float] = None) -> None:
    """Act on a game's cue, now its moment has come.

    ``expected_at`` is the deadline the caller believes it is firing: the
    interface checks it against what is actually in the database and does
    nothing if they disagree, so a timer that was overtaken by a re-cue (or by
    an admin cancelling and starting again) cannot close a circle early.
    """
    # Imported here rather than at the top: admin_interface pulls in most of
    # the app, and a cue is read in places - model comments, the frontend
    # contract - that have no business importing it.
    from .admin_interface import AdminInterface

    try:
        AdminInterface().fire_next_event(game_id, expected_at=expected_at)
    except Exception:  # noqa: BLE001 - a timer has nobody to report to
        logger.exception("Firing game %s's cue failed", game_id)


def sweep() -> int:
    """Rebuild the timers from the database. Returns how many cues were found.

    Called once at startup. A cue still in the future is re-armed; one whose
    moment passed while the process was down fires immediately, because a
    circle that should have closed ten minutes ago should close now rather
    than never.
    """
    from .admin_interface import AdminInterface

    cues = AdminInterface().get_cued_games()
    now = time.time()
    for game_id, at in cues:
        if at <= now:
            logger.warning(
                "Game %s's cue was due %.0fs ago - firing it now", game_id, now - at
            )
            fire(game_id, expected_at=at)
        else:
            arm(game_id, at)
    return len(cues)
