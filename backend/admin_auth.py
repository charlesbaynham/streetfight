import logging
import os
from threading import RLock
from uuid import UUID

from fastapi import HTTPException
from fastapi import Request
from fastapi import WebSocket

logger = logging.getLogger(__name__)

no_cookie_clients = {}
no_cookie_lock = RLock()


def _auth_from_session(request: Request) -> bool:
    try:
        return request.session["admin_authed"] == "true"
    except KeyError:
        return False


async def is_admin_authed(
    *, request: Request = None, websocket: WebSocket = None
) -> UUID:
    request_or_ws = request or websocket

    return _auth_from_session(request_or_ws)


async def require_admin_auth(
    *, request: Request = None, websocket: WebSocket = None
) -> UUID:
    request_or_ws = request or websocket

    logger.debug("Checking if admin is authed. Session: %s", request_or_ws.session)

    if not _auth_from_session(request_or_ws):
        raise HTTPException(403, "Not authorized")

    return True


def mark_admin_authed(request: Request, password: str) -> None:
    if "ADMIN_PASSWORD" not in os.environ:
        logger.warning("No password set in environment - using default")

    correct_password = os.getenv("ADMIN_PASSWORD", "password")

    if password == correct_password:
        logger.info("Admin authenticated")
        request.session["admin_authed"] = "true"
        return True
    else:
        request.session["admin_authed"] = "false"
        raise HTTPException(403, "Wrong password")
