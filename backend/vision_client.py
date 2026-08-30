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
OPENROUTER_IMAGE_URL = "https://openrouter.ai/api/v1/images"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"

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
        reasoning_effort: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
        self.timeout = timeout if timeout is not None else _timeout_from_env()
        # None (the long-standing default) sends no "reasoning" request
        # parameter at all -- whatever effort the model applies unprompted.
        # Falls back to OPENROUTER_REASONING_EFFORT so the live pipeline is
        # configurable without a code change; the replay workbench overrides
        # it per request regardless of the env setting.
        self.reasoning_effort = _normalize_reasoning_effort(
            reasoning_effort
            if reasoning_effort is not None
            else os.getenv("OPENROUTER_REASONING_EFFORT")
        )
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
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
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


# OpenRouter's own vocabulary for the "reasoning" request parameter's
# "effort" key (docs/use-cases/reasoning-tokens). Not every model honours
# every level, but these are the values OpenRouter itself accepts.
VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


def _normalize_reasoning_effort(value: Optional[str]) -> Optional[str]:
    """A validated, lowercased reasoning-effort level, or None.

    None means "send no reasoning-effort override" -- OpenRouter's own
    default, whatever the model applies unprompted. That has been this
    pipeline's behaviour all along, so it stays the default here: this only
    ever *adds* a request parameter, never removes one.
    """
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized not in VALID_REASONING_EFFORTS:
        logger.warning(
            "Ignoring unrecognised reasoning effort %r; sending no override", value
        )
        return None
    return normalized


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


def get_vision_client(reasoning_effort: Optional[str] = None) -> Optional[VisionClient]:
    """The configured client, or None if there is no API key.

    Returning None rather than raising is deliberate: with no key the feature
    is simply switched off, and the shot queue must behave exactly as it did
    before.

    ``reasoning_effort`` overrides ``OPENROUTER_REASONING_EFFORT`` for this
    client -- the replay workbench's per-request knob; the live queue calls
    this with no argument and gets the env-configured (or unset) default.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    return OpenRouterVisionClient(api_key=api_key, reasoning_effort=reasoning_effort)


def get_escalation_client(
    reasoning_effort: Optional[str] = None,
) -> Optional[VisionClient]:
    """The stronger model's client (roadmap #11), or None if it is not set up.

    Two switches, both off by default: no ``OPENROUTER_API_KEY`` and there is
    no vision at all; no ``OPENROUTER_ESCALATION_MODEL`` and escalation
    specifically is off, which is the safety valve surviving intact -- with it
    unset, a shot the ladder wants escalated simply waits for the admin, which
    is where every shot went before any of this existed.

    Nothing here is model-specific: it is the same OpenRouter client pointed at
    a different model id, so trialling a new one is an environment change.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    escalation_model = os.getenv("OPENROUTER_ESCALATION_MODEL")
    if not api_key or not escalation_model:
        return None
    return OpenRouterVisionClient(
        api_key=api_key,
        model=escalation_model,
        reasoning_effort=(
            reasoning_effort or os.getenv("OPENROUTER_ESCALATION_REASONING_EFFORT")
        ),
    )


async def fetch_openrouter_key_balance(
    api_key: str, timeout: Optional[float] = None
) -> dict:
    """The remaining credit balance for ``api_key``, for the admin footer readout.

    Hits OpenRouter's ``/key`` endpoint, which reports on whichever key
    authenticates the request -- the same regular API key used for
    completions, no management key required. Returns ``limit`` (the key's
    spending cap in USD, or None if uncapped), ``limit_remaining`` and
    ``usage``. Raises :class:`VisionError` if the key is rejected or the
    endpoint can't be reached.
    """
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=timeout or DEFAULT_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(
                OPENROUTER_KEY_URL, headers={"Authorization": f"Bearer {api_key}"}
            )
    except Exception as e:
        raise VisionError(f"could not reach OpenRouter: {e}")

    if response.status_code >= 400:
        raise VisionError(
            f"OpenRouter rejected the request ({response.status_code}): "
            f"{response.text[:200]}"
        )

    try:
        data = response.json()["data"]
    except (KeyError, TypeError, ValueError):
        raise VisionError(f"unexpected response shape: {response.text[:200]}")

    return {
        "limit": data.get("limit"),
        "limit_remaining": data.get("limit_remaining"),
        "usage": data.get("usage"),
    }


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------

# The generation path must never reach a Google model. The recogniser under
# test is Gemini, so generating its exam paper with Gemini would make the
# benchmark circular -- and a stray OPENROUTER_MODEL in somebody's .env is
# exactly how that would happen silently. This is an explicit guard rather
# than a convention, because a convention cannot fail loudly.
FORBIDDEN_GENERATION_PREFIXES = ("google/",)

DEFAULT_IMAGE_MODEL = "openai/gpt-5.4-image-2"


class ImageGenerationError(RuntimeError):
    pass


class OpenRouterImageClient:
    """Generate an image from a prompt and zero or more input images.

    Posts to OpenRouter's **Image** API, not to ``/chat/completions``: the
    image models are served there, take their reference images as
    ``input_references``, and answer with base64 rather than with a data URL
    on a chat message. Asking ``/chat/completions`` for one is a 500 (or, if
    the model emits image only and the request asks for image *and* text, a
    404) -- which is a whole evening of debugging written down so nobody
    repeats it.

    The base64 is turned back into a ``data:image/...;base64,...`` URL, which
    is the form the rest of this codebase already consumes.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ImageGenerationError("OPENROUTER_API_KEY is not set")
        self.model = model or os.getenv("OPENROUTER_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL
        self.timeout = timeout if timeout is not None else _timeout_from_env()
        # What the last generation actually cost, straight from OpenRouter.
        # The gates are about spending honestly, and a price table written
        # from a rate card was out by several times when it was first run.
        self.last_cost_usd: Optional[float] = None

        lowered = self.model.lower()
        for prefix in FORBIDDEN_GENERATION_PREFIXES:
            if lowered.startswith(prefix):
                raise ImageGenerationError(
                    f"refusing to generate images with {self.model!r}: the "
                    "recogniser being tested is a Google model, so generating "
                    "its inputs with one would make the benchmark circular"
                )

    async def generate(
        self, prompt: str, input_image_urls: Optional[List[str]] = None, **params
    ) -> str:
        """Return a ``data:image/...;base64,...`` URL for the generated image.

        ``params`` are the Image API's generation parameters -- ``seed``,
        ``aspect_ratio``, ``resolution``, ``n`` -- and an unlisted one is
        rejected, so they are passed through rather than guessed at here.
        """
        import httpx

        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "input_references": [
                {"type": "image_url", "image_url": {"url": url}}
                for url in input_image_urls or []
            ],
        }
        payload.update(params)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        OPENROUTER_IMAGE_URL, json=payload, headers=headers
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    # 502 is an upstream generation failure, and OpenRouter
                    # does not bill it, so retrying costs nothing.
                    last_error = ImageGenerationError(
                        f"OpenRouter returned {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                elif response.status_code >= 400:
                    raise ImageGenerationError(
                        f"OpenRouter rejected the request ({response.status_code}): "
                        f"{response.text[:200]}"
                    )
                else:
                    body = response.json()
                    self.last_cost_usd = (body.get("usage") or {}).get("cost")
                    return _image_data_url_of(body)
            except httpx.HTTPError as e:
                last_error = ImageGenerationError(f"OpenRouter request failed: {e}")

            if attempt < MAX_ATTEMPTS:
                # Same escalating backoff as the vision path above.
                await asyncio.sleep(2.0 * attempt)

        raise last_error or ImageGenerationError("image generation failed")


def _image_data_url_of(body: dict) -> str:
    """Turn an Image API reply into the data URL the rest of the code uses."""
    images = body.get("data") or []
    for image in images:
        encoded = image.get("b64_json")
        if encoded:
            media = image.get("media_type") or "image/png"
            return f"data:{media};base64,{encoded}"
    raise ImageGenerationError(f"the model returned no image: {json.dumps(body)[:200]}")
