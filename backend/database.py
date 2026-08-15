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


def add_missing_columns(engine):
    """
    Poor man's migrations: add any columns that the ORM models define but the
    database lacks.

    There is no Alembic here - in dev the database is simply reset after a
    model change. Production data survives deploys though, so a newly added
    column would otherwise break every SELECT on its table (e.g.
    games.ai_shot_review_enabled did exactly that to the whole admin panel).
    New tables are handled by the create_all() call in load(); this handles
    new columns on existing tables.
    """
    import sqlalchemy as sa
    from sqlalchemy.schema import CreateColumn

    from .model import Base

    inspector = sa.inspect(engine)

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue

            existing = {col["name"] for col in inspector.get_columns(table.name)}

            for column in table.columns:
                if column.name in existing:
                    continue

                ddl = CreateColumn(column).compile(dialect=engine.dialect).string

                # NOT NULL columns can only be added to a non-empty table with
                # a default, so render the model's Python-side default (if it
                # is a plain scalar) as a server-side DEFAULT clause
                default = getattr(column.default, "arg", None)
                if default is not None and not callable(default):
                    literal = sa.literal(default).compile(
                        dialect=engine.dialect,
                        compile_kwargs={"literal_binds": True},
                    )
                    ddl += f" DEFAULT {literal}"

                logging.getLogger(__name__).warning(
                    "Adding missing database column %s.%s", table.name, ddl
                )
                conn.execute(sa.text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))


def load():
    """
    Set up a database connection to be used from now on
    """
    from sqlalchemy_utils import database_exists

    from .model import Base
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

            session_counter -= 1
            logger.debug(
                "Garbage collecting session hash %d (%d exist)",
                session_hash,
                session_counter,
            )

        weakref.finalize(session, log_close)

        return session

    Session = get_wrapped_session

    if not database_exists(engine.url) or (
        "RESET_DATABASE" in os.environ and bool(os.environ["RESET_DATABASE"])
    ):
        reset_database(engine=engine)
    else:
        # Bring an existing database up to date with the models: create any
        # new tables, then add any new columns to existing tables
        Base.metadata.create_all(bind=engine)
        add_missing_columns(engine)


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
