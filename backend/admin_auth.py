from threading import RLock
from uuid import UUID

from fastapi import HTTPException
from fastapi import Request
from fastapi import WebSocket

no_cookie_clients = {}
no_cookie_lock = RLock()


def _auth_from_session(request: Request) -> bool:
    try:
        return request.session["authed"] == "true"
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

    if not _auth_from_session(request_or_ws):
        raise HTTPException(403, "Not authorized")

    return True


def mark_admin_authed(request: Request) -> None:
    request.session["admin_authed"] = "true"
