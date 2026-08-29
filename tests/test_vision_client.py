"""Tests for the OpenRouter transport itself: turning a response body into
(content, reasoning, reasoning_details), and turning a turn back into a
chat-completions message -- the two ends of carrying a "thinking" model's
reasoning across turns without depending on any one provider's format.
"""

import pytest

from backend.vision_client import OPENROUTER_IMAGE_URL
from backend.vision_client import OpenRouterImageClient
from backend.vision_client import OpenRouterVisionClient
from backend.vision_client import VisionError
from backend.vision_client import _as_message
from backend.vision_client import _content_of
from backend.vision_client import _normalize_reasoning_effort
from backend.vision_client import fetch_openrouter_key_balance
from backend.vision_client import get_vision_client


def response_body(message: dict) -> dict:
    return {"choices": [{"message": message}]}


def test_content_of_extracts_reply_reasoning_and_reasoning_details():
    details = [{"type": "reasoning.text", "text": "Thinking it through..."}]
    body = response_body(
        {
            "role": "assistant",
            "content": '{"shot_hit_a_person": true}',
            "reasoning": "Thinking it through...",
            "reasoning_details": details,
        }
    )

    content, reasoning, reasoning_details = _content_of(body)

    assert content == '{"shot_hit_a_person": true}'
    assert reasoning == "Thinking it through..."
    assert reasoning_details == details


def test_content_of_defaults_both_reasoning_fields_to_none_when_absent():
    body = response_body({"role": "assistant", "content": "{}"})

    content, reasoning, reasoning_details = _content_of(body)

    assert content == "{}"
    assert reasoning is None
    assert reasoning_details is None


def test_content_of_rejects_an_unexpected_shape():
    with pytest.raises(VisionError):
        _content_of({"choices": []})


def test_as_message_omits_reasoning_details_when_the_turn_has_none():
    message = _as_message({"role": "assistant", "text": '{"a": 1}'})

    assert "reasoning_details" not in message


def test_as_message_passes_reasoning_details_through_unmodified():
    details = [{"type": "reasoning.encrypted", "data": "opaque-blob"}]

    message = _as_message(
        {"role": "assistant", "text": '{"a": 1}', "reasoning_details": details}
    )

    assert message["reasoning_details"] == details
    # It rides alongside the usual content, not in place of it.
    assert message["content"] == [{"type": "text", "text": '{"a": 1}'}]


# -- reasoning-effort configuration ------------------------------------------


def test_normalize_reasoning_effort_lowercases_and_validates():
    assert _normalize_reasoning_effort("HIGH") == "high"
    assert _normalize_reasoning_effort("  medium  ") == "medium"
    assert _normalize_reasoning_effort(None) is None
    assert _normalize_reasoning_effort("") is None


def test_normalize_reasoning_effort_rejects_unknown_values():
    assert _normalize_reasoning_effort("extreme") is None


def test_client_sends_no_reasoning_override_by_default(monkeypatch):
    # The long-standing pipeline behaviour: nothing requested, unless
    # OPENROUTER_REASONING_EFFORT says otherwise.
    monkeypatch.delenv("OPENROUTER_REASONING_EFFORT", raising=False)

    client = OpenRouterVisionClient(api_key="k")

    assert client.reasoning_effort is None


def test_client_reads_reasoning_effort_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REASONING_EFFORT", "low")

    client = OpenRouterVisionClient(api_key="k")

    assert client.reasoning_effort == "low"


def test_explicit_reasoning_effort_overrides_the_env_setting(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REASONING_EFFORT", "low")

    client = OpenRouterVisionClient(api_key="k", reasoning_effort="high")

    assert client.reasoning_effort == "high"


def test_get_vision_client_forwards_the_override(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_REASONING_EFFORT", "low")

    default_client = get_vision_client()
    overridden_client = get_vision_client(reasoning_effort="xhigh")

    assert default_client.reasoning_effort == "low"
    assert overridden_client.reasoning_effort == "xhigh"


class _FakeResponse:
    status_code = 200

    def json(self):
        return response_body({"role": "assistant", "content": "{}"})


class _FakeHTTPXClient:
    """Captures the JSON payload of the one POST it expects, for asserting on
    without touching the network."""

    sent_payloads = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json, headers):
        _FakeHTTPXClient.sent_payloads.append(json)
        return _FakeResponse()


@pytest.mark.asyncio
async def test_complete_sends_no_reasoning_key_when_unset(monkeypatch, mocker):
    monkeypatch.delenv("OPENROUTER_REASONING_EFFORT", raising=False)
    _FakeHTTPXClient.sent_payloads = []
    mocker.patch("httpx.AsyncClient", _FakeHTTPXClient)

    client = OpenRouterVisionClient(api_key="k")
    await client.complete([{"role": "user", "text": "hi"}], schema={})

    assert "reasoning" not in _FakeHTTPXClient.sent_payloads[0]


@pytest.mark.asyncio
async def test_complete_sends_the_effort_as_a_reasoning_request_parameter(
    monkeypatch, mocker
):
    _FakeHTTPXClient.sent_payloads = []
    mocker.patch("httpx.AsyncClient", _FakeHTTPXClient)

    client = OpenRouterVisionClient(api_key="k", reasoning_effort="high")
    await client.complete([{"role": "user", "text": "hi"}], schema={})

    assert _FakeHTTPXClient.sent_payloads[0]["reasoning"] == {"effort": "high"}


# -- fetch_openrouter_key_balance ---------------------------------------------


class _FakeKeyResponse:
    def __init__(self, status_code=200, body=None, text="error"):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        return self._body


class _FakeHTTPXGetClient:
    """Captures the request it expects and hands back a canned response,
    without touching the network."""

    response = None
    sent_headers = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers):
        _FakeHTTPXGetClient.sent_headers = headers
        return _FakeHTTPXGetClient.response


@pytest.mark.asyncio
async def test_fetch_openrouter_key_balance_returns_the_limit_fields(mocker):
    _FakeHTTPXGetClient.response = _FakeKeyResponse(
        body={"data": {"limit": 100, "limit_remaining": 74.5, "usage": 25.5}}
    )
    mocker.patch("httpx.AsyncClient", _FakeHTTPXGetClient)

    balance = await fetch_openrouter_key_balance("k")

    assert balance == {"limit": 100, "limit_remaining": 74.5, "usage": 25.5}
    assert _FakeHTTPXGetClient.sent_headers == {"Authorization": "Bearer k"}


@pytest.mark.asyncio
async def test_fetch_openrouter_key_balance_raises_on_a_rejected_key(mocker):
    _FakeHTTPXGetClient.response = _FakeKeyResponse(status_code=401, text="bad key")
    mocker.patch("httpx.AsyncClient", _FakeHTTPXGetClient)

    with pytest.raises(VisionError):
        await fetch_openrouter_key_balance("k")


@pytest.mark.asyncio
async def test_fetch_openrouter_key_balance_raises_on_an_unexpected_body(mocker):
    _FakeHTTPXGetClient.response = _FakeKeyResponse(body={"unexpected": "shape"})
    mocker.patch("httpx.AsyncClient", _FakeHTTPXGetClient)

    with pytest.raises(VisionError):
        await fetch_openrouter_key_balance("k")


# -- OpenRouterImageClient -----------------------------------------------------


class _FakeImageResponse:
    status_code = 200

    def json(self):
        return {
            "data": [{"b64_json": "AAAA", "media_type": "image/jpeg"}],
            "usage": {"cost": 0.035},
        }


class _FakeImageHTTPXClient(_FakeHTTPXClient):
    posted_urls = []

    async def post(self, url, json, headers):
        _FakeImageHTTPXClient.posted_urls.append(url)
        _FakeHTTPXClient.sent_payloads.append(json)
        return _FakeImageResponse()


@pytest.mark.asyncio
async def test_generate_posts_to_the_image_api_and_returns_a_data_url(mocker):
    """The whole transport, not just its parts: the first real generation run
    failed on a NameError inside it, and the second on being pointed at
    /chat/completions, which does not serve image models at all.
    """
    _FakeHTTPXClient.sent_payloads = []
    _FakeImageHTTPXClient.posted_urls = []
    mocker.patch("httpx.AsyncClient", _FakeImageHTTPXClient)

    client = OpenRouterImageClient(
        api_key="k", model="bytedance-seed/seedream-5-0-lite"
    )
    url = await client.generate(
        "a photograph", ["data:image/jpeg;base64,BBBB"], seed=1, aspect_ratio="1:1"
    )

    assert url == "data:image/jpeg;base64,AAAA"
    # What it cost is read back rather than estimated: the gates spend real
    # money and the rate-card arithmetic was out by an order of magnitude.
    assert client.last_cost_usd == 0.035
    assert _FakeImageHTTPXClient.posted_urls == [OPENROUTER_IMAGE_URL]

    payload = _FakeHTTPXClient.sent_payloads[0]
    assert payload["prompt"] == "a photograph"
    assert payload["seed"] == 1
    assert payload["aspect_ratio"] == "1:1"
    # Reference images ride in input_references here, not as message content.
    assert payload["input_references"] == [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,BBBB"}}
    ]
