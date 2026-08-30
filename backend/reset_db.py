"""Create the schema, and optionally a sample game worth looking at.

``MAKE_DEBUG_ENTRIES`` used to make one game and ten empty teams named after
colours. That was wrong in three ways at once: ten teams cannot be given
distinct hat colours from a palette of seven, so the sample game could not
generate a single join QR code; the teams had no players, so nothing that
needs a crowd could be tried at all; and the team ids were minted at *import*
time, so a printed code stopped working when the server restarted rather than
when the database was reset.

It now builds the deterministic test world instead -- six teams of five, each
player having picked an outfit through the real picking code, standing where
their phone last reported them. Everything is derived from one seed, so the
same reset produces the same game and a printed join code keeps working.
"""

import logging
import os
from uuid import UUID

from .database import engine as db_engine
from .dotenv import load_env_vars
from .model import Base

logger = logging.getLogger(__name__)

# The seed the fixture world is built from, so a developer's sample game and
# tests/fixtures/test_game are the same thirty people.
SAMPLE_SEED = 20260919


def sample_game_id() -> UUID:
    from .test_world import ids

    return ids.game_id(SAMPLE_SEED)


# Kept as a module-level name because tests and tools import it. Derived, not
# minted: the whole point is that it survives a restart.
SAMPLE_GAME_ID = sample_game_id()


def make_debug_entries(seed: int = SAMPLE_SEED) -> dict:
    """Provision the sample game. Returns what was made, for logging."""
    from .test_world import spec
    from .test_world import telemetry as telemetry_mod
    from .test_world.cast import provision
    from .test_world.movement import truth_track
    from .test_world.personas import build_cast
    from .test_world.replay import anchor_epoch
    from .test_world.replay import place_players

    cast = build_cast(seed)
    identity = provision(seed, cast)

    # Put each player where their phone last said they were -- not where they
    # really are. The difference is the whole point of the simulated
    # telemetry, and an admin map with nobody on it teaches nothing.
    #
    # Timestamped as the world says rather than as now: a fix that went stale
    # forty minutes before the game ended has to *look* forty minutes stale,
    # or the one thing the telemetry was built to exercise is thrown away at
    # the last step. The simulated hour is anchored to end now, the same
    # bargain `npm run demoshots` strikes when it replays the shots.
    positions = truth_track(seed, cast)["positions"]
    fixes = telemetry_mod.fix_timelines(seed, cast, positions)
    placed = place_players(
        seed, fixes, spec.N_TICKS, anchor=anchor_epoch(spec.DURATION_S)
    )

    return {"players": len(cast), "located": placed, "identity": identity}


def debug_entries_wanted() -> bool:
    return "MAKE_DEBUG_ENTRIES" in os.environ


def make_debug_entries_if_wanted() -> None:
    """Build the sample game, unless it is already there.

    Deliberately *not* called from :func:`reset_database`. That runs inside
    ``database.load()``, which itself runs while ``backend.database`` is being
    imported -- and the sample game is built through ``AdminInterface``, whose
    own import is what pulled ``database`` in. Provisioning there is a
    circular import: the app cannot build a game while it is still being
    assembled. So the schema is created during import and the game is made
    afterwards, by whoever starts the process.
    """
    if not debug_entries_wanted():
        return

    from .database import session_scope
    from .model import Game

    game_id = sample_game_id()
    with session_scope() as session:
        already_there = session.query(Game).filter_by(id=game_id).first() is not None
    if already_there:
        return

    logger.warning("Making debug entries in database")
    made = make_debug_entries()
    logger.warning(
        "Sample game %s: %d players, %d with a location",
        game_id,
        made["players"],
        made["located"],
    )


def reset_database(engine):
    """The schema, and nothing else -- see make_debug_entries_if_wanted."""
    target_metadata = Base.metadata
    target_metadata.drop_all(bind=engine)
    target_metadata.create_all(bind=engine)

    logger.warning("Resetting database")


if __name__ == "__main__":
    load_env_vars()
    reset_database(engine=db_engine)
    make_debug_entries_if_wanted()
