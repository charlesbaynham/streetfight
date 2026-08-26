"""Transport for vision-model calls, via OpenRouter.

This module knows how to send an image and a prompt somewhere and get JSON
back. It knows nothing about shots, channels or colours -- that is
:mod:`backend.shot_vision`.

The model is **not** fixed. It is read from ``OPENROUTER_MODEL`` so different
models can be trialled against real photos without a code change, which means
this client cannot rely on any one provider's conveniences: structured-output
support is requested but never assumed, and the reply is parsed defensively.
"""

import asyncio
import json
import logging
import os
import re
from typing import List
from typing import Optional

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# A placeholder while the prompt is developed. The intended workflow is to trial
# several models against real shot photos and pick on measured abstention
# behaviour, so treat this as a starting point, not a decision.
DEFAULT_MODEL = "google/gemini-3.7-flash-20260813"

DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_ATTEMPTS = 3

# Fenced code blocks are the most common way a model wraps JSON it was asked to
# emit bare.
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class VisionError(RuntimeError):
    """The vision model could not be reached, or did not answer usefully."""


def parse_json_reply(text: str) -> dict:
    """Pull a JSON object out of a model's reply.

    Handles the three things models actually do when asked for JSON: emit it
    bare, wrap it in a ``` fence, or bracket it with a sentence of commentary.
    Raises :class:`VisionError` if there is no object in there at all.
    """
    if not text or not text.strip():
        raise VisionError("the model returned an empty reply")

    candidates = [text]

    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))

    # Last resort: the outermost braces
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])  # noqa: E203 (black's slice style)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate.strip())
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed

    raise VisionError(f"could not find a JSON object in the reply: {text[:200]!r}")


class VisionClient:
    """The interface :mod:`backend.shot_vision` codes against.

    ``turns`` is a conversation: a list of
    ``{"role": "user"|"assistant", "text": str, "image_data_url": str|None,
    "reasoning_details": list|None}``. It is a list rather than a single
    prompt because the model may ask for a zoomed view of the photo, and
    answering that means a second turn with the first exchange still in view
    -- otherwise it re-reasons from scratch and cannot tell that it has
    already spent its one zoom. ``reasoning_details`` on an assistant turn is
    how a "thinking" model's own prior reasoning is carried into the next
    call -- see :attr:`last_reasoning_details`; dropping it makes every later
    turn re-reason from nothing but the previous turn's bare JSON answer.
    """

    async def complete(self, turns: List[dict], schema: dict) -> dict:
        raise NotImplementedError

    @property
    def last_reasoning(self) -> Optional[str]:
        """The model's own extended-thinking trace from the most recent
        :meth:`complete` call, when the provider returned one, as plain text
        for display.

        Distinct from the short ``"reasoning"`` field the model fills in as
        part of the JSON reply itself (see ``build_schema`` in
        :mod:`backend.shot_vision`) -- this is a provider-level reasoning
        trace (OpenRouter's unified reasoning tokens), not part of the parsed
        reply. None when there is nothing to show.
        """
        return None

    @property
    def last_reasoning_details(self) -> Optional[List[dict]]:
        """The structured reasoning blocks behind :attr:`last_reasoning`.

        OpenRouter's provider-independent form (``message.reasoning_details``)
        -- opaque blocks (some providers' are encrypted) that must be passed
        back verbatim on the next turn's assistant message for the model to
        continue reasoning from where it left off, rather than starting over
        from just the previous turn's final answer. Use this for conversation
        continuation; use :attr:`last_reasoning` for showing a human what the
        model was thinking. None when the provider returned nothing.
        """
        return None


class OpenRouterVisionClient(VisionClient):
    """Calls a vision model through OpenRouter's chat-completions API."""

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = api_key
        self.model = model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
        self.timeout = timeout if timeout is not None else _timeout_from_env()
        self._last_reasoning: Optional[str] = None
        self._last_reasoning_details: Optional[List[dict]] = None

    @property
    def last_reasoning(self) -> Optional[str]:
        return self._last_reasoning

    @property
    def last_reasoning_details(self) -> Optional[List[dict]]:
        return self._last_reasoning_details

    async def complete(self, turns: List[dict], schema: dict) -> dict:
        import httpx

        payload = {
            "model": self.model,
            "messages": [_as_message(turn) for turn in turns],
            # Requested, not relied upon: a model without native JSON mode
            # ignores this and parse_json_reply picks up the slack.
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "shot_review",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        OPENROUTER_URL, json=payload, headers=headers
                    )

                if response.status_code == 429 or response.status_code >= 500:
                    last_error = VisionError(
                        f"OpenRouter returned {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                elif response.status_code >= 400:
                    # 4xx other than rate limiting is our fault; retrying an
                    # identical bad request just wastes the queue's time.
                    raise VisionError(
                        f"OpenRouter rejected the request ({response.status_code}): "
                        f"{response.text[:200]}"
                    )
                else:
                    content, reasoning, reasoning_details = _content_of(response.json())
                    self._last_reasoning = reasoning
                    self._last_reasoning_details = reasoning_details
                    return parse_json_reply(content)
            except VisionError:
                raise
            except Exception as e:  # network errors, timeouts, malformed JSON
                last_error = e

            if attempt < MAX_ATTEMPTS:
                backoff = 2**attempt
                logger.warning(
                    "Vision call attempt %s/%s failed (%s); retrying in %ss",
                    attempt,
                    MAX_ATTEMPTS,
                    last_error,
                    backoff,
                )
                await asyncio.sleep(backoff)

        raise VisionError(
            f"vision call failed after {MAX_ATTEMPTS} attempts: {last_error}"
        )


class FakeVisionClient(VisionClient):
    """A canned client for tests and for local development without a key.

    ``reply`` may be a single dict, a callable, or a list of dicts to hand back
    one per call -- which is how a test drives "ask for a zoom, then answer".
    """

    def __init__(
        self,
        reply=None,
        error: Optional[Exception] = None,
        reasoning=None,
        reasoning_details=None,
    ):
        self.reply = reply if reply is not None else {}
        self.error = error
        # None, a single string (every call), or a list parallel to ``reply``
        # -- mirrors how ``reply`` itself is indexed per call.
        self.reasoning = reasoning
        # None, a single reasoning_details array (every call), or a list of
        # arrays parallel to ``reply`` -- distinguished from the single-array
        # case by its elements being lists themselves rather than blocks.
        self.reasoning_details = reasoning_details
        self.calls = []

    async def complete(self, turns: List[dict], schema: dict) -> dict:
        self.calls.append({"turns": list(turns), "schema": schema})
        if self.error is not None:
            raise self.error
        if callable(self.reply):
            return self.reply(turns, schema)
        if isinstance(self.reply, list):
            index = min(len(self.calls), len(self.reply)) - 1
            return self.reply[index]
        return self.reply

    @property
    def last_reasoning(self) -> Optional[str]:
        if isinstance(self.reasoning, list):
            index = min(len(self.calls), len(self.reasoning)) - 1
            return self.reasoning[index] if 0 <= index < len(self.reasoning) else None
        return self.reasoning

    @property
    def last_reasoning_details(self) -> Optional[List[dict]]:
        value = self.reasoning_details
        if isinstance(value, list) and (not value or isinstance(value[0], list)):
            index = min(len(self.calls), len(value)) - 1
            return value[index] if 0 <= index < len(value) else None
        return value

    @property
    def images_sent(self) -> List[str]:
        """Every image handed to the model, in order, across all calls."""
        return [
            turn["image_data_url"]
            for call in self.calls
            for turn in call["turns"]
            if turn.get("image_data_url")
        ]


def _as_message(turn: dict) -> dict:
    """One conversation turn as a chat-completions message.

    Plain text plus an optional image part -- nothing provider-specific, so a
    swap of OPENROUTER_MODEL does not need a change here. An assistant turn
    may also carry ``reasoning_details`` (see :attr:`VisionClient.
    last_reasoning_details`) -- passed straight through, unmodified, exactly
    as OpenRouter requires for a "thinking" model to continue reasoning
    across turns rather than starting over from a bare JSON answer.
    """
    content = []
    if turn.get("text"):
        content.append({"type": "text", "text": turn["text"]})
    if turn.get("image_data_url"):
        content.append(
            {"type": "image_url", "image_url": {"url": turn["image_data_url"]}}
        )
    message = {"role": turn.get("role", "user"), "content": content}
    if turn.get("reasoning_details"):
        message["reasoning_details"] = turn["reasoning_details"]
    return message


def _content_of(body: dict):
    """The assistant's text, plus any reasoning trace, from a response body.

    Returns ``(content, reasoning, reasoning_details)``. Both reasoning
    fields are OpenRouter's unified reasoning-tokens output -- included by
    default whenever the model behind it produced one, no opt-in required --
    and are None for a model that didn't (or a provider that doesn't return
    them).
    """
    try:
        message = body["choices"][0]["message"]
        return (
            message["content"],
            message.get("reasoning") or None,
            message.get("reasoning_details") or None,
        )
    except (KeyError, IndexError, TypeError):
        raise VisionError(f"unexpected response shape: {str(body)[:200]}")


def _timeout_from_env() -> float:
    raw = os.getenv("OPENROUTER_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Ignoring unparseable OPENROUTER_TIMEOUT_SECONDS=%r; using %s",
            raw,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS


def get_vision_client() -> Optional[VisionClient]:
    """The configured client, or None if there is no API key.

    Returning None rather than raising is deliberate: with no key the feature
    is simply switched off, and the shot queue must behave exactly as it did
    before.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    return OpenRouterVisionClient(api_key=api_key)
