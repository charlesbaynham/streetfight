import asyncio
import logging
from functools import wraps
from typing import Callable
from typing import Dict

from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


class DatabaseScopeProvider:
    """
    This object provides a wrapper for class methods that access a database
    through an SQLAlchemy session and need to perform an action when the session
    is closed.

    This wrapper creates two class variables on the class whose methods are
    wrapped: `_session` (which is shared between all instances of this wrapper
    and should be used by class code to access the database), and
    `_database_scope_data` which is private for this class.

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

    def __init__(
        self,
        name: str,
        precommit_method: Callable = lambda _: None,
        postcommit_method: Callable = lambda _: None,
    ) -> None:
        self.name = name
        self.update_events: Dict[int, asyncio.Event] = {}
        self.precommit_method = precommit_method
        self.postcommit_method = postcommit_method

    @staticmethod
    def session_is_dirty(session: Session):
        return bool(session.dirty or session.new or session.deleted)

    def db_scoped(self_outer, func: Callable):

        from . import database

        @wraps(func)
        def f(self, *args, **kwargs):
            if not hasattr(self, "_database_scope_data"):
                self._database_scope_data = dict()
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