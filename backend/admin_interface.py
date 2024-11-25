import asyncio
import logging
import os
from typing import List
from typing import Tuple
from uuid import UUID
from uuid import uuid4 as get_uuid

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy.orm import Session

from . import ticker_message_dispatcher as tk
from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event
from .database_scope_provider import DatabaseScopeProvider
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
from .utils import add_params_to_url

logger = logging.getLogger(__name__)


AdminScopeWrapper = DatabaseScopeProvider("admin")
db_scoped = AdminScopeWrapper.db_scoped


class AdminInterface:
    def __init__(self, session=None) -> None:
        self._session: Session = session

    @db_scoped
    def _get_user_orm(self, user_id) -> User:
        g = self._session.query(User).filter_by(id=user_id).first()
        if not g:
            raise HTTPException(404, f"User {user_id} not found")
        return g

    @db_scoped
    def _get_game_orm(self, game_id) -> Game:
        g = self._session.query(Game).filter_by(id=game_id).first()
        if not g:
            raise HTTPException(404, f"Game {game_id} not found")
        return g

    @db_scoped
    def _get_team_orm(self, team_id) -> Team:
        t = self._session.query(Team).filter_by(id=team_id).first()
        if not t:
            raise HTTPException(404, f"Team {team_id} not found")
        return t

    @db_scoped
    def _get_shot_orm(self, shot_id) -> Shot:
        s = self._session.query(Shot).get(shot_id)
        if not s:
            raise HTTPException(404, f"Shot {shot_id} not found")
        return s

    @db_scoped
    def get_shot_model(self, shot_id) -> ShotModel:
        s = self._get_shot_orm(shot_id)
        return ShotModel.from_orm(s)

    @db_scoped
    def get_games(self) -> List[GameModel]:
        logger.info("AdminInterface - get_games")
        return [GameModel.from_orm(g) for g in self._session.query(Game).all()]

    @db_scoped
    def get_users(self, team_id: UUID = None, game_id: UUID = None) -> List[UserModel]:
        logger.info("AdminInterface - get_users")

        q = self._session.query(User)

        if team_id:
            q.filter_by(team_id=team_id)
        if game_id:
            q.filter_by(game_id=game_id)

        return [UserModel.from_orm(g) for g in q.all()]

    @db_scoped
    def get_game(self, game_id) -> GameModel:
        logger.info("AdminInterface - get_game")
        g = self._get_game_orm(game_id)
        return GameModel.from_orm(g)

    @db_scoped
    def create_game(self) -> UUID:
        logger.info("AdminInterface - create_game")
        g = Game()
        self._session.add(g)
        self._session.commit()

        return g.id

    @db_scoped
    def create_team(self, game_id: UUID, name: str) -> UUID:
        logger.info("AdminInterface - create_team")
        game = self._get_game_orm(game_id)
        team = Team(name=name)
        game.teams.append(team)
        self._session.commit()

        self._get_game_ticker(game_id=game_id).touch_game_ticker_tag()

        return team.id

    @db_scoped
    def _get_game_ticker(self, game_id: UUID) -> Ticker:
        return Ticker(game_id, user_id=None, session=self._session)

    @db_scoped
    def set_game_active(self, game_id: UUID, active: bool) -> int:
        logger.info("AdminInterface - set_game_active %s/%s", game_id, active)

        game = self._get_game_orm(game_id)
        game.active = active

        # Collect the user IDs for manual bumping after the session is committed
        user_ids = []
        for team in game.teams:
            for user in team.users:
                user_ids.append(user.id)

        ticker = self._get_game_ticker(game_id=game_id)
        if active:
            ticker.post_message(f"Game started")
        else:
            ticker.post_message(f"Game paused")

        self._session.commit()

        # Manually bump all the users
        for user_id in user_ids:
            trigger_update_event("user", user_id)

    def add_user_to_team(self, user_id: UUID, team_id: UUID):
        logger.info("AdminInterface - add_user_to_team")
        with UserInterface(user_id) as ui:
            ui.join_team(team_id)

            u = ui.get_user()

            user_name = u.name
            team_name = u.team.name
            game_id = u.team.game_id

            tk.send_ticker_message(
                tk.TickerMessageType.USER_JOINED_TEAM,
                {"user": user_name, "team": team_name},
                game_id=game_id,
                session=ui.get_session(),
            )

    @db_scoped
    def get_unchecked_shots(self, limit=5) -> Tuple[int, List[ShotModel]]:
        query = (
            self._session.query(Shot)
            .filter_by(checked=False)
            .order_by(Shot.time_created)
        )

        num_shots = query.count()
        filtered_shots = query.limit(limit).all()

        shot_models = [ShotModel.from_orm(s) for s in filtered_shots]

        self._session.close()

        for shot_model in shot_models:
            shot_model.image_base64 = draw_cross_on_image(shot_model.image_base64)

        return num_shots, shot_models

    def hit_user_by_admin(self, user_id, num=1):
        with UserInterface(user_id) as ui:
            ui.hit(num)

            u: User = ui.get_user()

            user_name = u.name
            game_id = u.team.game_id

            if u.hit_points > 0:
                message_type = tk.TickerMessageType.ADMIN_HIT_USER
            else:
                message_type = tk.TickerMessageType.ADMIN_HIT_AND_KNOCKED_OUT_USER

            tk.send_ticker_message(
                message_type,
                {"user": user_name, "num": num},
                session=ui.get_session(),
                user_id=user_id,
                game_id=game_id,
            )

    @db_scoped
    def hit_user(self, shot_id, target_user_id):
        shot = self._get_shot_orm(shot_id)

        u_from = shot.user
        ui_target = UserInterface(target_user_id, session=self._session)

        ui_target.hit(shot.shot_damage)

        u_to = self._get_user_orm(target_user_id)

        if u_to.hit_points > 0:
            message_type = tk.TickerMessageType.HIT_AND_DAMAGE

        else:
            message_type = tk.TickerMessageType.HIT_AND_KNOCKOUT
            ui_target.clear_unchecked_shots()

        tk.send_ticker_message(
            message_type,
            {"user": u_from.name, "target": u_to.name, "num": shot.shot_damage},
            game_id=u_from.team.game_id,
            session=self._session,
            highlight_user_id=u_from.id,
        )

        try:
            self.mark_shot_checked(shot_id)
        except HTTPException:
            # Handle the edge case where a user shoots themselves
            pass

        # Record the target user in the db
        shot.target_user_id = target_user_id

    def set_user_HP(self, user_id, num=1):
        with UserInterface(user_id) as ui:
            ui.set_HP(num)

            u = ui.get_user()

            if u.hit_points > 1:
                message_type = tk.TickerMessageType.ADMIN_GAVE_ARMOUR
            elif u.hit_points == 1:
                message_type = tk.TickerMessageType.ADMIN_REVIVED_USER
            else:
                message_type = tk.TickerMessageType.ADMIN_HIT_AND_KILLED_USER

            tk.send_ticker_message(
                message_type,
                {"user": u.name, "num": num - 1},
                user_id=user_id,
                game_id=u.team.game_id,
                team_id=u.team_id,
                session=ui.get_session(),
            )

    def award_user_ammo(self, user_id, num=1):
        with UserInterface(user_id) as ui:
            ui.award_ammo(num=num)

            user_model = ui.get_user_model()

            tk.send_ticker_message(
                tk.TickerMessageType.ADMIN_GAVE_AMMO,
                {"user": user_model.name, "num": num},
                user_id=user_id,
                game_id=user_model.game_id,
                team_id=user_model.team_id,
                session=ui.get_session(),
            )

    def set_user_name(self, user_id, name: str):
        with UserInterface(user_id) as ui:
            ui.set_name(name)

            # Bump the game this user is in
            try:
                game_id = ui.get_user().team.game_id
                trigger_update_event("ticker", game_id)
            except AttributeError:
                # User is not in a team. Meh
                pass

    @db_scoped
    def mark_shot_checked(self, shot_id):
        shot = self._session.query(Shot).filter_by(id=shot_id).first()

        if not shot:
            raise HTTPException(404, f"Shot id {shot_id} not found")

        if shot.checked:
            raise HTTPException(400, f"Shot id {shot_id} has already been checked")

        shot.checked = True
        self._session.commit()

    def make_new_item(
        self,
        item_type: str,
        item_data: dict,
        collected_only_once=True,
        collected_as_team=False,
    ) -> str:
        """Makes a new item with the given settings and encodes it into a URL

        Encoded items can be collected by visiting the URL. The item data itself
        is stored in a query parameter "d" - collecting the item via
        :meth:`UserInterface.collect_item` using this data directly also works.

        Items are signed using the SECRET_KEY environment variable. The URL
        domain is not part of the signature, so it's possible in theory to alter
        this in URLs, but might be annoying to do so, so better to make sure
        that `WEBSITE_URL` is set correctly in the .env file before generating QR
        codes.


        Args:
            item_type (str): The type of item to create
            item_data (dict): The data for the item - a dict that depends on the item type
            collected_only_once (bool, optional): Whether the item can only be collected once. Defaults to True. Otherwise can be collected by other users / teams even after first collection.
            collected_as_team (bool, optional): Whether the item is collected as a team. Defaults to False.
        """
        logger.info("make_new_item item_type=%s, item_data=%s", item_type, item_data)
        try:
            item_type = ItemType(item_type)
        except ValueError:
            raise HTTPException(
                400,
                "Invalid item type. Valid choices are %s" % [t.value for t in ItemType],
            )

        item = ItemModel(
            id=get_uuid(),
            itype=item_type,
            data=item_data,
            collected_only_once=collected_only_once,
            collected_as_team=collected_as_team,
        )
        item.sign()

        encoded_item = item.to_base64()
        logger.info("Made new item: %s => %s", item, encoded_item)

        # Encode this into a URL
        encoded_url = add_params_to_url(os.environ["WEBSITE_URL"], {"d": encoded_item})

        return encoded_url

    @db_scoped
    def get_locations(self, game_id: UUID = None):
        # If game_id is not provided, get the game_id of the first game
        if not game_id:
            game_id = self._session.query(Game.id).first()[0]

        teams = self._session.query(Team).filter_by(game_id=game_id).all()
        locations = []
        for team in teams:
            for user in team.users:
                user: User
                locations.append(
                    {
                        "user_id": user.id,
                        "team_id": team.id,
                        "user": user.name,
                        "team": team.name,
                        "latitude": user.latitude,
                        "longitude": user.longitude,
                        "state": user.state,
                        "timestamp": user.location_timestamp,
                    }
                )
        return locations

    @db_scoped
    def get_scoreboard(self, game_id: UUID):
        teams_and_ids = (
            self._session.query(Team.id, Team.name).filter_by(game_id=game_id).all()
        )
        teams_by_id = {id: name for id, name in teams_and_ids}

        user_data = (
            self._session.query(
                User.id, User.name, User.team_id, User.hit_points, User.time_of_death
            )
            .filter(User.team_id.in_(teams_by_id.keys()))
            .all()
        )
        users_by_id = {
            id: (name, teams_by_id[team_id], hit_points, time_of_death)
            for id, name, team_id, hit_points, time_of_death in user_data
        }

        completed_shots_by_these_users = (
            self._session.query(Shot.user_id, Shot.shot_damage)
            .filter(
                and_(
                    Shot.user_id.in_(users_by_id.keys()),
                    Shot.checked,
                    Shot.target_user_id != None,
                )
            )
            .all()
        )

        self._session.close()

        table = []
        for user_id, (
            username,
            teamname,
            hitpoints,
            time_of_death,
        ) in users_by_id.items():
            total_damage = sum(
                map(
                    lambda s: s[1],
                    filter(lambda s: s[0] == user_id, completed_shots_by_these_users),
                )
            )
            table.append(
                {
                    "name": username,
                    "team": teamname,
                    "hitpoints": hitpoints,
                    "total_damage": total_damage,
                    "state": User.calculate_state(teamname, hitpoints, time_of_death),
                }
            )

        table = sorted(table, key=lambda t: t["total_damage"], reverse=True)

        return {"table": table}

    @db_scoped
    def _get_all_game_ids(self):
        return self._session.query(Game.id).all()

    async def generate_any_ticker_updates(self, timeout=None):
        """
        An async iterator that yields None every time any ticker is updated in any
        game, or at most after timeout seconds
        """
        while True:
            game_ids = self._get_all_game_ids()

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
