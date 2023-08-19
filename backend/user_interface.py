import asyncio
import logging
from functools import wraps
from typing import Callable
from typing import Dict
from uuid import UUID
from uuid import uuid4 as get_uuid

from fastapi import HTTPException
from sqlalchemy.ext import baked

from .model import Game
from .model import Shot
from .model import User
from .model import UserModel


logger = logging.getLogger(__name__)
GET_HASH_TIMEOUT = 20

update_events: Dict[int, asyncio.Event] = {}


# A bakery for SQLAlchemy queries
bakery = baked.bakery()


class UserInterface:
    """
    Class to query / interact with Users
    """

    def __init__(self, user_id: str, session=None):
        self.user_id = user_id
        self._session = session
        self._session_users = 0
        self._session_is_external = bool(session)
        self._db_scoped_altering = False

    def _check_for_dirty_session(self):
        if self._session.dirty or self._session.new or self._session.deleted:
            self._session_modified = True
            logger.debug("Marking changes as present")

    def db_scoped(func: Callable):
        """
        Start a session and store it in self._session

        When a @db_scoped method returns, commit the session

        Close the session once all @db_scoped methods are finished (if the session is not external)

        If any of the decorated functions altered the database state, also release an asyncio
        event marking this user as having been updated
        """
        from . import database

        @wraps(func)
        def f(self, *args, **kwargs):
            if not self._session:
                self._session = database.Session()
            if self._session_users == 0:
                self._session_modified = False

            try:
                self._session_users += 1
                out = func(self, *args, **kwargs)

                # If this commit will alter the database, set the modified flag
                self._check_for_dirty_session()

                return out
            except Exception as e:
                logging.exception("Exception encountered! Rolling back DB")
                self._session.rollback()
                raise e
            finally:
                if self._session_users == 1 and self._session_modified:
                    # If any of the functions altered the game state, fire
                    # the corresponding updates events if they are present
                    # in the global dict And mark the game as altered in the
                    # database.
                    #
                    # Check this before we reduce session_users to 0, else
                    # calling get_game will reopen a new session before the
                    # old one is closed.
                    logger.debug("Touching game")
                    self.get_user().touch()

                self._session_users -= 1

                if self._session_users == 0:
                    logger.debug("Committing session")
                    self._session.commit()

                    if self._session_modified:
                        logger.debug("...and triggering updates")
                        trigger_update_event(self.user_id)

        return f

    @db_scoped
    def _make_user(self) -> User:
        """
        Make a new user
        """
        user = User(
            id=self.user_id,
        )
        self._session.add(user)

        logger.info("Making new user {}".format(user.id))

        return user

    @db_scoped
    def get_user(self) -> User:
        "Return an ORM object for this user, making a new one if required"
        user = self._session.query(User).filter_by(id=self.user_id).first()

        if not user:
            user = self._make_user()

        return user

    @db_scoped
    def get_user_model(self) -> UserModel:
        u = self.get_user()
        return UserModel.from_orm(u) if u else None

    @db_scoped
    def join_game(self, game_id: UUID):
        game = self._session.query(Game).filter_by(id=game_id).first()

        if not game:
            logger.info("Creating new game with uuid=%s", game_id)
            game = Game(id=game_id)
            self._session.add(game)

        game.users.append(self.get_user())

    @db_scoped
    def submit_shot(self, image_base64: str):
        user = self.get_user()
        game = user.game

        if not game:
            raise HTTPException(405, "User is not in a game yet")

        shot_entry = Shot(user=user, game=game, image_base64=image_base64)
        self._session.add(shot_entry)

    @db_scoped
    def get_hash_now(self):
        user = self.get_user()

        update_tag = user.game.update_tag

        ret = update_tag[0] if update_tag else 0
        logger.info(f"Current hash {ret}, user {self.user_id}")
        return ret

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
            return current_hash

        # Otherwise, lookup / make an event and subscribe to it
        if self.user_id not in update_events:
            update_events[self.user_id] = asyncio.Event()
            logger.info("Made new event for game %s", self.user_id)
        else:
            logger.info("Subscribing to event for %s", self.user_id)

        try:
            event = update_events[self.user_id]
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.info(f"Event received for game {self.user_id}")
            return self.get_hash_now()
        except asyncio.TimeoutError:
            return current_hash


def trigger_update_event(user_id: int):
    logger.info(f"Triggering updates for user {user_id}")
    global update_events
    if user_id in update_events:
        update_events[user_id].set()
        del update_events[user_id]
