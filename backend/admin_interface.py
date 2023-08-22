import logging
from typing import List
from typing import Tuple
from uuid import UUID

from fastapi import HTTPException

from . import database
from .model import Game
from .model import GameModel, Team, TeamModel
from .model import Shot
from .model import ShotModel
from .user_interface import UserInterface


logger = logging.getLogger(__name__)


class AdminInterface:
    def __init__(self) -> None:
        self.session = database.Session()

    def _get_game_orm(self, game_id):
        g = self.session.query(Game).filter_by(id=game_id).first()
        if not g:
            raise HTTPException(404, f"Game {game_id} not found")
        return g

    def get_games(self) -> List[GameModel]:

        return [GameModel.from_orm(g) for g in self.session.query(Game).all()]

    def get_game(self, game_id) -> GameModel:
        g = self._get_game_orm(game_id)
        return GameModel.from_orm(g)

    def create_game(self) -> UUID:
        g = Game()
        self.session.add(g)
        self.session.commit()

        return g.id

    def create_team(self, game_id: UUID, name: str) -> int:
        game = self._get_game_orm(game_id)
        team = Team(name=name)
        game.teams.append(team)
        self.session.commit()

        return team.id

    def get_unchecked_shots(self, limit=5) -> Tuple[int, List[ShotModel]]:
        query = (
            self.session.query(Shot)
            .filter_by(checked=False)
            .order_by(Shot.time_created)
        )

        num_shots = query.count()
        filtered_shots = query.limit(limit).all()

        return num_shots, [ShotModel.from_orm(s) for s in filtered_shots]

    def kill_user(self, user_id):
        UserInterface(user_id).kill()

    def mark_shot_checked(self, shot_id):
        shot = self.session.query(Shot).filter_by(id=shot_id).first()

        if not shot:
            raise HTTPException(404, f"Shot id {shot_id} not found")

        if shot.checked:
            raise HTTPException(400, f"Shot id {shot_id} has already been checked")

        shot.checked = True
        self.session.commit()
