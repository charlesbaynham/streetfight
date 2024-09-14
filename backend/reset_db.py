import logging
import os
from uuid import UUID

from dotenv import find_dotenv
from dotenv import load_dotenv

from .database import engine
from .model import Base
from .model import Game
from .model import Team

logger = logging.getLogger(__name__)

SAMPLE_GAME_ID = UUID("a47c0fcf-67bd-4c91-a83b-1ac6c3d8fd43")

SAMPLE_TEAMS = [
    (UUID("890e8e0a-575b-4df6-85ee-eb7e6656085d"), "Team A"),
    (UUID("c6f6f9f9-3a90-469e-a344-54a2cf33f4e7"), "Team B"),
    (UUID("01f56942-5a4e-48c0-bc9d-b037a0a22653"), "Team C"),
]


def reset_database():
    target_metadata = Base.metadata
    target_metadata.bind = engine
    target_metadata.drop_all()
    target_metadata.create_all()

    logger.warning("Resetting database")

    load_dotenv(find_dotenv())
    if "MAKE_DEBUG_ENTRIES" in os.environ:
        from . import database

        logger.warning("Making debug entries in database")

        session = database.Session()
        g = Game(id=SAMPLE_GAME_ID)
        session.add(g)
        for team_id, team_name in SAMPLE_TEAMS:
            session.add(Team(id=team_id, game=g, name=team_name))

        session.commit()


if __name__ == "__main__":
    reset_database()
