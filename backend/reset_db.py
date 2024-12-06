import logging
import os
import random
from uuid import UUID
from uuid import uuid4

from .database import engine as db_engine
from .dotenv import load_env_vars
from .model import Base
from .model import Game
from .model import Team

random.seed(0)

logger = logging.getLogger(__name__)

SAMPLE_GAME_ID = UUID("a47c0fcf-67bd-4c91-a83b-1ac6c3d8fd43")

TEAM_COLOURS = [
    "Red Team",
    "Blue Team",
    "Green Team",
    "Yellow Team",
    "Purple Team",
    "Orange Team",
    "Pink Team",
    "Cyan Team",
    "Brown Team",
    "Black Team",
]


SAMPLE_TEAMS = [(uuid4(), team_name) for team_name in TEAM_COLOURS]


def reset_database(engine):
    target_metadata = Base.metadata
    # target_metadata.bind = engine
    target_metadata.drop_all(bind=engine)
    target_metadata.create_all(bind=engine)

    logger.warning("Resetting database")

    if "MAKE_DEBUG_ENTRIES" in os.environ:
        from . import database

        logger.warning("Making debug entries in database")

        session = database.Session()
        g = Game(id=SAMPLE_GAME_ID)
        g.active = True
        session.add(g)
        for team_id, team_name in SAMPLE_TEAMS:
            session.add(Team(id=team_id, game=g, name=team_name))

        session.commit()


if __name__ == "__main__":
    load_env_vars()
    reset_database(engine=db_engine)
