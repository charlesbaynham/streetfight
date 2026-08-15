"""The one signing scheme for every QR code the game prints.

Item pickups and team-join codes are both just payloads handed to strangers on
paper, so they share a single HMAC keyed on ``SECRET_KEY``. The ``kind``
prefix ("item" / "join") domain-separates the payload types: a signature made
for one kind can never validate as another. Deterministic (no salt), so
reprinting a code yields an identical URL.
"""

import hashlib
import hmac
import os

from .dotenv import load_env_vars

load_env_vars()


def sign_payload(kind: str, *parts) -> str:
    """HMAC-SHA256 (hex) over ``f"{kind}:" + ":".join(str(p) for p in parts)``."""
    message = f"{kind}:" + ":".join(str(p) for p in parts)
    return hmac.new(
        os.environ["SECRET_KEY"].encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
