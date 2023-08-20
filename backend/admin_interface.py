import logging
from typing import List
from uuid import UUID

from . import database
from .model import Game
from .model import GameModel
from .model import Shot
from .model import ShotModel


logger = logging.getLogger(__name__)


class AdminInterface:
    @classmethod
    def get_games(cls) -> List[GameModel]:
        session = database.Session()
        return [GameModel.from_orm(g) for g in session.query(Game).all()]

    @classmethod
    def create_game(cls) -> UUID:
        session = database.Session()
        g = Game()
        session.add(g)
        session.commit()

        return g.id

    @classmethod
    def get_unchecked_shots(cls, limit=5) -> List[ShotModel]:
        session = database.Session()
        return [
            ShotModel.from_orm(s)
            for s in session.query(Shot)
            .filter_by(checked=False)
            .order_by(Shot.time_created)
            .limit(limit)
            .all()
        ]
