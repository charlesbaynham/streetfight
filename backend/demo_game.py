"""Fire the sample game's ten demo shots one at a time, live, over five minutes.

``npm run demoshots`` (:mod:`backend.test_world.replay`) drops all ten in at
once. That is the right shape for a queue to adjudicate and the wrong shape
for a dashboard to *watch*: the spectator screen's whole job is to react to a
shot landing, and it cannot show that if every shot landed before the page
loaded. So this fires the same ten shots one at a time, roughly thirty seconds
apart, from a background task an admin starts and can stop.

**Time is sped up, and re-anchored rather than merely scaled.** The world's
shots are spread over ninety minutes and we want them in five, but a shot's
``location_context`` is a snapshot of the fixes that existed when its
photograph was taken -- the point R11 exists to test -- so squashing the fix
timestamps along with the shot times would quietly hand every shot a
perfectly-fresh crowd. Instead each shot gets its *own* anchor,
``anchor_epoch(tick)``, which puts that shot's tick at this instant: the shot
reads as just fired, and every fix behind it keeps the exact age the world
gave it. Between shots the cast jump forward by minutes of world time in
seconds of wall time, which is what "speed up time" means here.

Three properties the admin button needs:

* **Idempotent.** Starting a run that is already going returns its status and
  changes nothing. Even across a cancel, a restart *resumes*: the shot ids are
  derived from the seed, so the shots already fired are skipped and the drip
  picks up at the next one. A half-provisioned game -- the cast interrupted
  part-way through, by a crash, a reload, or a deleted player -- is
  *completed* rather than fired into: the next press finishes provisioning
  the missing players before resuming the drip.
* **Cancellable.** Cancelling stops the task between shots; what has already
  been fired stays fired.
* **Refuses a real game.** If any player who is in a team is not one of the
  thirty simulated ones, this does nothing at all. The demo provisions thirty
  players and fires shots at them, and there is now a live game whose database
  must never be on the receiving end of that.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import List
from typing import Optional

from .database import session_scope
from .model import Game
from .model import User
from .reset_db import SAMPLE_SEED
from .reset_db import sample_game_id
from .test_world import ids
from .test_world import replay as replay_mod

logger = logging.getLogger(__name__)

# "About five minutes", spread over however many shots the world describes.
DEFAULT_TOTAL_S = 300.0

STATE_IDLE = "idle"
STATE_PROVISIONING = "provisioning"
STATE_FIRING = "firing"
STATE_DONE = "done"
STATE_CANCELLING = "cancelling"
STATE_CANCELLED = "cancelled"
STATE_ERROR = "error"


class DemoGameRefused(RuntimeError):
    """This database has a real game in it, so the demo will not touch it."""


@dataclass
class _Run:
    """One press of the button, and everything the status endpoint reports."""

    seed: int
    total_s: float
    world_path: Path
    images_dir: Optional[Path]
    state: str = STATE_PROVISIONING
    total: int = 0
    already_fired: int = 0
    fired: List[dict] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    interval_s: Optional[float] = None
    next_fire_at: Optional[float] = None
    error: Optional[str] = None
    task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()


_current: Optional[_Run] = None


def demo_user_ids(seed: int = SAMPLE_SEED) -> set:
    """The ids the thirty simulated players have, derived from the seed."""
    from .test_world.personas import build_cast

    return {ids.user_id(seed, person["slug"]) for person in build_cast(seed)}


def strangers(seed: int = SAMPLE_SEED) -> List[str]:
    """Players in a team who are not part of the demo cast.

    Membership of a *team* is the test rather than mere existence: a browser
    that opened the app once leaves a nameless user row behind, and refusing
    to demo because of one would be useless. A player in a team is somebody
    playing a game.
    """
    known = demo_user_ids(seed)
    with session_scope() as session:
        rows = session.query(User.id, User.name).filter(User.team_id.isnot(None)).all()
    return [name or str(user_id) for user_id, name in rows if user_id not in known]


def refuse_if_live(seed: int = SAMPLE_SEED) -> None:
    found = strangers(seed)
    if not found:
        return
    shown = ", ".join(sorted(found)[:5])
    if len(found) > 5:
        shown += f", and {len(found) - 5} more"
    raise DemoGameRefused(
        f"{len(found)} player(s) in this database are not part of the demo cast "
        f"({shown}). The demo game creates thirty players and shoots at them, so "
        "it will not run against a game somebody is playing."
    )


def _provision(seed: int) -> None:
    """Make the sample game, or finish it, unless the whole cast is there.

    The ``Game`` row existing is not proof the cast is: ``test_world.cast
    .provision`` commits the game, then the teams, then each of the thirty
    players in their own transaction, so anything that interrupts it part-way
    -- the service restarting, a dev-server reload, an exception mid-pick --
    leaves a game row with a missing or partial cast. Checking for the
    players themselves, not just the game, is what makes a second press
    *finish* a half-provisioned game rather than skip straight to firing
    shots at shooters who were never really there.

    Synchronous, and therefore blocking the event loop for the few seconds
    thirty players take to pick outfits through the real allocator. That is
    the same bargain ``MAKE_DEBUG_ENTRIES`` strikes at startup, and moving it
    to a thread would put ``@db_scoped``'s post-commit update events -- which
    set asyncio Events -- off the loop that owns them.
    """
    from .reset_db import make_debug_entries

    game_id = sample_game_id()
    wanted = demo_user_ids(seed)
    with session_scope() as session:
        game_present = session.get(Game, game_id) is not None
        present = {
            user_id
            for (user_id,) in session.query(User.id)
            .filter(User.id.in_(wanted), User.team_id.isnot(None))
            .all()
        }
    missing = wanted - present

    if game_present and not missing:
        return

    logger.warning(
        "Demo game: provisioning the sample game %s (%d of %d cast members missing)",
        game_id,
        len(missing),
        len(wanted),
    )
    made = make_debug_entries(seed)
    logger.warning(
        "Demo game: %d players, %d with a location", made["players"], made["located"]
    )


async def _drip(run: _Run) -> None:
    """Provision if needed, then fire the pending shots one at a time."""
    try:
        _provision(run.seed)

        world = replay_mod.load_world(run.world_path)
        shots = replay_mod.demo_shots(world)
        images_dir = run.images_dir or replay_mod.default_images_dir(run.world_path)

        run.total = len(shots)
        # Derived from the whole set, not from what is left, so resuming a
        # cancelled run keeps the pace it started with.
        run.interval_s = run.total_s / max(1, run.total)

        already = replay_mod.fired_shot_ids(ids.game_id(run.seed))
        pending = [
            shot
            for shot in shots
            if ids.shot_id(run.seed, shot["scenario"]) not in already
        ]
        run.already_fired = run.total - len(pending)
        run.state = STATE_FIRING

        for index, shot in enumerate(pending):
            if index:
                run.next_fire_at = time.time() + run.interval_s
                await asyncio.sleep(run.interval_s)
                run.next_fire_at = None
            else:
                # A cancellation point before the first shot, so a cancel
                # arriving during provisioning is still obeyed.
                await asyncio.sleep(0)

            row = replay_mod.fire_shot(
                run.seed,
                world,
                shot,
                images_dir,
                anchor=replay_mod.anchor_epoch(shot["tick"]),
            )
            if row is None:
                logger.warning(
                    "Demo game: no cropped photograph for %s", shot["scenario"]
                )
                run.missing.append(shot["scenario"])
                continue
            logger.info("Demo game: fired %s", row["scenario"])
            run.fired.append(row)

        # Leave everybody where the game left them rather than where the last
        # shot found them, exactly as a whole-evening replay does.
        replay_mod.place_players(
            run.seed,
            world["fixes"],
            world["clock"]["ticks"],
            replay_mod.anchor_epoch(world["clock"]["ticks"]),
        )
    except asyncio.CancelledError:
        run.state = STATE_CANCELLED
        run.next_fire_at = None
        logger.warning("Demo game: cancelled after %d shot(s)", len(run.fired))
        raise
    except Exception as problem:  # noqa: BLE001 - reported through the status
        run.state = STATE_ERROR
        run.next_fire_at = None
        run.error = str(problem)
        logger.exception("Demo game: failed")
    else:
        run.state = STATE_DONE
        run.next_fire_at = None


def start(
    seed: int = SAMPLE_SEED,
    total_s: float = DEFAULT_TOTAL_S,
    world_path: Optional[Path] = None,
    images_dir: Optional[Path] = None,
) -> dict:
    """Start the drip, or leave a running one alone. Returns the status.

    Raises :class:`DemoGameRefused` if this database is somebody's real game.
    """
    global _current

    if _current is not None and _current.running:
        return status()

    refuse_if_live(seed)

    run = _Run(
        seed=seed,
        total_s=total_s,
        world_path=Path(world_path) if world_path else replay_mod.DEFAULT_WORLD,
        images_dir=Path(images_dir) if images_dir else None,
    )
    run.task = asyncio.create_task(_drip(run))
    _current = run
    return status()


def cancel() -> dict:
    """Stop the drip between shots. What has been fired stays fired."""
    if _current is not None and _current.running:
        _current.state = STATE_CANCELLING
        _current.task.cancel()
    return status()


def status() -> dict:
    """What the admin page draws: state, progress, and when the next shot is."""
    run = _current
    if run is None:
        return {
            "state": STATE_IDLE,
            "running": False,
            "fired": 0,
            "total": 0,
            "already_fired": 0,
            "scenarios": [],
            "missing": [],
            "interval_s": None,
            "next_in_s": None,
            "error": None,
        }

    next_in = None
    if run.next_fire_at is not None:
        next_in = max(0.0, round(run.next_fire_at - time.time(), 1))

    return {
        "state": run.state,
        "running": run.running,
        # Counting what was already there as done: a resumed run's progress
        # bar is about the game, not about this press of the button.
        "fired": run.already_fired + len(run.fired),
        "total": run.total,
        "already_fired": run.already_fired,
        "scenarios": [row["scenario"] for row in run.fired],
        "missing": run.missing,
        "interval_s": run.interval_s,
        "next_in_s": next_in,
        "error": run.error,
    }


def _reset_for_tests() -> None:
    global _current
    _current = None
