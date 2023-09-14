import asyncio
import logging
from functools import wraps
from threading import RLock
from typing import Callable
from typing import Dict
from typing import Union
from uuid import UUID
from uuid import uuid4 as get_uuid

from fastapi import HTTPException
from sqlalchemy.ext import baked
from sqlalchemy.orm import Session

from .items import DecodedItem
from .model import Game
from .model import Item
from .model import Shot
from .model import Team
from .model import User
from .model import UserModel

logger = logging.getLogger(__name__)
GET_HASH_TIMEOUT = 20

update_events: Dict[int, asyncio.Event] = {}

make_user_lock = RLock()


class DatabaseScopeProvider:
    def __init__(
        self,
        name: str,
        precommit_method: Callable = lambda _: None,
        postcommit_method: Callable = lambda _: None,
    ) -> None:
        self.name = name
        self.update_events: Dict[int, asyncio.Event] = {}
        self.thread_lock = RLock()
        self.precommit_method = precommit_method
        self.precommit_method = postcommit_method

    @staticmethod
    def session_is_dirty(session: Session):
        return session.dirty or session.new or session.deleted

    def db_scoped(self_outer, func: Callable):
        """
        Wrapper for class methods that access a database through an SQLAlchemy
        session and need to perform an action when the session is closed.

        This wrapper uses two class variables: `_session` (which is shared between
        all instances of this wrapper and should be used by class code to access
        the database), and `_database_scope_data` which is private for this
        class.

        1. For the first db_scoped method, starts a session and stores it in
           self._session

        2. When the last @db_scoped method returns, commit the session

        3. If any of the decorated functions altered the database state,
            a. Call `precommit_method(self)` before the db commit
            b. Call `postcommit_method(self)` after the db commit

        Example usage:

        @db_scoped("users", lambda self: self.get_user().touch()) def
        do_something(self):
            # do something with users, probably using self._session
        """
        from . import database

        @wraps(func)
        def f(self, *args, **kwargs):
            if not hasattr(self, "_database_scope_data"):
                self._database_scope_data = {}
            try:
                wrapper_data = self._database_scope_data[self_outer.name]
            except KeyError:
                self._database_scope_data[self_outer.name] = {
                    "session_users": 0,
                    "session_modified": False,
                }
                wrapper_data = self._database_scope_data[self_outer.name]

            if not self._session:
                self._session = database.Session()
            if wrapper_data["session_users"] == 0:
                wrapper_data["session_modified"] = False

            try:
                wrapper_data["session_users"] += 1
                out = func(self, *args, **kwargs)
                # If this commit will alter the database, set the modified flag
                wrapper_data["session_modified"] = self_outer.session_is_dirty(
                    self._session
                )

                return out
            except Exception as e:
                logging.exception("Exception encountered! Rolling back DB")
                self._session.rollback()
                raise e
            finally:
                if (
                    wrapper_data["session_users"] == 1
                    and wrapper_data["session_modified"]
                ):
                    logger.debug("Calling precommit_method for %s", self_outer.name)
                    self_outer.precommit_method(self)

                wrapper_data["session_users"] -= 1

                if wrapper_data["session_users"] == 0:
                    logger.debug("Committing session")
                    self._session.commit()

                    if wrapper_data["session_modified"]:
                        logger.debug(
                            "Calling postcommit_method for %s", self_outer.name
                        )
                        self_outer.postcommit_method(self)

        return f


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

        self._session = session
        self._session_users = 0
        self._session_is_external = bool(session)
        self._db_scoped_altering = False

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
            user = self._session.query(User).filter_by(id=self.user_id).first()

            if not user:
                user = self._make_user()

        return user

    @db_scoped
    def kill(self) -> User:
        "Take a hitpoint from the user"
        self.get_user().hit_points -= 1

    @db_scoped
    def award_HP(self, num=1) -> User:
        "Give health to the user"
        self.get_user().hit_points += num

    @db_scoped
    def award_ammo(self, num=1) -> User:
        "Give ammo to the user"
        self.get_user().num_bullets += num

    @db_scoped
    def get_user_model(self) -> UserModel:
        u = self.get_user()
        return UserModel.from_orm(u) if u else None

    @db_scoped
    def _get_item_from_database(self, item_id: int) -> Item:
        return self._session.query(Item).filter_by(id=item_id).first()

    @db_scoped
    def set_name(self, new_name: str):
        self.get_user().name = new_name

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
        user = self.get_user()
        team = user.team

        if not team:
            raise HTTPException(405, "User is not in a team yet")

        game = team.game

        if user.hit_points <= 0:
            raise HTTPException(403, "User is dead")

        if user.num_bullets <= 0:
            raise HTTPException(403, "User has no ammo")

        logger.info("User %s submitting shot to game %s", user.id, game.id)

        shot_entry = Shot(user=user, team=team, game=game, image_base64=image_base64)
        self._session.add(shot_entry)

        user.num_bullets -= 1

        # Save to folder
        f = open("logs/out.txt", "w")
        f.write(image_base64)
        f.close()

    @db_scoped
    def get_hash_now(self):
        user = self.get_user()

        update_tag = user.update_tag

        ret = update_tag if update_tag else 0
        logger.info(f"Current hash {ret}, user {self.user_id}")
        return ret

    @db_scoped
    def collect_item(self, encoded_item: str) -> None:
        """Add the scanned item into a user's inventory"""

        item = DecodedItem.from_base64(encoded_item)

        item_validation_error = item.validate_signature()
        if item_validation_error:
            raise HTTPException(
                402, f"The scanned item is invalid - error {item_validation_error}"
            )

        if self._get_item_from_database(item.id):
            raise HTTPException(403, "Item has already been collected")

        user = self.get_user()

        if user.team is None:
            raise HTTPException(
                403,
                "Cannot collect item, you are not in a game. How did you even get here?",
            )

        if item.itype == "armour":
            if user.hit_points <= 0:
                raise HTTPException(403, "Cannot collect armour, you are dead!")

            self.award_HP(item.data["num"])
        elif item.itype == "medpack":
            if user.hit_points > 0:
                raise HTTPException(403, "Medpacks can only be used on dead players")

            self.award_HP(1 - user.hit_points)
        elif item.itype == "ammo":
            if user.hit_points <= 0:
                raise HTTPException(403, "Cannot collect ammo, you are dead!")

            self.award_ammo(item.data["num"])
        else:
            raise HTTPException(404, "Unknown item type")

        self._session.add(
            Item(
                id=item.id,
                item_type=item.itype,
                data=item.data_as_json(),
                user=user,
                game=user.team.game,
            )
        )

    async def get_hash(self, known_hash=None, timeout=GET_HASH_TIMEOUT) -> int:
        """
        Gets the latest hash of this user

        If known_hash is provided and is the same as the current hash,
        do not return immediately: wait for up to timeout seconds.

        Note that this function is not @db_scoped, but it calls one that is:
        this is to prevent the database being locked while it waits
        """
        current_hash = self.get_hash_now()

        # Return immediately if the hash has changed or if there's no known hash
        if known_hash is None or known_hash != current_hash:
            logger.debug("Out of date hash - returning immediately")
            return current_hash

        # Otherwise, lookup / make an event and subscribe to it
        if self.user_id not in update_events:
            update_events[self.user_id] = asyncio.Event()
            logger.info("Made new event for user %s", self.user_id)

        try:
            event = update_events[self.user_id]
            logger.info("Subscribing to event %s for user %s", event, self.user_id)
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.info(f"Event received for user {self.user_id}")
            return self.get_hash_now()
        except asyncio.TimeoutError:
            logger.info(f"Event timeout for user {self.user_id}")
            return current_hash


def trigger_update_event(user_id: UUID):
    global update_events

    logger.info(f"Triggering updates for user {user_id}")
    logger.debug(f"update_events = %s, user_id=%s", update_events, user_id)

    if user_id in update_events:
        logger.debug("Update event found")
        update_events[user_id].set()
        del update_events[user_id]
    else:
        logger.debug("No update event found")
