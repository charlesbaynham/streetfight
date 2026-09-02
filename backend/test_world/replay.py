"""Put the ten demo shots into the sample game, as shots somebody fired.

``observe`` crops each generated photograph to the 1080x2048 a phone really
produces; this is what turns those crops into rows in a database. The part
that needs care is *when*. A shot's ``location_context`` is a snapshot of
where every phone said its owner was at the moment of the photograph, and the
world's thirty players walk around for an hour -- so firing all ten against
the positions the game ended at would produce shots whose telemetry
contradicts their own pictures. That contradiction is precisely what R11
exists to give the identification code a fair test of, so manufacturing it by
accident would be worse than useless.

So the replay walks the scenarios in tick order, moves the whole cast to the
fix each of them had *at that tick* before firing, and stamps the shot with
the moment it was taken. The simulated hour is anchored to end now: the newest
shot is a minute old, the oldest about ninety, and every fix age in the
database is the one the world said it would be.

The pieces are separated from :func:`load_shots` because there are two ways to
want them. This module's own way dumps all ten in at once, which is what a
queue to adjudicate wants. :mod:`backend.demo_game` fires the same ten one at
a time over five minutes, which is what a dashboard to *watch* wants, and it
re-anchors each shot as it goes (see there).
"""

import datetime
import logging
from pathlib import Path
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional
from uuid import UUID

from backend.database import session_scope
from backend.model import Game
from backend.model import Shot
from backend.model import User
from backend.test_world import generate as generate_mod
from backend.test_world import ids
from backend.test_world import store as store_mod
from backend.test_world import telemetry as telemetry_mod
from backend.test_world import world as world_mod
from backend.user_interface import UserInterface

logger = logging.getLogger(__name__)

# Package data, so it is found from the module rather than from the current
# directory: the demo game is an admin *button*, and the deployed unit runs out
# of the state directory (/data), where a relative path finds nothing. See the
# note in backend/test_world/__init__.py.
DEFAULT_WORLD = Path(__file__).resolve().parent / "data" / "world.json"


def anchor_epoch(seconds_before_now: int, now: Optional[float] = None) -> float:
    """Epoch seconds for tick 0, if tick ``seconds_before_now`` is *now*.

    The world is set on a date in September; anchoring to it literally would
    put every shot in the future, where ``shot_identification`` reads each fix
    as newer than the shot it belongs to and so perfectly fresh. Ending the
    hour at the present moment keeps the *relative* times the world computed
    -- which are the ones that matter -- and puts them where a dev's clock can
    see them.

    Pass the world's whole duration to end the game now (what a replay of the
    finished evening wants); pass one shot's tick to make *that* shot now
    (what firing them live wants).

    Whole seconds, because a shot's time is stored to the second: a fractional
    anchor rounds the shot down and leaves every fix age in its context up to
    a second short of what the world says it is.
    """
    import time

    return float(int((now if now is not None else time.time()) - seconds_before_now))


def load_world(world_path: Path = DEFAULT_WORLD) -> dict:
    """The world file, with the scenes the demo shots are described by."""
    world_path = Path(world_path)
    world = world_mod.load(world_path)
    scenes = world.get("scenes") or {}
    if not scenes.get("shots"):
        raise RuntimeError(
            f"{world_path} has no scenes in it - run `python -m backend.test_world "
            "scenes` first"
        )
    return world


def demo_shots(world: dict) -> List[dict]:
    """Every demo shot in the world, in the order they were taken."""
    return sorted(world["scenes"]["shots"], key=lambda shot: shot["tick"])


def default_images_dir(world_path: Path = DEFAULT_WORLD) -> Path:
    return Path(world_path).parent / "shots"


def fired_shot_ids(game_id: UUID) -> set:
    """The ids of the shots the sample game already holds.

    Raises if the game itself is not there: everything downstream would
    otherwise fail one player at a time with a much less useful message.
    """
    with session_scope() as session:
        if session.get(Game, game_id) is None:
            raise RuntimeError(
                f"the sample game ({game_id}) is not in this database - reset it "
                "with MAKE_DEBUG_ENTRIES set first"
            )
        return {row[0] for row in session.query(Shot.id).filter_by(game_id=game_id)}


def place_players(
    seed: int, fixes: Dict[str, List[dict]], tick: int, anchor: float
) -> int:
    """Move the cast to the fix each of them had at ``tick``. Returns how many.

    A player whose phone had not reported by ``tick`` has their location
    *cleared* rather than left alone: "we don't know where they were" is a
    real state, and leaving a later fix in place would quietly answer an
    earlier shot's question with information that did not exist yet.

    Writes the columns directly, in one session, for the same reason
    :func:`UserInterface.set_location` uses a detached one: this is a position
    being restored, not a player moving, and it must not fire an update event
    per player per shot.
    """
    placed = 0
    with session_scope() as session:
        for slug, timeline in fixes.items():
            user = session.get(User, ids.user_id(seed, slug))
            if user is None:
                continue
            fix = telemetry_mod.newest_fix_at(timeline, tick)
            if fix is None:
                user.latitude = None
                user.longitude = None
                user.location_timestamp = None
                user.location_accuracy = None
                continue
            user.latitude = fix["lat"]
            user.longitude = fix["long"]
            user.location_accuracy = fix["accuracy"]
            user.location_timestamp = anchor + fix["t"]
            placed += 1
    return placed


def load_reference_photos(seed: int, world_path: Path = DEFAULT_WORLD) -> int:
    """Give each of the cast the kit-check photo taken of them at the door.

    The thirty reference photographs are the generator's, so they are found
    the way it finds them -- by planning the world against the image store
    beside ``world.json`` -- and they live only in a checkout: the store and
    the fixtures the ids are hashed from are not package data (see
    ``backend/test_world/__init__.py``), so a deployment provisions the cast
    without them and this returns 0 rather than failing the demo button.

    Stored straight to the column, never reviewed: a review would cost a
    vision call per player every reset, and the door page can run one by hand.
    Returns how many players got a photograph.
    """
    store = store_mod.ImageStore(Path(world_path).parent / "images")
    if not store.root.is_dir():
        return 0
    try:
        plan = generate_mod.plan(load_world(world_path), world_path, store=store)
    except FileNotFoundError:
        return 0

    loaded = 0
    with session_scope() as session:
        for job in plan.jobs:
            if job.kind != "reference" or not store.has(job.image_id):
                continue
            user = session.get(User, ids.user_id(seed, job.name))
            if user is None:
                continue
            user.reference_photo_base64 = generate_mod.data_url(
                store.path_for(job.image_id)
            )
            user.reference_review_state = None
            user.reference_review = None
            loaded += 1
    return loaded


def _stamp(anchor: float, tick: int) -> datetime.datetime:
    """The wall-clock moment of ``tick``, as the database writes times.

    Naive UTC, because that is what ``func.now()`` stores on both SQLite and
    Postgres -- a demo shot has to sort against a real one.
    """
    moment = datetime.datetime.fromtimestamp(anchor + tick, datetime.timezone.utc)
    return moment.replace(tzinfo=None, microsecond=0)


def fire_shot(
    seed: int,
    world: dict,
    shot: dict,
    images_dir: Path,
    anchor: float,
) -> Optional[dict]:
    """Fire one demo shot, with the cast standing where its moment found them.

    Returns a row describing what was fired, or ``None`` if the cropped
    photograph is not on disk (``observe --execute`` makes those).
    """
    image = Path(images_dir) / f"{shot['scenario']}.jpg"
    if not image.exists():
        return None

    place_players(seed, world["fixes"], shot["tick"], anchor)

    with UserInterface(ids.user_id(seed, shot["shooter"]["slug"])) as ui:
        # The cast start the sample game with no ammo, and firing costs a
        # bullet. Handed over one at a time rather than in a lump, so a
        # player who fires twice ends the replay where they started.
        ui.award_ammo()
        ui.submit_shot(
            generate_mod.data_url(image),
            heading=shot["heading"],
            shot_id=ids.shot_id(seed, shot["scenario"]),
            time_created=_stamp(anchor, shot["tick"]),
        )

    return {
        "scenario": shot["scenario"],
        "shooter": shot["shooter"]["slug"],
        "target": shot["target"]["slug"],
        "intended_result": shot["intended_result"],
        "seconds_ago": world["clock"]["ticks"] - shot["tick"],
    }


def load_shots(
    seed: int,
    world_path: Path = DEFAULT_WORLD,
    images_dir: Optional[Path] = None,
    now: Optional[float] = None,
    only: Optional[Iterable[str]] = None,
) -> dict:
    """Replay every demo shot that is not in the sample game already.

    Idempotent: the shot ids are derived from the seed and the scenario, so a
    second run finds all ten present and does nothing. ``only`` narrows the
    replay to named scenarios ("S4"), which is how you get one shot back after
    adjudicating it into the wrong answer.
    """
    world = load_world(world_path)
    images_dir = Path(images_dir) if images_dir else default_images_dir(world_path)

    game_id = ids.game_id(seed)
    already_there = fired_shot_ids(game_id)

    anchor = anchor_epoch(world["clock"]["ticks"], now)
    loaded, skipped, missing = [], [], []

    wanted = set(only) if only is not None else None

    for shot in demo_shots(world):
        scenario = shot["scenario"]
        if wanted is not None and scenario not in wanted:
            continue
        if ids.shot_id(seed, scenario) in already_there:
            skipped.append(scenario)
            continue

        row = fire_shot(seed, world, shot, images_dir, anchor)
        if row is None:
            missing.append(scenario)
            continue
        loaded.append(row)

    # Leave everybody where the game left them, not where the last shot found
    # them: the admin map and the spectator screen show the present.
    placed = place_players(seed, world["fixes"], world["clock"]["ticks"], anchor)

    return {
        "game_id": game_id,
        "loaded": loaded,
        "skipped": skipped,
        "missing": missing,
        "located": placed,
        "anchor": anchor,
    }
