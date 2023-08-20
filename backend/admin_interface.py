import logging
from typing import List
from typing import Tuple
from uuid import UUID

from fastapi import HTTPException

from . import database
from .model import Game
from .model import GameModel
from .model import Shot
from .model import ShotModel
from .user_interface import UserInterface


logger = logging.getLogger(__name__)


class AdminInterface:
    @classmethod
    def get_games(cls) -> List[GameModel]:
        session = database.Session()
        return [GameModel.from_orm(g) for g in session.query(Game).all()]

    @classmethod
    def get_game(cls, game_id=None) -> GameModel:
        session = database.Session()
        g = session.query(Game).filter_by(id=game_id).first()
        if not g:
            raise HTTPException(404, f"Game {game_id} not found")
        return GameModel.from_orm(g)

    @classmethod
    def create_game(cls) -> UUID:
        session = database.Session()
        g = Game()
        session.add(g)
        session.commit()

        return g.id

    @classmethod
    def get_unchecked_shots(cls, limit=5) -> Tuple[int, List[ShotModel]]:
        session = database.Session()

        query = session.query(Shot).filter_by(checked=False).order_by(Shot.time_created)

        num_shots = query.count()
        filtered_shots = query.limit(limit).all()

        return num_shots, [ShotModel.from_orm(s) for s in filtered_shots]

    @classmethod
    def kill_user(cls, user_id):
        UserInterface(user_id).kill()
