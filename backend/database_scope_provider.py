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

    It also creates a member on the `_session` object called `__owner` which is
    set to the hash of `self` if the session was created by this class. This
    class will only close sessions that were created by the wrapped object (but
    it will still commit them).

    1. For the first db_scoped method, starts a session and stores it in
       self._session

    2. When the last @db_scoped method returns, commit and close the session

    3. If any of the decorated functions altered the database state,
        a. Call `precommit_method(self)` before the db commit
        b. Call `postcommit_method(self)` after the db close

    4. Regardless of whether the database state was altered, call
       `exit_method(self)`

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
        exit_method: Callable = lambda _: None,
    ) -> None:
        self.name = name
        self.update_events: Dict[int, asyncio.Event] = {}
        self.precommit_method = precommit_method
        self.postcommit_method = postcommit_method
        self.exit_method = exit_method

    @staticmethod
    def session_is_dirty(session: Session):
        o = bool(session.dirty or session.new or session.deleted)
        return o

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
                self._session.__owner = hash(self)

            # If we're the entrypoint to a db_scoped session, reset the
            # session_modified flag. Note that we can't rely on the
            # initialisation above because the user may well reuse objects with
            # db_scoped methods and call them more than once.
            if wrapper_data["session_users"] == 0:
                wrapper_data["session_modified"] = False

            wrapper_data["session_users"] += 1

            try:
                out = func(self, *args, **kwargs)
                # If this commit will alter the database, set the modified flag
                dirty = self_outer.session_is_dirty(self._session)
                logger.debug(
                    "(DSP %s) session_is_dirty=%s, session_modified=%s",
                    self_outer.name,
                    dirty,
                    wrapper_data["session_modified"],
                )
                if dirty:
                    logger.debug(
                        "(DSP %s) Setting session_modified flag",
                        self_outer.name,
                    )
                    wrapper_data["session_modified"] = True

                return out
            except Exception as e:
                logging.exception("Exception encountered! Rolling back DB")
                self._session.rollback()
                raise e
            finally:
                if wrapper_data["session_users"] == 1:
                    logger.debug("(DSP %s) Last user of scoped call", self_outer.name)

                if (
                    wrapper_data["session_users"] == 1
                    and wrapper_data["session_modified"]
                ):
                    logger.debug("(DSP %s) Calling precommit_method", self_outer.name)
                    self_outer.precommit_method(self)

                wrapper_data["session_users"] -= 1

                if wrapper_data["session_users"] == 0:
                    logger.debug("(DSP %s) Committing session", self_outer.name)
                    self._session.commit()

                    try:
                        if self._session.__owner == hash(self):
                            logger.debug("(DSP %s) Closing session", self_outer.name)
                            self._session.close()
                        else:
                            logger.debug(
                                "(DSP %s) Not closing session, it was made by another object",
                                self_outer.name,
                            )
                    except AttributeError:
                        logger.debug(
                            "(DSP %s) Not closing session, it was made outside this wrapper",
                            self_outer.name,
                        )

                    if wrapper_data["session_modified"]:
                        logger.debug(
                            "(DSP %s) Calling postcommit_method", self_outer.name
                        )
                        self_outer.postcommit_method(self)

                    logger.debug("(DSP %s) Calling exit_method", self_outer.name)
                    self_outer.exit_method(self)

        return f
