"""Where the test suite's database lives.

One module rather than a fixture because ``backend.database`` calls ``load()``
at import time, which is *before* any fixture runs -- so the environment has
to be right by then. ``tests/conftest.py`` calls this at its own top, ahead of
the import of ``shared_fixtures``.

Under pytest-xdist each worker gets its own file. They have to: the
``db_session`` fixture rebuilds the schema with ``drop_all`` between tests, so
two workers sharing one SQLite file would drop each other's tables halfway
through a test.
"""

import os
from pathlib import Path

#: Set this to keep the suite off the testing database entirely (the live
#: schema upgrade test points the engine at a snapshot of its own).
IGNORE_ENV = "IGNORE_TESTING_DB"


def worker_slug() -> str:
    """``""`` under a plain run, ``"-gw3"`` for xdist's fourth worker."""
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    return f"-{worker}" if worker else ""


def testing_db_path() -> Path:
    return Path(__file__, "..", "..", f"testing{worker_slug()}.db").resolve()


def testing_db_url() -> str:
    return f"sqlite:///{testing_db_path()}"


def set_testing_db_url() -> None:
    """Point DATABASE_URL at this worker's own database, unless told not to."""
    if IGNORE_ENV not in os.environ:
        os.environ["DATABASE_URL"] = testing_db_url()
