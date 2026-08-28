"""
The startup schema sync (backend.database.add_missing_columns) exists because
production keeps its data across deploys and there are no migrations: a column
added to the models (like games.ai_shot_review_enabled) would otherwise break
every SELECT on its table until someone wiped the database.
"""

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.database import add_missing_columns
from backend.model import Base
from backend.model import Game


def make_old_schema_engine(tmp_path):
    """A database built from the current models, then aged: the AI review
    columns dropped and a game row inserted, like a production database from
    before that feature shipped."""
    engine = sa.create_engine(f"sqlite:///{tmp_path}/old.db")
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE games DROP COLUMN ai_shot_review_enabled"))
        conn.execute(sa.text("ALTER TABLE games DROP COLUMN ai_auto_actions_enabled"))
        conn.execute(sa.text("ALTER TABLE games DROP COLUMN ai_escalation_enabled"))
        conn.execute(
            sa.text("ALTER TABLE games DROP COLUMN ai_resolve_everything_enabled")
        )
        conn.execute(sa.text("ALTER TABLE shots DROP COLUMN ai_review_state"))
        conn.execute(sa.text("ALTER TABLE shots DROP COLUMN ai_review"))
        conn.execute(
            sa.text(
                "INSERT INTO games (id, active, ticker_update_tag)"
                " VALUES (:id, :active, :tag)"
            ),
            {"id": b"0" * 16, "active": True, "tag": 1},
        )

    return engine


def test_missing_columns_are_added(tmp_path):
    engine = make_old_schema_engine(tmp_path)

    # The aged database cannot serve the ORM
    with sessionmaker(bind=engine)() as session:
        try:
            session.query(Game).all()
            raise AssertionError("Expected the old schema to fail")
        except sa.exc.OperationalError:
            pass

    add_missing_columns(engine)

    columns = {col["name"] for col in sa.inspect(engine).get_columns("games")}
    assert {
        "ai_shot_review_enabled",
        "ai_auto_actions_enabled",
        "ai_escalation_enabled",
        "ai_resolve_everything_enabled",
    } <= columns
    shot_columns = {col["name"] for col in sa.inspect(engine).get_columns("shots")}
    assert {"ai_review_state", "ai_review"} <= shot_columns

    # The existing row survived and picked up the NOT NULL default
    with sessionmaker(bind=engine)() as session:
        games = session.query(Game).all()
        assert len(games) == 1
        assert games[0].active is True
        assert games[0].ai_shot_review_enabled is False
        assert games[0].ai_auto_actions_enabled is False
        assert games[0].ai_resolve_everything_enabled is False
        # ...including the one whose default is on rather than off
        assert games[0].ai_escalation_enabled is True


def test_sync_is_idempotent(tmp_path):
    engine = make_old_schema_engine(tmp_path)

    add_missing_columns(engine)
    add_missing_columns(engine)

    with sessionmaker(bind=engine)() as session:
        assert len(session.query(Game).all()) == 1
