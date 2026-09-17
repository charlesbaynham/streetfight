import os
import pathlib
import re
import sqlite3
from uuid import UUID
from uuid import uuid4 as uuid

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.database import add_missing_columns
from backend.model import APPEALS_PER_GAME
from backend.model import Base
from backend.model import Game
from backend.model import Item
from backend.model import ItemType
from backend.model import RevokedBatch
from backend.model import Shot
from backend.model import Team
from backend.model import TickerEntry
from backend.model import User
from backend.model import UserAlias


def test_db_init(db_session):
    assert len(db_session.query(Game).all()) == 0
    assert len(db_session.query(User).all()) == 0


def test_storage(db_session):
    id = uuid()
    db_session.add(User(id=id, name="Hello"))
    db_session.commit()

    assert db_session.query(User.name).first()[0] == "Hello"


def test_importing_the_app_with_a_fresh_database_and_debug_entries_wanted(tmp_path):
    """A fresh database plus MAKE_DEBUG_ENTRIES must not deadlock the imports.

    `database.load()` runs while `backend.database` is being imported, and on a
    fresh database it resets the schema. Building the sample game there too
    would need AdminInterface -- whose own import is what pulled `database` in
    -- so it was a circular import that only appeared on a database that did
    not exist yet, which is to say: never locally, always in CI. Hence a
    subprocess: the bug lives in module import, so nothing already imported
    into this interpreter can see it.
    """
    import subprocess
    import sys

    env = {
        "PATH": os.environ["PATH"],
        "DATABASE_URL": f"sqlite:///{tmp_path / 'fresh.db'}",
        "MAKE_DEBUG_ENTRIES": "true",
        "SECRET_KEY": "not-so-secret",
    }
    done = subprocess.run(
        [sys.executable, "-c", "import backend.main"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert done.returncode == 0, done.stderr[-2000:]


class TestLiveSchemaUpgrade:
    """The gate on a change that the live database cannot take.

    There are no migrations. A deploy brings the live schema up to date by
    running `create_all()` and then `add_missing_columns()` over it
    (`database.load()`), which handles exactly one shape of change: a new
    table, a new nullable column, or a new column with a plain scalar default.
    A rename, a drop, a type change or a `NOT NULL` column with no scalar
    default is not applied, and the first request afterwards fails on a column
    the models believe in and the database has never heard of.

    So: build a copy of the live schema from the committed snapshot, upgrade it
    the way a deploy would, and then use it. `tests/live_schema/refresh.py`
    rebuilds the snapshot when live moves; point SNAPSHOT at the new file in
    the same commit.

    Knowingly out of scope: an index added to an existing table. `create_all()`
    skips a table that exists, so a new index does not reach live either -- but
    it costs speed rather than correctness, and nothing here would tell the two
    apart.
    """

    SNAPSHOT = "2026-09-16_b50fe89.sql"

    # A game already in the live database when the deploy happens. Written
    # through the snapshot's own reflected columns rather than through the
    # models, because live wrote it before the models moved -- and written at
    # all because an empty table hides the failure that matters: a NOT NULL
    # column with no default is only a problem once there are rows to fill in.
    SEEDED_GAME_ID = UUID(bytes=b"g" * 16)
    SEEDED_TICKER_TAG = 7

    @staticmethod
    def _engine_from_snapshot(tmp_path, name):
        snapshot = (
            pathlib.Path(__file__).parent
            / "live_schema"
            / TestLiveSchemaUpgrade.SNAPSHOT
        )
        path = tmp_path / name
        with sqlite3.connect(path) as conn:
            conn.executescript(snapshot.read_text())

        return sa.create_engine(f"sqlite:///{path}")

    @staticmethod
    def _seed(engine):
        placeholders = {sa.Boolean: False, sa.Integer: 0, sa.Float: 0.0}

        metadata = sa.MetaData()
        metadata.reflect(bind=engine, only=["games"])
        games = metadata.tables["games"]

        row = {
            "id": TestLiveSchemaUpgrade.SEEDED_GAME_ID.bytes,
            "active": True,
            "ticker_update_tag": TestLiveSchemaUpgrade.SEEDED_TICKER_TAG,
        }
        for column in games.columns:
            if column.name in row or column.nullable:
                continue
            for kind, placeholder in placeholders.items():
                if isinstance(column.type, kind):
                    row[column.name] = placeholder
                    break
            else:
                row[column.name] = ""

        # Bound through sa.text(), not games.insert(): the reflected BINARY(16)
        # of a UUID primary key has no idea it is a UUIDType and would try to
        # make a number of the bytes.
        columns = ", ".join(row)
        values = ", ".join(f":{name}" for name in row)
        with engine.begin() as conn:
            conn.execute(
                sa.text(f"INSERT INTO games ({columns}) VALUES ({values})"), row
            )

    @staticmethod
    def _upgrade(engine):
        """What `database.load()` does to an existing database on deploy."""
        Base.metadata.create_all(bind=engine)
        add_missing_columns(engine)

    @staticmethod
    def _reflect(engine):
        inspector = sa.inspect(engine)
        return {
            table: {
                column["name"]: (str(column["type"]), column["nullable"])
                for column in inspector.get_columns(table)
            }
            for table in inspector.get_table_names()
        }

    @staticmethod
    def _same_shape(upgraded, wanted) -> bool:
        """Whether a column on the upgraded database is the one the models want.

        Exact equality, with one exemption: a **wider** VARCHAR. SQLite records
        a column's declared type but never enforces a string length, and
        SQLAlchemy re-derives an ``Enum`` column's length from the longest
        member name - so adding a member to ``ItemType`` widens the type on a
        fresh database while the live one keeps the narrower one, and stores
        the longer string quite happily either way. That is rule 2's "a new
        ``ItemType`` member needs nothing at all". A *narrowing*, a change of
        nullability, or any other type change is still a difference: those are
        the ones that cannot be deployed.
        """
        if upgraded == wanted:
            return True

        (live_type, live_null), (fresh_type, fresh_null) = upgraded, wanted
        if live_null != fresh_null:
            return False

        live = re.fullmatch(r"VARCHAR\((\d+)\)", live_type)
        fresh = re.fullmatch(r"VARCHAR\((\d+)\)", fresh_type)

        return bool(live and fresh and int(fresh.group(1)) > int(live.group(1)))

    def test_only_a_widened_varchar_is_exempt(self):
        """The exemption is narrow on purpose: it must not hide a narrowing, a
        change of nullability, or a different type altogether."""
        assert self._same_shape(("VARCHAR(7)", True), ("VARCHAR(14)", True))

        assert not self._same_shape(("VARCHAR(14)", True), ("VARCHAR(7)", True))
        assert not self._same_shape(("VARCHAR(7)", True), ("VARCHAR(14)", False))
        assert not self._same_shape(("VARCHAR(7)", True), ("INTEGER", True))

    def test_upgraded_live_schema_matches_the_models(self, tmp_path):
        """The upgraded database must end up the same shape as a fresh one.

        A column the models dropped or renamed is still sitting in the upgraded
        database and missing from the fresh one; a column whose type or
        nullability changed differs between the two. Either way the deploy
        silently did not do what the developer thought it did.
        """
        live = self._engine_from_snapshot(tmp_path, "live.db")
        self._seed(live)
        self._upgrade(live)

        fresh = sa.create_engine(f"sqlite:///{tmp_path}/fresh.db")
        self._upgrade(fresh)

        upgraded_schema = self._reflect(live)
        fresh_schema = self._reflect(fresh)

        assert set(upgraded_schema) == set(fresh_schema)

        for table in sorted(fresh_schema):
            upgraded = upgraded_schema[table]
            wanted = fresh_schema[table]

            stale = sorted(set(upgraded) - set(wanted))
            assert not stale, (
                f"{table}: the models no longer define {stale}, but the live"
                " database still has them. A rename or a drop cannot be"
                " deployed -- there are no migrations."
            )

            missing = sorted(set(wanted) - set(upgraded))
            assert not missing, (
                f"{table}: {missing} did not reach the upgraded database."
                " add_missing_columns only renders a plain scalar default."
            )

            differing = sorted(
                name
                for name in wanted
                if not self._same_shape(upgraded[name], wanted[name])
            )
            assert not differing, (
                f"{table}: {differing} have a different type or nullability on"
                " the upgraded database than on a fresh one. A column cannot be"
                " altered in place -- there are no migrations."
            )

    def test_every_model_can_be_written_and_read_on_the_upgraded_schema(self, tmp_path):
        """One row through every mapped class, plus the association table.

        The schema comparison above says the columns line up; this says the ORM
        can actually use them -- which is what a deployed server does on its
        first request, and the only thing that catches a NOT NULL column whose
        default the database was never told about.
        """
        engine = self._engine_from_snapshot(tmp_path, "live.db")
        self._seed(engine)
        self._upgrade(engine)

        written = {
            Game,
            Shot,
            Team,
            User,
            UserAlias,
            TickerEntry,
            Item,
            RevokedBatch,
        }
        mapped = {mapper.class_ for mapper in Base.registry.mappers}
        assert mapped == written, (
            "A mapped class with no row here is a class this gate does not"
            f" cover: {sorted(cls.__name__ for cls in mapped ^ written)}"
        )

        game_id, team_id, user_id, stray_id, shot_id = (uuid() for _ in range(5))

        with sessionmaker(bind=engine)() as session:
            user = User(id=user_id, name="Pat", game_id=game_id, team_id=team_id)
            user.items.append(Item(id=uuid(), item_type=ItemType.AMMO, data='{"n": 2}'))
            session.add_all(
                [
                    Game(id=game_id, active=True),
                    Team(id=team_id, name="Reds", game_id=game_id),
                    user,
                    User(id=stray_id, name="Pat's other phone", game_id=game_id),
                    Shot(
                        id=shot_id,
                        game_id=game_id,
                        user_id=user_id,
                        team_id=team_id,
                        image_base64="data:image/jpeg;base64,AAAA",
                    ),
                ]
            )
            session.flush()
            session.add(UserAlias(session_id=stray_id, user_id=user_id))
            session.add(
                TickerEntry(
                    game_id=game_id,
                    highlight_user_id=user_id,
                    shot_id=shot_id,
                    message="Pat shot somebody",
                )
            )
            session.add(RevokedBatch(batch="sandbox"))
            session.commit()

        with sessionmaker(bind=engine)() as session:
            # The row live already had, still readable -- and every column the
            # models require now filled in, whether or not it existed when the
            # row was written. A new NOT NULL column whose default the database
            # was never told about arrives here as a None.
            existing = session.get(Game, self.SEEDED_GAME_ID)
            assert existing.active is True
            assert existing.ticker_update_tag == self.SEEDED_TICKER_TAG
            for column in Game.__table__.columns:
                if column.nullable:
                    continue
                assert getattr(existing, column.name) is not None, (
                    f"games.{column.name} is NOT NULL in the models but null on"
                    " a row that predates it"
                )

            assert session.get(Game, game_id).teams[0].name == "Reds"
            read_user = session.get(User, user_id)
            assert read_user.team.name == "Reds"
            assert read_user.appeals_remaining == APPEALS_PER_GAME
            assert [i.item_type for i in read_user.items] == [ItemType.AMMO]
            assert session.get(Shot, shot_id).checked is False
            assert session.get(UserAlias, stray_id).user_id == user_id
            assert session.query(TickerEntry).one().message == "Pat shot somebody"
            assert session.get(RevokedBatch, "sandbox").revoked_at is not None
