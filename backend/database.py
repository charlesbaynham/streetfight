import logging
import os
import time
import weakref
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .dotenv import load_env_vars

load_env_vars()

engine = None
Session = None
session_counter = 0


logger = logging.getLogger("sqltimings")
if os.environ.get("DEBUG_DATABASE"):
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.WARNING)


# if the sqltimings logger is enabled for debug, add hooks to the database engine
@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if logger.isEnabledFor(logging.DEBUG):
        conn.info.setdefault("query_start_time", []).append(time.time())
        logger.debug("Start query: %s", statement)


@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if logger.isEnabledFor(logging.DEBUG):
        total = time.time() - conn.info["query_start_time"].pop(-1)
        logger.debug("Query complete in %fs", total)


def load():
    """
    Set up a database connection to be used from now on
    """
    from sqlalchemy_utils import database_exists
    from .reset_db import reset_database

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "Env var DATABASE_URL not set. If you are running for "
            "development, copy the .env.dev file to .env"
        )

    global engine
    global Session

    engine = create_engine(db_url)
    RawSession = sessionmaker(bind=engine)

    def get_wrapped_session(*args, **kwargs):
        session = RawSession(*args, **kwargs)

        global session_counter
        session_counter += 1

        session_hash = hash(session)

        logger.debug(
            "Creating session hash %d (%d exist)", session_hash, session_counter
        )

        def log_close():
            global session_counter

            logger.debug(
                "Garbage collecting session hash %d (%d exist)",
                session_hash,
                session_counter,
            )
            session_counter -= 1

        weakref.finalize(session, log_close)

        return session

    Session = get_wrapped_session

    if not database_exists(engine.url):
        reset_database(engine=engine)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


load()
