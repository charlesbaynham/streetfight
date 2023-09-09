import logging
from typing import List
from typing import Tuple
from uuid import UUID
from uuid import uuid4 as get_uuid

from fastapi import HTTPException

from . import database
from .model import Game
from .model import GameModel
from .model import Shot
from .model import ShotModel
from .model import Team

from .model import User
from .model import UserModel
from .user_interface import UserInterface

from .items import DecodedItem
from .model import ItemType

logger = logging.getLogger(__name__)


class AdminInterface:
    def __init__(self) -> None:
        self.session = database.Session()

    def _get_user_orm(self, user_id) -> User:
        g = self.session.query(User).filter_by(id=user_id).first()
        if not g:
            raise HTTPException(404, f"User {user_id} not found")
        return g

    def _get_game_orm(self, game_id) -> Game:
        g = self.session.query(Game).filter_by(id=game_id).first()
        if not g:
            raise HTTPException(404, f"Game {game_id} not found")
        return g

    def _get_team_orm(self, team_id) -> Team:
        t = self.session.query(Team).filter_by(id=team_id).first()
        if not t:
            raise HTTPException(404, f"Team {team_id} not found")
        return t

    def get_games(self) -> List[GameModel]:
        return [GameModel.from_orm(g) for g in self.session.query(Game).all()]

    def get_users(self, team_id: UUID = None, game_id: UUID = None) -> List[UserModel]:
        q = self.session.query(User)

        if team_id:
            q.filter_by(team_id=team_id)
        if game_id:
            q.filter_by(game_id=game_id)

        return [UserModel.from_orm(g) for g in q.all()]

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

    def add_user_to_team(self, user_id: UUID, team_id: UUID):
        UserInterface(user_id).join_team(team_id)

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

    def award_user_HP(self, user_id, num=1):
        UserInterface(user_id).award_HP(num=num)

    def award_user_ammo(self, user_id, num=1):
        UserInterface(user_id).award_ammo(num=num)

    def mark_shot_checked(self, shot_id):
        shot = self.session.query(Shot).filter_by(id=shot_id).first()

        if not shot:
            raise HTTPException(404, f"Shot id {shot_id} not found")

        if shot.checked:
            raise HTTPException(400, f"Shot id {shot_id} has already been checked")

        shot.checked = True
        self.session.commit()

    def make_new_item(self, item_type: str, item_data: dict) -> str:
        try:
            item_type = ItemType(item_type)
        except ValueError:
            raise HTTPException(
                400,
                "Invalid item type. Valid choices are %s" % [t.value for t in ItemType],
            )

        item = DecodedItem(id=get_uuid(), item_type=item_type, data=item_data)
        item.sign()

        encoded_item = item.to_base64()
        logger.info("Made new item: %s => %s", item, encoded_item)

        return encoded_item
