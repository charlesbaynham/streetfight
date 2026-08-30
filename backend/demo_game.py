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

Five properties the admin button needs:

* **Every press starts the game from the beginning.** The button empties the
  database, rebuilds the thirty players from the seed, arms them, unpauses the
  game and fires all ten shots from the first. It used to *resume* -- a press
  after a cancel picked up at the next unfired shot -- which is the wrong
  thing for a demo somebody is about to show to a room: what you want is the
  game you have already seen, again, from the top.
* **It arms the cast.** They are provisioned as they would arrive at the door
  -- no ammo, no weapon (``UserInterface.DEFAULT_SHOT_DAMAGE`` is zero) -- and
  a shot from an unarmed player takes nobody's last hit point, so nothing on
  the dashboard ever changes. So each of them is handed plenty of ammo, the
  weakest weapon there is, and no armour at all: a hit kills.
* **A shot nobody can fire is skipped, not fatal.** The cast have one hit
  point each, so a shot the queue judges a hit kills its target -- and if a
  later scenario has that player shooting back, ``submit_shot`` refuses it
  with "User is dead". The scenario is dropped into ``skipped`` (with the
  reason, which the admin page shows) and the run carries on; the first
  casualty must not end the demo with six shots unfired.
* **Cancellable.** Cancelling stops the task between shots; what has already
  been fired stays fired, until the next press wipes it.
* **Refuses a real game.** If any player who is in a team is not one of the
  thirty simulated ones, or the database holds a game that is not the demo's
  own, this does nothing at all. That guard was always important -- the demo
  provisions thirty players and fires shots at them -- and now that a press
  *drops every table*, it is the only thing standing between this button and
  somebody's real evening. It is asked twice: once before the task is created,
  and again with nothing in between it and the drop itself.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import List
from typing import Optional

from fastapi import HTTPException

from .database import session_scope
from .model import DEFAULT_SHOT_TIMEOUT
from .model import Game
from .model import User
from .reset_db import SAMPLE_SEED
from .test_world import ids
from .test_world import replay as replay_mod

logger = logging.getLogger(__name__)

# "About five minutes", spread over however many shots the world describes.
DEFAULT_TOTAL_S = 300.0

# What each simulated player is holding when the demo starts. Ammo they cannot
# plausibly run out of, the weakest weapon in the lookup table (`Pewster`: one
# point of damage, the standard fire delay), and one hit point -- no armour --
# so that a hit that lands kills.
DEMO_BULLETS = 50
DEMO_SHOT_DAMAGE = 1
DEMO_SHOT_TIMEOUT = DEFAULT_SHOT_TIMEOUT
DEMO_HIT_POINTS = 1

STATE_IDLE = "idle"
STATE_RESETTING = "resetting"
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
    state: str = STATE_RESETTING
    total: int = 0
    fired: List[dict] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
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


def foreign_games(seed: int = SAMPLE_SEED) -> List[str]:
    """Games in this database that are not the demo's own.

    The second half of the guard, and the half that only matters now the
    button wipes the database: a game an admin created ten minutes ago and has
    not yet handed a join code to has no players in a team, so
    :func:`strangers` sees nothing to complain about. Dropping every table
    would take it with everything else, and "the teams I set up have gone" is
    exactly the outcome this button must never produce.
    """
    demo_game_id = ids.game_id(seed)
    with session_scope() as session:
        rows = session.query(Game.id).filter(Game.id != demo_game_id).all()
    return [str(game_id) for (game_id,) in rows]


def refuse_if_live(seed: int = SAMPLE_SEED) -> None:
    found = strangers(seed)
    if found:
        shown = ", ".join(sorted(found)[:5])
        if len(found) > 5:
            shown += f", and {len(found) - 5} more"
        raise DemoGameRefused(
            f"{len(found)} player(s) in this database are not part of the demo cast "
            f"({shown}). The demo game clears the database, creates thirty players "
            "and shoots at them, so it will not run against a game somebody is "
            "playing."
        )

    others = foreign_games(seed)
    if others:
        shown = ", ".join(sorted(others)[:5])
        if len(others) > 5:
            shown += f", and {len(others) - 5} more"
        raise DemoGameRefused(
            f"{len(others)} game(s) in this database are not the demo's own "
            f"({shown}). The demo game clears the database, so it will not run "
            "where somebody else's game would be wiped with it."
        )


def _reset_database(seed: int) -> None:
    """Empty every table, so the press replays the game from the beginning.

    The guard is asked again here rather than trusted from :func:`start`: this
    is the line that does the damage, and there is nothing between the
    question and the answer.
    """
    refuse_if_live(seed)

    from .database import engine
    from .reset_db import reset_database

    logger.warning("Demo game: clearing the database")
    reset_database(engine)


def _provision(seed: int) -> None:
    """Build the sample game from nothing.

    Unconditional, because :func:`_reset_database` ran a moment ago and there
    is never anything left to resume from. (This used to have to work out
    whether a previous press had been interrupted part-way through the cast;
    wiping first makes that question moot, which is most of why wiping is
    worth it.)

    Synchronous, and therefore blocking the event loop for the few seconds
    thirty players take to pick outfits through the real allocator. That is
    the same bargain ``MAKE_DEBUG_ENTRIES`` strikes at startup, and moving it
    to a thread would put ``@db_scoped``'s post-commit update events -- which
    set asyncio Events -- off the loop that owns them.
    """
    from .reset_db import make_debug_entries

    logger.warning("Demo game: provisioning the sample game %s", ids.game_id(seed))
    made = make_debug_entries(seed)
    logger.warning(
        "Demo game: %d players, %d with a location", made["players"], made["located"]
    )


def _kit_out(seed: int) -> int:
    """Arm the cast: ammo, the weakest weapon, no armour. Returns how many.

    Written straight to the columns in one session, for the reason
    ``replay.place_players`` gives: this is a game being set up, not thirty
    players each collecting something, and it must not fire an update event
    per player.
    """
    armed = 0
    with session_scope() as session:
        for user_id in demo_user_ids(seed):
            user = session.get(User, user_id)
            if user is None:
                continue
            user.num_bullets = DEMO_BULLETS
            user.shot_damage = DEMO_SHOT_DAMAGE
            user.shot_timeout = DEMO_SHOT_TIMEOUT
            user.hit_points = DEMO_HIT_POINTS
            user.time_of_death = None
            armed += 1
    return armed


def _unpause(seed: int) -> bool:
    """Start the game if it is paused. Returns whether it had to be started.

    A freshly created game is inactive, and so is one an admin paused before
    pressing the button. Either way the demo has ten shots to show and a
    paused game to show them in, so it starts the game itself -- through
    ``AdminInterface`` rather than the column, so the ticker says "Game
    started" and every player's client hears about it.
    """
    from .admin_interface import AdminInterface

    game_id = ids.game_id(seed)
    with session_scope() as session:
        game = session.get(Game, game_id)
        if game is None or game.active:
            return False

    logger.warning("Demo game: starting the paused game %s", game_id)
    AdminInterface().set_game_active(game_id, True)
    return True


async def _drip(run: _Run) -> None:
    """Wipe, rebuild, arm, unpause, then fire the shots one at a time."""
    try:
        _reset_database(run.seed)

        run.state = STATE_PROVISIONING
        _provision(run.seed)
        _kit_out(run.seed)
        _unpause(run.seed)

        world = replay_mod.load_world(run.world_path)
        shots = replay_mod.demo_shots(world)
        images_dir = run.images_dir or replay_mod.default_images_dir(run.world_path)

        run.total = len(shots)
        run.interval_s = run.total_s / max(1, run.total)
        run.state = STATE_FIRING

        for index, shot in enumerate(shots):
            if index:
                run.next_fire_at = time.time() + run.interval_s
                await asyncio.sleep(run.interval_s)
                run.next_fire_at = None
            else:
                # A cancellation point before the first shot, so a cancel
                # arriving during provisioning is still obeyed.
                await asyncio.sleep(0)

            try:
                row = replay_mod.fire_shot(
                    run.seed,
                    world,
                    shot,
                    images_dir,
                    anchor=replay_mod.anchor_epoch(shot["tick"]),
                )
            except HTTPException as refusal:
                # The cast have one hit point and no armour, so a shot the
                # queue judges a hit kills its target -- and a later scenario
                # may have that player shooting back, which `submit_shot`
                # refuses with "User is dead". That is the demo working, not
                # the demo broken: the auto-actions this button exists to show
                # off are what killed them. So the scenario is dropped and the
                # rest of the run goes on, rather than the first casualty
                # ending the evening with six shots unfired.
                logger.warning(
                    "Demo game: skipping %s - %s", shot["scenario"], refusal.detail
                )
                run.skipped.append(
                    {"scenario": shot["scenario"], "reason": str(refusal.detail)}
                )
                continue
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

    A press while a run is going changes nothing -- the run is already showing
    what the button promises. A press after one has finished or been cancelled
    wipes the database and plays the whole game again from the first shot.

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
            "scenarios": [],
            "missing": [],
            "skipped": [],
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
        "fired": len(run.fired),
        "total": run.total,
        "scenarios": [row["scenario"] for row in run.fired],
        "missing": run.missing,
        "skipped": run.skipped,
        "interval_s": run.interval_s,
        "next_in_s": next_in,
        "error": run.error,
    }


def _reset_for_tests() -> None:
    global _current
    _current = None
