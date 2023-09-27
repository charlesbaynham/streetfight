import asyncio
import logging
from typing import List
from typing import Tuple
from uuid import UUID
from uuid import uuid4 as get_uuid

from fastapi import HTTPException

from . import database
from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event
from .image_processing import draw_cross_on_image
from .items import ItemModel
from .model import Game
from .model import GameModel
from .model import ItemType
from .model import Shot
from .model import ShotModel
from .model import Team
from .model import User
from .model import UserModel
from .ticker import Ticker
from .user_interface import UserInterface

logger = logging.getLogger(__name__)


class AdminInterface:
    def __init__(self) -> None:
        logger.debug("Making session for AdminInterface")
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

    def _get_shot_orm(self, shot_id) -> Shot:
        s = self.session.query(Shot).get(shot_id)
        if not s:
            raise HTTPException(404, f"Shot {shot_id} not found")
        return s

    def get_games(self) -> List[GameModel]:
        logger.info("AdminInterface - get_games")
        return [GameModel.from_orm(g) for g in self.session.query(Game).all()]

    def get_users(self, team_id: UUID = None, game_id: UUID = None) -> List[UserModel]:
        logger.info("AdminInterface - get_users")

        q = self.session.query(User)

        if team_id:
            q.filter_by(team_id=team_id)
        if game_id:
            q.filter_by(game_id=game_id)

        return [UserModel.from_orm(g) for g in q.all()]

    def get_game(self, game_id) -> GameModel:
        logger.info("AdminInterface - get_game")
        g = self._get_game_orm(game_id)
        return GameModel.from_orm(g)

    def create_game(self) -> UUID:
        logger.info("AdminInterface - create_game")
        g = Game()
        self.session.add(g)
        self.session.commit()

        return g.id

    def create_team(self, game_id: UUID, name: str) -> int:
        logger.info("AdminInterface - create_team")
        game = self._get_game_orm(game_id)
        team = Team(name=name)
        game.teams.append(team)
        self.session.commit()

        return team.id

    def set_game_active(self, game_id: UUID, active: bool) -> int:
        logger.info("AdminInterface - set_game_active %s/%s", game_id, active)

        game = self._get_game_orm(game_id)
        game.active = active

        # Collect the user IDs for manual bumping after the session is committed
        user_ids = []
        for team in game.teams:
            for user in team.users:
                user_ids.append(user.id)

        ticker = Ticker(game.id, session=self.session)
        if active:
            ticker.post_message(f"Game started")
        else:
            ticker.post_message(f"Game paused")

        self.session.commit()

        # Manually bump all the users
        for user_id in user_ids:
            trigger_update_event("user", user_id)

    def add_user_to_team(self, user_id: UUID, team_id: UUID):
        logger.info("AdminInterface - add_user_to_team")
        ui = UserInterface(user_id)
        ui.join_team(team_id)
        user_name = ui.get_user_model().name
        team_name = ui.get_team_model().name
        ui.get_ticker().post_message(f'{user_name} joined team "{team_name}"')

    def get_unchecked_shots(self, limit=5) -> Tuple[int, List[ShotModel]]:
        query = (
            self.session.query(Shot)
            .filter_by(checked=False)
            .order_by(Shot.time_created)
        )

        num_shots = query.count()
        filtered_shots = query.limit(limit).all()

        shot_models = [ShotModel.from_orm(s) for s in filtered_shots]

        for shot_model in shot_models:
            shot_model.image_base64 = draw_cross_on_image(shot_model.image_base64)

        return num_shots, shot_models

    def hit_user(self, shot_id, target_user_id):
        shot = self._get_shot_orm(shot_id)

        u_from = shot.user
        u_to = self._get_user_orm(target_user_id)

        ui = UserInterface(target_user_id)

        ui.kill(shot.shot_damage)

        if u_to.hit_points > 0:
            ui.get_ticker().post_message(f"{u_from.name} hit {u_to.name}")
        else:
            ui.get_ticker().post_message(f"{u_from.name} killed {u_to.name}")

    def award_user_HP(self, user_id, num=1):
        ui = UserInterface(user_id)

        ui.award_HP(num=num)

        user_model = ui.get_user_model()
        ticker = ui.get_ticker()
        if ticker:
            ticker.post_message(f"{user_model.name} was given {num} armour")

    def award_user_ammo(self, user_id, num=1):
        ui = UserInterface(user_id)

        ui.award_ammo(num=num)

        user_model = ui.get_user_model()
        ticker = ui.get_ticker()
        if ticker:
            ticker.post_message(f"{user_model.name} was given {num} ammo")

    def mark_shot_checked(self, shot_id):
        shot = self.session.query(Shot).filter_by(id=shot_id).first()

        if not shot:
            raise HTTPException(404, f"Shot id {shot_id} not found")

        if shot.checked:
            raise HTTPException(400, f"Shot id {shot_id} has already been checked")

        shot.checked = True
        self.session.commit()

    def make_new_item(self, item_type: str, item_data: dict) -> str:
        logger.info("make_new_item item_type=%s, item_data=%s", item_type, item_data)
        try:
            item_type = ItemType(item_type)
        except ValueError:
            raise HTTPException(
                400,
                "Invalid item type. Valid choices are %s" % [t.value for t in ItemType],
            )

        item = ItemModel(id=get_uuid(), itype=item_type, data=item_data)
        item.sign()

        encoded_item = item.to_base64()
        logger.info("Made new item: %s => %s", item, encoded_item)

        return encoded_item

    async def generate_any_ticker_updates(self, timeout=None):
        """
        An async iterator that yields None every time any ticker is updated in any
        game, or at most after timeout seconds
        """
        while True:
            game_ids = self.session.query(Game.id).all()

            # Lookup / make an event for each game's ticker
            events = []
            for game_id in game_ids:
                logger.debug("(AdminInterface) Getting event for game %s", game_id[0])
                events.append(get_trigger_event("ticker", game_id[0]))

            # make futures for waiting for all these events
            futures = [
                asyncio.wait_for(event.wait(), timeout=timeout) for event in events
            ]

            try:
                logger.debug("(Admin Updater) Subscribing to events %s", events)
                await next(asyncio.as_completed(futures))

                logger.debug("(Admin Updater) Event received")
                yield
            except asyncio.TimeoutError:
                logger.debug("(Admin Updater) Event timeout")
                yield
