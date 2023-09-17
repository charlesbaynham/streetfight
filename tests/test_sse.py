import pytest
from fastapi.testclient import TestClient


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
