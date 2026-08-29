import os
from uuid import uuid4 as uuid

from backend.model import Game
from backend.model import User


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
