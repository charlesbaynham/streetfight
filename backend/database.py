import logging
import os
import time
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .dotenv import load_env_vars

load_env_vars()

engine = None
Session = None


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
    Session = sessionmaker(bind=engine)

    

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
