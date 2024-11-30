import pytest
from fastapi import HTTPException

from backend.admin_auth import _auth_from_session
from backend.admin_auth import is_admin_authed
from backend.admin_auth import mark_admin_authed
from backend.admin_auth import require_admin_auth


@pytest.fixture
def mock_request():
    class MockRequest:
        def __init__(self, session):
            self.session = session

    return MockRequest


@pytest.fixture
def mock_websocket():
    class MockWebSocket:
        def __init__(self, session):
            self.session = session

    return MockWebSocket


def test_auth_from_session(mock_request):
    request = mock_request({"authed": "true"})
    assert _auth_from_session(request) == True

    request = mock_request({})
    assert _auth_from_session(request) == False


@pytest.mark.asyncio
async def test_is_admin_authed(mock_request, mock_websocket):
    request = mock_request({"authed": "true"})
    assert await is_admin_authed(request=request) == True

    websocket = mock_websocket({"authed": "true"})
    assert await is_admin_authed(websocket=websocket) == True

    request = mock_request({})
    assert await is_admin_authed(request=request) == False


@pytest.mark.asyncio
async def test_require_admin_auth(mock_request, mock_websocket):
    request = mock_request({"authed": "true"})
    assert await require_admin_auth(request=request) == True

    websocket = mock_websocket({"authed": "true"})
    assert await require_admin_auth(websocket=websocket) == True

    request = mock_request({})
    with pytest.raises(HTTPException):
        await require_admin_auth(request=request)


def test_mark_admin_authed(mock_request):
    request = mock_request({})
    mark_admin_authed(request)
    assert request.session["admin_authed"] == "true"
