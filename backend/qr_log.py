"""``qr_codes.csv``: the record of every code that has ever been printed.

The tag and index stamped on a card mean nothing on their own - this file is
what turns them back into an item, and the game-day runbook has the operator
read it to tell two look-alike weapon cards apart.

The default sits beside the source tree, which is where a developer running
``npm run qrgen`` wants it. On a deployment the source tree is a read-only
``/nix/store`` path, so ``QR_LOGFILE`` moves the file onto the state directory
instead (``nix/streetfight.nix`` sets it).
"""

import os
from pathlib import Path
from typing import Iterable

QR_LOGFILE_ENV = "QR_LOGFILE"

DEFAULT_QR_LOGFILE = Path(__file__, "../../qr_codes.csv").resolve()


def qr_logfile() -> Path:
    """Read per call rather than at import, so a test or a CLI can move it."""
    return Path(os.environ.get(QR_LOGFILE_ENV) or DEFAULT_QR_LOGFILE)


def append_rows(rows: Iterable[str]) -> None:
    """Append ``rows`` to the log. The file has no header and is read by
    column number, so a new field goes on the end of a row, never in it."""
    with open(qr_logfile(), "a") as f:
        f.writelines(f"{row}\n" for row in rows)
