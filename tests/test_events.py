import asyncio
import json
import logging
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from backend.sse_event_streams import SSE_KEEPALIVE_TIMEOUT
from backend.sse_event_streams import admin_updates_generator
from backend.sse_event_streams import make_sse_update_message
from backend.sse_event_streams import updates_generator

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_user_interface():
    with patch("backend.sse_event_streams.UserInterface") as MockUserInterface:
        yield MockUserInterface


@pytest.fixture
def mock_admin_interface():
    with patch("backend.sse_event_streams.AdminInterface") as MockAdminInterface:
        yield MockAdminInterface


def test_make_sse_update_message():
    message = {"handler": "update_prompt", "data": "user"}
    expected_output = f"data: {json.dumps(message)}\n\n"
    assert make_sse_update_message(json.dumps(message)) == expected_output


@pytest.mark.asyncio
async def test_updates_generator(mock_user_interface):
    user_id = 1
    mock_user_interface.return_value.generate_user_updates = AsyncMock(
        return_value=iter([None])
    )
    mock_user_interface.return_value.get_team_id = AsyncMock(return_value=None)

    gen = updates_generator(user_id)
    result = [await anext(gen) for _ in range(2)]
    assert len(result) == 2


@pytest.mark.asyncio
async def test_admin_updates_generator(mock_admin_interface):
    mock_admin_interface.return_value.generate_any_ticker_updates = AsyncMock(
        return_value=iter([None])
    )

    gen = admin_updates_generator()
    result = [await anext(gen) for _ in range(2)]
    assert len(result) == 2


@pytest.mark.asyncio
async def test_keepalive_timer():
    async def keepalive_timer():
        i = 0
        while True:
            await asyncio.sleep(SSE_KEEPALIVE_TIMEOUT)
            yield i
            i += 1

    gen = keepalive_timer()
    result = [await anext(gen) for _ in range(2)]
    assert result == [0, 1]
