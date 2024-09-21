import asyncio
import logging
import time
from threading import RLock
from typing import List
from typing import Tuple
from typing import Union
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session as SQLAlchemySession

from . import asyncio_triggers
from .asyncio_triggers import get_trigger_event
from .database import session_scope
from .database_scope_provider import DatabaseScopeProvider
from .image_processing import save_image
from .item_actions import do_item_actions
from .items import ItemModel
from .model import Game
from .model import Item
from .model import Shot
from .model import Team
from .model import TeamModel
from .model import User
from .model import UserModel
from .ticker import Ticker

logger = logging.getLogger(__name__)

# 10 minutes to get to safety
TIME_KNOCKED_OUT = 10 * 60

make_user_lock = RLock()


def touch_user(user_interface: "UserInterface"):
    logger.debug("Touching user %s", user_interface.user_id)
    user = (
        user_interface._session.query(User).filter_by(id=user_interface.user_id).first()
    )
    user.touch()


UserScopeWrapper = DatabaseScopeProvider(
    "users",
    precommit_method=touch_user,
    postcommit_method=lambda user_interface: asyncio_triggers.trigger_update_event(
        "user", user_interface.user_id
    ),
)
db_scoped = UserScopeWrapper.db_scoped


class UserInterface:
    """
    Class to query / interact with Users
    """

    def __init__(self, user_id: Union[UUID, str], session=None):
        if isinstance(user_id, str):
            self.user_id = UUID(user_id)
        elif isinstance(user_id, UUID):
            self.user_id = user_id
        else:
            raise TypeError

        self._session: SQLAlchemySession = session
        self._session_users = 0
        self._session_is_external = bool(session)
        self._db_scoped_altering = False

    def __enter__(self):
        from . import database

        # Create a session here instead of letting db_scoped do it. This will
        # mean that we have ownership of it here, so db_scoped will leave it
        # alone and let us manage its lifecycle.
        if self._session:
            self._session.close()

        self._session = database.Session()

        return self

    def __exit__(self, *args):
        if not self._session_is_external:
            if self._session:
                logger.debug(
                    "UserInterface %s closing session",
                    hash(self),
                )
                self._session.close()

    def get_session(self):
        return self._session

    @db_scoped
    def _make_user(self) -> User:
        """
        Make a new user
        """
        user = User(
            id=self.user_id,
        )
        self._session.add(user)
        self._session.commit()

        logger.info("Making new user {}".format(user.id))

        return user

    @db_scoped
    def get_user(self) -> User:
        "Return an ORM object for this user, making a new one if required"

        with make_user_lock:
            user = self._session.query(User).get(self.user_id)

            if not user:
                user = self._make_user()

        return user

    @db_scoped
    def hit(self, num=1) -> User:
        "Take num hitpoints from the user, leaving them on as least zero"
        u: User = self.get_user()
        initial_HP = u.hit_points

        u.hit_points -= num

        if u.hit_points < 0:
            u.hit_points = 0

        # Record the time of death if this shot killed the user. Note that we
        # check if this was the death blow, since the user could be shot more
        # than once
        if initial_HP > 0 and u.hit_points <= 0:
            u.time_of_death = time.time() + TIME_KNOCKED_OUT

    @db_scoped
    def award_HP(self, num=1) -> User:
        "Give health to the user"
        self.get_user().hit_points += num

    @db_scoped
    def set_HP(self, num) -> User:
        """
        Set the user's health, wiping any death state
        """
        u: User = self.get_user()
        u.hit_points = num
        u.time_of_death = 0

    @db_scoped
    def award_ammo(self, num=1) -> User:
        "Give ammo to the user"
        self.get_user().num_bullets += num

    @db_scoped
    def get_user_model(self) -> UserModel:
        u = self.get_user()
        return UserModel.from_orm(u) if u else None

    @db_scoped
    def get_team_id(self) -> UUID:
        return self.get_user().team_id

    @db_scoped
    def get_team_model(self) -> UserModel:
        team = self.get_user().team
        return TeamModel.from_orm(team) if team else None

    @db_scoped
    def _get_item_from_database(self, item_id: int) -> Item:
        return self._session.query(Item).filter_by(id=item_id).first()

    @db_scoped
    def set_name(self, new_name: str):
        self.get_user().name = new_name

    @db_scoped
    def set_weapon_data(self, damage: int, fire_delay: float):
        u = self.get_user()
        u.shot_timeout = fire_delay
        u.shot_damage = damage

    @db_scoped
    def join_team(self, team_id: UUID):
        from .admin_interface import AdminInterface

        team = self._session.query(Team).filter_by(id=team_id).first()

        if not team:
            game_ids = self._session.query(Game.id).filter_by().all()
            if len(game_ids) == 0:
                game_id = AdminInterface().create_game()
                logger.warning(
                    "Team does not exist and no games are running - creating it and making a new game (%s)",
                    game_id,
                )
            elif len(game_ids) > 1:
                logger.error(
                    "Cannot assign team to game automatically since multiple teams exist"
                )
                raise HTTPException(
                    405,
                    "Cannot join team - team does not exist and multiple games are running",
                )
            else:
                game_id = game_ids[0]
                logger.warning(
                    "Team does not exist - creating it and adding it to the only game (%s)",
                    game_id,
                )

            logger.info("Creating new team with uuid=%s", team_id)
            team = Team(id=team_id, game_id=game_id)
            self._session.add(team)

        team.users.append(self.get_user())

    @db_scoped
    def submit_shot(self, image_base64: str):
        user: User = self.get_user()
        team = user.team

        if not team:
            raise HTTPException(405, "User is not in a team yet")

        game = team.game

        if user.hit_points <= 0:
            raise HTTPException(403, "User is dead")

        if user.num_bullets <= 0:
            raise HTTPException(403, "User has no ammo")

        logger.info("User %s submitting shot to game %s", user.id, game.id)

        shot_entry = Shot(
            user=user,
            team=team,
            game=game,
            image_base64=image_base64,
            shot_damage=user.shot_damage,
        )
        self._session.add(shot_entry)

        user.num_bullets -= 1

        # Save to folder
        save_image(base64_image=image_base64, name=user.name)

    @db_scoped
    def collect_item(self, encoded_item: str) -> None:
        """Add the scanned item into a user's inventory"""

        item = ItemModel.from_base64(encoded_item)

        item_validation_error = item.validate_signature()
        if item_validation_error:
            raise HTTPException(
                404, f"The scanned item is invalid - error {item_validation_error}"
            )

        user: User = self.get_user()

        if user.team is None:
            raise HTTPException(
                403,
                "Cannot collect item, you are not in a game. How did you even get here?",
            )

        item_from_db = self._get_item_from_database(item.id)

        already_collected = False

        if item_from_db:
            if item.collected_only_once:
                already_collected = True
            else:
                if item.collected_as_team:
                    team_ids = [u.team_id for u in item_from_db.users]
                    if user.team_id in team_ids:
                        already_collected = True
                else:
                    if user in item_from_db.users:
                        already_collected = True

        if already_collected:
            raise HTTPException(403, "Item has already been collected")

        try:
            do_item_actions(self, item)
        except RuntimeError as e:
            raise HTTPException(403, str(e))

        if item_from_db:
            user.items.append(item_from_db)
        else:
            user.items.append(
                Item(
                    id=item.id,
                    item_type=item.itype,
                    data=item.data_as_json(),
                    game=user.team.game,
                )
            )

    @db_scoped
    def get_messages(
        self, num, private=False, newest_first=True
    ) -> List[Tuple[str, str]]:
        """
        Get ticker messages for this user

        Args:
            num (int): Number of messages to get
            private (bool, optional): If True, only get messages that are private for this user. Defaults to False.
            newest_first (bool, optional): If True, get the newest messages first. Defaults to True.

        Returns:
            List[Tuple[str,str]]: A list of messages, each as a tuple of (type, message)
        """
        user = self.get_user()

        if not user.team:
            return []

        return Ticker(
            game_id=user.team.game.id,
            session=self.get_session(),
            user_id=self.user_id if private else None,
        ).get_messages(num_messages=num, newest_first=newest_first)

    def generate_updates(self, timeout=None):
        """
        An async generator that yields None every time an update is available
        for this user

        Note that this does not hold a database session open, so it can be used
        in parallel with other database operations

        Args:
            timeout (int, optional): Maximum number of seconds to wait for an
            update. Defaults to no timeout.
        """

        with self:
            game_id = self.get_user().team_id

        if game_id is None:
            raise ValueError("User is not in a game")

        ticker = Ticker(
            game_id=game_id,
            user_id=self.user_id,
        )

        return ticker.generate_updates(timeout=timeout)

    @db_scoped
    def clear_unchecked_shots(self):
        """
        Mark all unchecked shots for this user as checked and refund all bullets
        """

        u = self.get_user()
        unchecked_shots = (
            self._session.query(Shot)
            .filter_by(user_id=self.user_id, team_id=u.team_id, checked=False)
            .all()
        )

        bullet_refunds = 0
        for shot in unchecked_shots:
            shot.checked = True
            bullet_refunds += 1

        self.award_ammo(bullet_refunds)

    def record_location(self, latitute: float, longitude: float):
        """
        Record the location of the user

        This method should be quick and _does not_ prompt a user update event
        """
        # Make our own session, detached from the usual machinery to ensure no update events
        with session_scope() as session:
            user = session.query(User).get(self.user_id)
            user.latitude = latitute
            user.longitude = longitude

    async def generate_updates(self, timeout=None):
        """
        A generator that yields None every time an update is available for this
        user, or at most after timeout seconds

        Does not use the database.
        """
        while True:
            # Lookup / make an event for this user and subscribe to it
            event = get_trigger_event("user", self.user_id)

            try:
                logger.info("Subscribing to event %s for user %s", event, self.user_id)
                await asyncio.wait_for(event.wait(), timeout=timeout)
                logger.info(f"Event received for user {self.user_id}")
                yield
            except asyncio.TimeoutError:
                logger.info(f"Event timeout for user {self.user_id}")
                yield
