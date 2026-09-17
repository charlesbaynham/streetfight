"""Rebuild the live-schema snapshot from a git revision.

There are no migrations, so tests/test_database.py upgrades a copy of the live
schema and checks the result still serves the ORM. That needs a snapshot of
what live is actually running, and live's database was built by create_all()
from its own revision's models -- so the snapshot is reproducible from git
rather than dumped off the droplet.

Usage, from the repo root:

    python tests/live_schema/refresh.py <rev>

where <rev> is the revision live reports at /api/get_version. Writes
tests/live_schema/<today>_<rev7>.sql. Commit it, delete the file it replaces,
and point SNAPSHOT in tests/test_database.py at the new name.

The revision's backend/model.py is loaded on its own, in a temporary package,
because the current one is what the test upgrades *to* -- importing it here
would compare the models against themselves.
"""

import datetime
import importlib.util
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

import sqlalchemy as sa

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

HEADER = """\
-- The schema of the live database, as of {date}, when the droplet was
-- running revision {rev}.
--
-- It is here so that tests/test_database.py can prove a pull request still
-- deploys: there are no migrations, so live is upgraded by create_all() plus
-- add_missing_columns() over exactly this, and only some changes survive that
-- (see CLAUDE.md, "There are still no migrations").
--
-- Live's database was built by create_all() from {rev}'s models, so this is
-- reproducible rather than dumped off the box. To refresh it when live moves,
-- run (from the repo root, with <rev> the new revision reported by
-- /api/get_version):
--
--   python tests/live_schema/refresh.py <rev>
--
-- which writes tests/live_schema/<today>_<rev>.sql. Commit the new file,
-- delete the old one, and point SNAPSHOT in tests/test_database.py at it. The
-- file name carries the revision, so a stale snapshot is visible.
"""


def _metadata_at(rev, workdir):
    source = subprocess.run(
        ["git", "show", f"{rev}:backend/model.py"],
        cwd=REPO,
        capture_output=True,
        check=True,
        text=True,
    ).stdout

    module_path = workdir / "live_model.py"
    module_path.write_text(source)

    spec = importlib.util.spec_from_file_location("live_model", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Base.metadata


def dump_schema(rev, workdir):
    metadata = _metadata_at(rev, workdir)

    db_path = workdir / "live.db"
    metadata.create_all(sa.create_engine(f"sqlite:///{db_path}"))

    with sqlite3.connect(db_path) as conn:
        statements = conn.execute(
            "SELECT sql FROM sqlite_master"
            " WHERE sql IS NOT NULL ORDER BY type DESC, name"
        ).fetchall()

    # Trailing whitespace stripped per line: sqlite pads its CREATE TABLE text
    # after every comma, and the pre-commit hook would otherwise rewrite the
    # file the moment it was committed.
    lines = [
        line.rstrip()
        for (sql,) in statements
        for line in f"{sql.strip()};".splitlines()
    ]
    return "".join(f"{line}\n" for line in lines)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2

    rev = argv[1]
    short = subprocess.run(
        ["git", "rev-parse", "--short=7", rev],
        cwd=REPO,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()

    with tempfile.TemporaryDirectory() as tmp:
        schema = dump_schema(rev, pathlib.Path(tmp))

    today = datetime.date.today().isoformat()
    out = HERE / f"{today}_{short}.sql"
    out.write_text(HEADER.format(date=today, rev=short) + schema)
    print(f"wrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
