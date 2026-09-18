import pytest

# Point every worker at its own database *before* anything imports
# backend.database, which calls load() at import time. Two things depend on
# this happening here rather than in a fixture: without it the import-time
# load() reaches for .env's DATABASE_URL and creates the developer's own
# data.db, and under pytest-xdist every worker would then share one SQLite
# file -- which the db_session fixture drop_all()s between tests, so workers
# would delete each other's tables mid-test.
from .db_url import set_testing_db_url  # noqa: E402
from .quiet_logs import quieten_logs  # noqa: E402

set_testing_db_url()

# .env.dev's DEBUG_DATABASE/LOG_LEVEL are a developer's settings, and cost the
# suite more than everything else in it put together. See tests/quiet_logs.py.
quieten_logs()

# Shared fixtures:
from .shared_fixtures import *  # noqa


def pytest_addoption(parser):
    parser.addoption(
        "--runselenium", action="store_true", default=False, help="run slow tests"
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "selenium: marks tests as requiring selenium (select with '-m selenium')",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runselenium"):
        # --runslow given in cli: do not skip slow tests
        return
    skip_selenium = pytest.mark.skip(reason="need --runselenium option to run")
    for item in items:
        if "selenium" in item.keywords:
            item.add_marker(skip_selenium)
