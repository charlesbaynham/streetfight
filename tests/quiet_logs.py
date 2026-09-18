"""Turn the developer's debug logging off for the test suite.

The suite runs against ``.env.dev`` (CI copies it to ``.env``), which is tuned
for a developer watching a live server: ``LOG_LEVEL=DEBUG`` and
``DEBUG_DATABASE=true``. Under pytest that combination is ruinous:

* ``DEBUG_DATABASE`` puts ``backend.database``'s ``sqltimings`` logger at DEBUG,
  and its ``before_cursor_execute`` / ``after_cursor_execute`` hooks then format
  and emit two records for **every SQL statement** the suite executes -- and
  ``db_session`` rebuilds the whole schema between tests, so most of those
  statements are DDL nobody will ever read.
* ``LOG_LEVEL`` is applied to the *root* logger by ``backend.main``'s
  ``setup_logging()``, which also attaches a ``RotatingFileHandler``. So every
  one of those records is formatted twice over and written to
  ``logs/backend.log`` as well as captured by pytest. A single full run wrote
  over 40 MB there.

Neither is worth anything to a passing test, and pytest's own log capture still
shows a failing one everything it emitted. ``python-dotenv`` does not override
variables that are already set, so setting them here -- before anything imports
``backend`` -- wins over ``.env``.

Set ``STREETFIGHT_TEST_DEBUG_LOGS=1`` to put the old behaviour back when
debugging a test that needs to see its queries.
"""

import logging
import os
from pathlib import Path

from .db_url import worker_slug

DEBUG_LOGS_ENV = "STREETFIGHT_TEST_DEBUG_LOGS"

#: Where the suite sends backend.main's rotating file handler. Out of the
#: developer's own logs/ directory, and one file per xdist worker: doRollover()
#: renames the numbered backups in sequence, so four processes rotating one
#: file race each other into a FileNotFoundError at import time.
TEST_LOG_DIR = Path(__file__, "..", "..", "logs", "tests").resolve()


def debug_logs_requested() -> bool:
    return bool(os.environ.get(DEBUG_LOGS_ENV))


def quieten_logs() -> None:
    os.environ["BACKEND_LOG_FILE"] = str(TEST_LOG_DIR / f"backend{worker_slug()}.log")

    if debug_logs_requested():
        logging.basicConfig(level=logging.DEBUG)
        return

    # Empty rather than deleted: python-dotenv would otherwise put .env's own
    # value back when backend.database imports.
    os.environ["DEBUG_DATABASE"] = ""
    os.environ["LOG_LEVEL"] = "WARNING"
    logging.basicConfig(level=logging.WARNING)
