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
    from .test_world import ids
    from .test_world import telemetry as telemetry_mod
    from .test_world.cast import provision
    from .test_world.movement import truth_track
    from .test_world.personas import build_cast
    from .user_interface import UserInterface

    cast = build_cast(seed)
    identity = provision(seed, cast)

    # Put each player where their phone last said they were -- not where they
    # really are. The difference is the whole point of the simulated
    # telemetry, and an admin map with nobody on it teaches nothing.
    positions = truth_track(seed, cast)["positions"]
    fixes = telemetry_mod.fix_timelines(seed, cast, positions)
    placed = 0
    for person in cast:
        timeline = fixes.get(person["slug"]) or []
        if not timeline:
            continue
        last = timeline[-1]
        with UserInterface(ids.user_id(seed, person["slug"])) as ui:
            ui.set_location(last["lat"], last["long"], last.get("accuracy"))
        placed += 1

    return {"players": len(cast), "located": placed, "identity": identity}


def reset_database(engine):
    target_metadata = Base.metadata
    target_metadata.drop_all(bind=engine)
    target_metadata.create_all(bind=engine)

    logger.warning("Resetting database")

    if "MAKE_DEBUG_ENTRIES" in os.environ:
        logger.warning("Making debug entries in database")
        made = make_debug_entries()
        logger.warning(
            "Sample game %s: %d players, %d with a location",
            sample_game_id(),
            made["players"],
            made["located"],
        )


if __name__ == "__main__":
    load_env_vars()
    reset_database(engine=db_engine)
