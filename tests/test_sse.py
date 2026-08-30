import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend import sse_event_streams
from backend.admin_interface import AdminInterface
from backend.asyncio_triggers import trigger_update_event


@pytest.mark.skip(reason="Broken. See https://github.com/encode/starlette/issues/1102")
@pytest.mark.asyncio
async def test_sse_endpoint(api_client: TestClient):
    # with api_client.get("/api/sse_updates", stream=True) as response:
    #     assert response.status_code == 200
    #     assert response.headers["content-type"] == "text/event-stream"

    resp = await api_client.get("/api/sse_updates", stream=True)
    assert resp.status_code == 200

    async for line in resp.iter_content(1):
        print(line)

        # Iterate through SSE events
        # for i in range(3):
        #     event = response.iter_lines(delimiter="\n")
        #     print(event)

    assert False


def parse_sse(message: str) -> dict:
    """Pull the JSON body out of a "data: {...}\n\n" frame."""
    assert message.startswith("data: ")
    return json.loads(message.removeprefix("data: ").strip())


@pytest.mark.asyncio
async def test_the_admin_stream_sends_keepalives(monkeypatch, one_game):
    """A quiet game must not look like a dead connection.

    UpdateListener.js restarts any stream that goes KEEPALIVE_TIMEOUT (20s)
    without a message, so without this the spectator screen - left running all
    night on a TV - reconnects every twenty seconds forever.
    """
    monkeypatch.setattr(sse_event_streams, "SSE_KEEPALIVE_TIMEOUT", 0.1)

    generator = sse_event_streams.admin_updates_generator()

    # The three prompts every admin stream opens with
    for _ in range(3):
        await asyncio.wait_for(anext(generator), timeout=1)

    keepalive = parse_sse(await asyncio.wait_for(anext(generator), timeout=2))

    assert keepalive["handler"] == "keepalive"
    assert keepalive["data"] == 0

    await generator.aclose()


@pytest.mark.asyncio
async def test_the_admin_stream_leaves_no_waiters_behind(one_game):
    """Every update the admin stream reports wakes one of the events it is
    watching. The rest must not survive it.

    The stream subscribes to three events per game and consumes whichever
    fires first; the losers wait on events that have already been discarded
    from the registry, so they can never complete. An admin page left open all
    evening would otherwise accumulate a task per game per update, and closing
    the page would not collect them either.
    """
    generator = AdminInterface().generate_any_game_updates()

    waiting_before = len(asyncio.all_tasks())

    for _ in range(3):
        update = asyncio.ensure_future(anext(generator))
        await asyncio.sleep(0.05)  # let the generator subscribe
        trigger_update_event("ticker", one_game)
        await asyncio.wait_for(update, timeout=1)

    await generator.aclose()
    await asyncio.sleep(0.05)  # let the cancellations land

    assert len(asyncio.all_tasks()) == waiting_before
