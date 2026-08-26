"""Tests for the OpenRouter transport itself: turning a response body into
(content, reasoning, reasoning_details), and turning a turn back into a
chat-completions message -- the two ends of carrying a "thinking" model's
reasoning across turns without depending on any one provider's format.
"""

import pytest

from backend.vision_client import VisionError
from backend.vision_client import _as_message
from backend.vision_client import _content_of


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
