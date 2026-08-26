"""Tests for the OpenRouter transport itself: turning a response body into
(content, reasoning, reasoning_details), and turning a turn back into a
chat-completions message -- the two ends of carrying a "thinking" model's
reasoning across turns without depending on any one provider's format.
"""

import pytest

from backend.vision_client import OpenRouterVisionClient
from backend.vision_client import VisionError
from backend.vision_client import _as_message
from backend.vision_client import _content_of
from backend.vision_client import _normalize_reasoning_effort
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
