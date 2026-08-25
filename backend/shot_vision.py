"""Reading a shot photo: the prompt, the response contract, and the verdict.

This is the vision *adapter* from the design brief (plan §8.1). It sits between
:mod:`backend.vision_client` (which just moves bytes) and
:mod:`backend.identity` (which is pure and knows nothing about photographs).

Two principles run through it:

**The model observes; Python decides.** The model answers two kinds of question
it can actually see the answer to: did the shot land on a person, and what
colour is each garment. It is never asked whether that person is a *player* --
:func:`classify` decides that from the observations, so the rule lives somewhere
tests can pin it down and does not drift when the model behind
``OPENROUTER_MODEL`` changes.

**An erasure is cheaper than a misread.** The code corrects two erasures but
only one misread (``d >= 2t + e + 1``), so "unknown" is offered for every
channel and the prompt asks about visibility before colour. Measured (plan
§12.1): without that, a model converts "I cannot see it" into a confident wrong
colour, which is the expensive failure.
"""

import json
import logging
from typing import Dict
from typing import List
from typing import Optional

from .identity.config import COLOUR_BUCKETS
from .identity.config import DEFAULT_CHANNEL_NAMES
from .identity.config import DEFAULT_THRESHOLDS
from .identity.config import default_scheme
from .identity.config import hex_for
from .identity.config import palette_for_channel
from .identity.observations import ChannelObservation
from .identity.observations import Reading

logger = logging.getLogger(__name__)

UNKNOWN = "unknown"

# A channel read below this confidence is treated as an erasure, exactly like
# not-visible/unknown: the code corrects two erasures but only one misread, so
# a shaky colour is worth less than an honest abstention. The same constant
# gates the auto-actions in backend.shot_auto_actions.
CONFIDENT_THRESHOLD = DEFAULT_THRESHOLDS.confident_threshold

# The reply field carrying "did the shot land on a person". Note that is not
# "is somebody standing at the centre": clothing, hands and shoes all count, and
# only a shot that entirely misses the person is a miss.
HIT_FIELD = "shot_hit_a_person"

# The model asks for a closer look by setting this. It gets one.
ZOOM_FIELD = "request_zoom"
ZOOM_FACTOR = 4

# Outcomes. Only HIT_PLAYER counts against a player's hit points. Shown to the
# admin as advice -- and, when a game's AI-review toggle is on, acted on for the
# head of the queue by backend.shot_auto_actions when confident enough.
HIT_PLAYER = "hit_player"
HIT_BYSTANDER = "hit_bystander"
MISS = "miss"

# Human-readable channel names for the prompt. The keys must stay in step with
# identity.config.DEFAULT_CHANNEL_NAMES.
CHANNEL_DESCRIPTIONS = {
    "tshirt": "the t-shirt or top on their torso",
    "trousers": "the trousers, jeans or shorts on their legs",
    "hat": "the hat or headwear on their head",
    "armbands": "the coloured armbands worn on the upper arms",
}


class ShotVisionError(ValueError):
    """The model's reply did not match the contract."""


class ChannelRead:
    """What the model reported for one channel."""

    def __init__(self, visible: bool, colour: Optional[str], confidence: float):
        self.visible = visible
        self.colour = colour  # None == unreadable (an erasure)
        self.confidence = confidence

    @property
    def is_erasure(self) -> bool:
        return self.colour is None

    def to_dict(self) -> dict:
        return {
            "visible": self.visible,
            "colour": self.colour,
            "confidence": self.confidence,
        }


class ShotVisionResult:
    """The parsed, validated reading plus the outcome Python decided."""

    def __init__(
        self,
        shot_hit_a_person: bool,
        channels: Dict[str, ChannelRead],
        reasoning: str = "",
        outcome: str = MISS,
        outcome_reason: str = "",
        slot: Optional[int] = None,
        confidence: float = 0.0,
        zoom_used: bool = False,
    ):
        self.shot_hit_a_person = shot_hit_a_person
        self.channels = channels
        self.reasoning = reasoning
        self.outcome = outcome
        self.outcome_reason = outcome_reason
        self.slot = slot
        self.confidence = confidence
        self.zoom_used = zoom_used

    @property
    def is_hit(self) -> bool:
        return self.outcome == HIT_PLAYER

    def to_dict(self) -> dict:
        """The JSON stored on the Shot and rendered as tags in the queue."""
        return {
            "shot_hit_a_person": self.shot_hit_a_person,
            "confidence": self.confidence,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "is_hit": self.is_hit,
            "slot": self.slot,
            "reasoning": self.reasoning,
            "zoom_used": self.zoom_used,
            "channels": {
                name: dict(read.to_dict(), hex=hex_for(name, read.colour))
                for name, read in self.channels.items()
            },
        }


# ---------------------------------------------------------------------------
# The prompt and its response contract
# ---------------------------------------------------------------------------


def channel_palettes() -> Dict[str, List[str]]:
    """``{channel: [colour, ...]}`` -- each channel's own alphabet."""
    return {name: palette_for_channel(name) for name in DEFAULT_CHANNEL_NAMES}


def build_schema(palettes: Optional[Dict[str, List[str]]] = None) -> dict:
    """The JSON schema the model is asked to fill in."""
    palettes = palettes or channel_palettes()
    return {
        "type": "object",
        "properties": {
            HIT_FIELD: {"type": "boolean"},
            # Asking for the zoom through the reply rather than a provider
            # tool-call API: OPENROUTER_MODEL is meant to be swapped freely, and
            # a boolean in the JSON works on every model.
            ZOOM_FIELD: {"type": "boolean"},
            "reasoning": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "channels": {
                "type": "object",
                "properties": {
                    name: {
                        "type": "object",
                        "properties": {
                            "visible": {"type": "boolean"},
                            # "unknown" is mandatory in every channel's list.
                            "colour": {"enum": list(palette) + [UNKNOWN]},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["visible", "colour", "confidence"],
                        "additionalProperties": False,
                    }
                    for name, palette in palettes.items()
                },
                "required": list(palettes),
                "additionalProperties": False,
            },
        },
        "required": [HIT_FIELD, ZOOM_FIELD, "reasoning", "confidence", "channels"],
        "additionalProperties": False,
    }


def wants_zoom(raw) -> bool:
    """Whether a raw reply is a request for a closer look.

    Checked *before* :func:`parse_result`, because a model asking for the zoom
    will not have filled in the channels yet and ``parse_result`` is right to
    reject a reply that has not.
    """
    return isinstance(raw, dict) and raw.get(ZOOM_FIELD) is True


_HIT_TEST = f"""FIRST: did the shot hit a person? If the centre of the cross is on empty ground, \
a wall, foliage, the sky, or nobody in particular, set "{HIT_FIELD}" to false -- \
even if one of the red lines passes over or right next to a person elsewhere in \
the frame. The lines themselves are not the hit; only their centre point is."""

_ZOOM_OPTIONAL_SENTENCES = """Some shots will be very close. For these, if it is \
difficult for you to tell whether it is a hit or not, you may request a zoomed \
version of the image once. You MUST ultimately make a decision on whether the \
shot is hitting a person or not."""

_ZOOM_UPFRONT_SENTENCES = """You MUST ultimately make a decision on whether the \
shot is hitting a person or not -- the zoomed view is already in front of you \
for exactly that."""

_HIT_DEFINITION = """It is a hit only if the centre of the cross itself lands on \
the person -- on their clothing, hands, or shoes. It is a miss if the centre \
point is on the background instead -- ground, a wall, foliage, a street light \
-- even if that background is right beside them."""

DEFAULT_DECISION_RULE = f"{_HIT_TEST}\n\n{_ZOOM_OPTIONAL_SENTENCES} {_HIT_DEFINITION}"

# The same rule for when the zoom is provided up front rather than on request:
# identical except that there is nothing left to ask for.
UPFRONT_ZOOM_DECISION_RULE = (
    f"{_HIT_TEST}\n\n{_ZOOM_UPFRONT_SENTENCES} {_HIT_DEFINITION}"
)


def build_prompt(
    palettes: Optional[Dict[str, List[str]]] = None,
    decision_rule: Optional[str] = None,
    zoom_offered: bool = True,
) -> str:
    """The instructions sent alongside the photo.

    ``decision_rule`` is the paragraph(s) telling the model how to turn the
    cross's position into a hit/miss call -- pulled out as a parameter so
    roadmap #4's prompt variants (``scripts/replay_shot_reviews.py``) can swap
    it without duplicating the rest of the template (channel questions,
    colour buckets, JSON shape).

    ``zoom_offered`` selects the zoom wording: the model is either *offered* a
    zoom it may request once (the default), or told the zoomed view is already
    in front of it (the always-zoom path in :func:`review_image`), in which
    case the default decision rule drops the request sentences to match.
    """
    palettes = palettes or channel_palettes()
    if decision_rule is None:
        decision_rule = (
            DEFAULT_DECISION_RULE if zoom_offered else UPFRONT_ZOOM_DECISION_RULE
        )

    if zoom_offered:
        zoom_paragraph = """You have the ability to request a zoomed-in view of this photograph if you reply \
with {"request_zoom": true} and nothing else. The next turn will provide you an \
image that contains only the middle 25% of the image in higher resolution. You \
may do this once only, so spend it on a target that is too small or too far away \
to judge from the whole frame. If the image is merely blurred, a zoom will not \
help."""
    else:
        zoom_paragraph = """You are shown this photograph twice: the first image is the whole frame, and \
the second is a zoomed-in view containing only the middle 25% of it in higher \
resolution, with the same red cross redrawn at the same aim point -- only its \
centre pixel counts, exactly as in the full frame. Use whichever view is \
clearer, and trust the zoomed one when they disagree. The zoom is already in \
front of you, so "request_zoom" must be false in your reply."""

    buckets = "\n".join(
        f"- {colour}: {note}"
        for colour, note in COLOUR_BUCKETS.items()
        if any(colour in palette for palette in palettes.values())
    )

    questions = []
    for name, palette in palettes.items():
        description = CHANNEL_DESCRIPTIONS.get(name, f"their {name}")
        options = ", ".join(f'"{colour}"' for colour in palette)
        questions.append(
            f"{name} ({description}):\n"
            f"  1. Can you clearly see it in this photo? If it is hidden, out of\n"
            f"     frame, in deep shadow, or too small or blurred to judge, the\n"
            f'     answer is no and the colour is "{UNKNOWN}".\n'
            f"  2. Only if you can clearly see it, which of these is it?\n"
            f"     {options}\n"
            f'     If it is none of these, answer "{UNKNOWN}".'
        )

    return f"""You are looking at a photograph taken during a street game. A player \
has photographed someone in order to "shoot" them.

The photo has a thin red cross drawn across it -- one horizontal line and one \
vertical line, each spanning the whole image. The lines themselves are guides \
only, there to help you find the aim point -- IGNORE anything they merely pass \
over or touch elsewhere in the frame. The single pixel at the centre of the \
cross, where the two lines meet, is the exact spot the shot landed. Only what \
is at that one pixel matters.

Your job is to report what the person at the centre of the cross is wearing. \
Report only what you can actually see. Do not guess.

{zoom_paragraph}

{decision_rule}

If the shot hit a person, answer these questions about THAT PERSON ONLY. There \
are usually other people in the frame -- passers-by who are not in the game. \
Ignore everyone except the person the shot hit.

{chr(10).join(questions)}

Answering "{UNKNOWN}" is a correct and useful answer. It is much better than a \
guess: a wrong colour is worse than no colour. Give each answer a confidence \
between 0 and 1. Also give a single overall "confidence" between 0 and 1 for \
your reading of this photo as a whole.

Some colour names cover a range, so use these buckets:
{buckets}

Reply with JSON only, matching this shape:
{{
  "{HIT_FIELD}": true,
  "request_zoom": false,
  "reasoning": "one or two sentences on what you can and cannot see",
  "confidence": 0.9,
  "channels": {{
{_example_channels(palettes)}
  }}
}}"""


ZOOM_FOLLOW_UP = (
    "Here is the zoomed view: the middle 25% of the previous photograph, at "
    "higher resolution. The same red cross marks the same aim point, redrawn for "
    "this cropped view -- only its centre pixel counts as the hit, exactly as "
    "before. This is your one zoom, so answer in full now with the JSON described "
    'above. "request_zoom" must be false in your reply.'
)

# The second turn of the always-zoom path: the zoomed view, sent whether or not
# the model would have asked for it.
ZOOM_UPFRONT_TURN = (
    "Here is the zoomed view promised above: the middle 25% of the first "
    "photograph, at higher resolution, with the same red cross redrawn at the "
    "same aim point. Answer in full now with the JSON described above; "
    '"request_zoom" must be false in your reply.'
)


def _example_channels(palettes: Dict[str, List[str]]) -> str:
    lines = []
    for name, palette in palettes.items():
        lines.append(
            f'    "{name}": {{"visible": true, "colour": "{palette[0]}", '
            '"confidence": 0.9}'
        )
    return ",\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------


def parse_result(raw: dict, palettes: Optional[Dict[str, List[str]]] = None):
    """Validate a raw reply into a :class:`ShotVisionResult` (outcome not yet set).

    A colour outside a channel's own palette is an error, not something to
    coerce to the nearest legal value -- silently rewriting a model's answer
    would hide exactly the misreads worth knowing about.
    """
    palettes = palettes or channel_palettes()

    if not isinstance(raw, dict):
        raise ShotVisionError(f"expected a JSON object, got {type(raw).__name__}")

    person = raw.get(HIT_FIELD)
    if not isinstance(person, bool):
        raise ShotVisionError(f"'{HIT_FIELD}' must be true or false; got {person!r}")

    reasoning = raw.get("reasoning") or ""
    if not isinstance(reasoning, str):
        raise ShotVisionError(f"'reasoning' must be a string; got {reasoning!r}")

    confidence = _clamped_confidence(raw.get("confidence"))

    if not person:
        return ShotVisionResult(
            shot_hit_a_person=False,
            channels={name: ChannelRead(False, None, 0.0) for name in palettes},
            reasoning=reasoning,
            confidence=confidence,
        )

    raw_channels = raw.get("channels")
    if not isinstance(raw_channels, dict):
        raise ShotVisionError("'channels' must be an object when someone was hit")

    missing = set(palettes) - set(raw_channels)
    if missing:
        raise ShotVisionError(f"reply is missing channels: {sorted(missing)}")

    channels = {}
    for name, palette in palettes.items():
        channels[name] = _parse_channel(name, raw_channels[name], palette)

    return ShotVisionResult(
        shot_hit_a_person=True,
        channels=channels,
        reasoning=reasoning,
        confidence=confidence,
    )


def _clamped_confidence(raw_value) -> float:
    """The top-level confidence, clamped to [0, 1].

    Missing or unparseable becomes 0.0 rather than an error: a stored legacy
    review with no confidence field, or a model that ignores the request, must
    never look confident enough to auto-fire.
    """
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(value, 0.0), 1.0)


def _parse_channel(name: str, raw, palette: List[str]) -> ChannelRead:
    if not isinstance(raw, dict):
        raise ShotVisionError(f"channel {name!r}: expected an object, got {raw!r}")

    visible = bool(raw.get("visible"))
    colour = raw.get("colour")
    if colour is not None and not isinstance(colour, str):
        raise ShotVisionError(
            f"channel {name!r}: colour must be a string; got {colour!r}"
        )
    if isinstance(colour, str):
        colour = colour.strip().lower()

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        raise ShotVisionError(
            f"channel {name!r}: confidence must be a number; got {raw.get('confidence')!r}"
        )
    confidence = min(max(confidence, 0.0), 1.0)

    if not colour or colour == UNKNOWN:
        return ChannelRead(visible=visible, colour=None, confidence=confidence)

    if colour not in palette:
        raise ShotVisionError(
            f"channel {name!r}: {colour!r} is not one of its colours ({palette})"
        )

    if not visible:
        # The model named a colour but said it could not see the garment.
        # Believe the abstention: erasures are the cheap failure.
        logger.info(
            "Channel %s reported colour %r but visible=false; treating as unreadable",
            name,
            colour,
        )
        return ChannelRead(visible=False, colour=None, confidence=confidence)

    return ChannelRead(visible=True, colour=colour, confidence=confidence)


# ---------------------------------------------------------------------------
# Handing the reading to the identity module
# ---------------------------------------------------------------------------


def to_hard_symbols(result: ShotVisionResult, scheme=None) -> List[Optional[int]]:
    """Per-channel symbol indices in channel order, None for an erasure.

    A read below CONFIDENT_THRESHOLD is erased here, so everything downstream
    (:func:`classify`, :func:`_slot_of`) is confidence-aware.
    """
    scheme = scheme or default_scheme()
    symbols = []
    for channel in scheme.channels:
        read = result.channels.get(channel.name)
        if read is None or read.is_erasure or read.confidence < CONFIDENT_THRESHOLD:
            symbols.append(None)
        else:
            symbols.append(channel.label_to_index(read.colour))
    return symbols


def to_reading(result: ShotVisionResult, scheme=None) -> Reading:
    """The :class:`Reading` the soft decoder consumes (plan §8.1).

    Nothing calls this yet: identifying *which* player was hit needs the
    candidate set and the GPS prior, which are the next piece of work. It lives
    here so that piece is an addition rather than a rewrite.
    """
    scheme = scheme or default_scheme()
    observations = []
    for channel in scheme.channels:
        read = result.channels.get(channel.name)
        if read is None or read.is_erasure:
            observations.append(ChannelObservation.erasure())
        else:
            observations.append(
                ChannelObservation.best_guess(read.colour, read.confidence)
            )
    return Reading(observations)


def classify(result: ShotVisionResult, scheme=None) -> ShotVisionResult:
    """Decide the outcome from the observations, and set it on ``result``.

    Bystanders are common in these photos and bystanders do not wear armbands,
    so the armbands are the player marker. But armbands are also one of the four
    erasable channels, and plan §12.3 puts them out of view roughly a fifth of
    the time -- so "no armbands visible" cannot simply mean "not a player".
    The code covers that case instead:

    1. the shot did not land on anybody -> miss;
    2. armbands read -> a player, and a hit;
    3. armbands hidden, but the other three channels are all read and complete
       to exactly one assignable codeword -> a player, and a hit. With one
       erasure the [4,2,3] code has a check symbol left over, so a real outfit
       reconstructs and a passer-by's clothes generally do not;
    4. anything else -> a bystander, and not a hit.

    Step 3 must require *all three* others. With only two readable channels any
    reading completes to some codeword (``k = 2``), so the check would vouch for
    nothing -- see :meth:`IdentityScheme.codewords_matching`.
    """
    scheme = scheme or default_scheme()

    if not result.shot_hit_a_person:
        result.outcome = MISS
        result.outcome_reason = "the shot did not land on anybody"
        return result

    symbols = to_hard_symbols(result, scheme)
    armbands_index = scheme.channels.names.index("armbands")

    if symbols[armbands_index] is not None:
        result.outcome = HIT_PLAYER
        result.outcome_reason = "armbands visible"
        result.slot = _slot_of(scheme, symbols)
        return result

    others_readable = [
        symbol for i, symbol in enumerate(symbols) if i != armbands_index
    ]
    if any(symbol is None for symbol in others_readable):
        result.outcome = HIT_BYSTANDER
        result.outcome_reason = (
            "armbands hidden and too few other garments readable to check the code"
        )
        return result

    slot = _slot_of(scheme, symbols)
    if slot is not None:
        result.outcome = HIT_PLAYER
        result.outcome_reason = (
            "armbands hidden, but the other colours are a valid code"
        )
        result.slot = slot
        return result

    result.outcome = HIT_BYSTANDER
    result.outcome_reason = (
        "armbands hidden and the other colours are not a valid player code"
    )
    return result


def _candidate_slots(scheme, symbols: List[Optional[int]]) -> List[int]:
    """The assignable slots agreeing with ``symbols`` on its readable positions.

    Codewords nobody could be wearing do not count as an identification: ones a
    restricted channel cannot express, and the never-assigned all-black slot 0.
    """
    usable = set(scheme.usable_slots())
    return [
        slot
        for slot in (
            scheme.slot_of_codeword(codeword)
            for codeword in scheme.codewords_matching(symbols)
            if scheme.channels.is_representable(codeword)
        )
        if slot in usable
    ]


def _slot_of(scheme, symbols: List[Optional[int]]) -> Optional[int]:
    """The assignable slot these symbols identify, if they identify exactly one."""
    assignable = _candidate_slots(scheme, symbols)
    return assignable[0] if len(assignable) == 1 else None


def _stored_channel(review_dict: dict, channel):
    """``(colour, confidence)`` for one channel of a *stored* review payload.

    ``colour`` is None when the payload says nothing usable about the channel -
    a legacy payload, a missing entry, or a colour no longer in the palette.
    """
    stored = review_dict.get("channels")
    if not isinstance(stored, dict):
        return (None, 0.0)
    read = stored.get(channel.name)
    if not isinstance(read, dict):
        return (None, 0.0)
    colour = read.get("colour")
    confidence = _clamped_confidence(read.get("confidence"))
    if not isinstance(colour, str) or not channel.has_label(colour):
        return (None, 0.0)
    return (colour, confidence)


def confident_channel_count(review_dict: dict, scheme=None) -> int:
    """How many channels a *stored* review read at or above the confidence
    threshold -- i.e. how many the code would treat as readable rather than
    erased.

    Split out of :func:`slot_candidates_from_review` because the auto-action
    gate still wants this count even though identification no longer decodes
    against the code: with only ``k`` readable positions an MDS code matches
    some codeword for *any* reading, so a shakier read than that vouches for
    nothing, whoever it is scored against.
    """
    scheme = scheme or default_scheme()
    count = 0
    for channel in scheme.channels:
        colour, confidence = _stored_channel(review_dict, channel)
        if colour is not None and confidence >= CONFIDENT_THRESHOLD:
            count += 1
    return count


def reading_from_review(review_dict: dict, scheme=None) -> Reading:
    """The soft decoder's :class:`Reading`, rebuilt from a *stored* review.

    The counterpart of :func:`to_reading` for a payload that has been round
    tripped through the database. Unlike
    :func:`slot_candidates_from_review` this does **not** erase a channel for
    being read with low confidence: the soft decoder weights by confidence
    itself, and throwing the weak reads away before it sees them discards
    exactly the marginal evidence it is designed to use.
    """
    scheme = scheme or default_scheme()
    observations = []
    for channel in scheme.channels:
        colour, confidence = _stored_channel(review_dict, channel)
        if colour is None:
            observations.append(ChannelObservation.erasure())
        else:
            observations.append(ChannelObservation.best_guess(colour, confidence))
    return Reading(observations)


def slot_candidates_from_review(review_dict: dict, scheme=None) -> List[int]:
    """Candidate slots rebuilt from a *stored* review payload (``to_dict()``).

    Pure -- no database. The stored channel labels are mapped back to indices
    with the same low-confidence erasure rule as :func:`to_hard_symbols`, and
    anything unrecognisable (a legacy payload, a colour no longer in the
    palette) is erased rather than rejected: an unreadable stored review is
    merely ambiguous, and ambiguity is the safe answer.

    Requires at least ``k + 1`` readable channels, else returns ``[]``: with
    only ``k`` readable positions an MDS code always matches exactly one
    codeword and vouches for nothing (see
    :meth:`IdentityScheme.codewords_matching`). This is ``_slot_of``'s
    candidate list without the exactly-one collapse, so a geolocation prior
    can later re-rank the candidates via ``to_reading``/``decoder.decode``
    instead of rewriting this.
    """
    scheme = scheme or default_scheme()
    stored_channels = review_dict.get("channels")
    if not isinstance(stored_channels, dict):
        return []

    symbols: List[Optional[int]] = []
    for channel in scheme.channels:
        read = stored_channels.get(channel.name)
        colour = read.get("colour") if isinstance(read, dict) else None
        confidence = (
            _clamped_confidence(read.get("confidence"))
            if isinstance(read, dict)
            else 0.0
        )
        if (
            not isinstance(colour, str)
            or not channel.has_label(colour)
            or confidence < CONFIDENT_THRESHOLD
        ):
            symbols.append(None)
        else:
            symbols.append(channel.label_to_index(colour))

    readable = sum(1 for symbol in symbols if symbol is not None)
    if readable < scheme.code.k + 1:
        return []
    return _candidate_slots(scheme, symbols)


async def review_image(
    client,
    image_data_url: str,
    scheme=None,
    palettes=None,
    zoom_provider=None,
    prompt: Optional[str] = None,
    always_zoom: bool = False,
) -> ShotVisionResult:
    """Review one prepared image, allowing the model a single zoom.

    ``prompt`` overrides :func:`build_prompt` -- used by the offline replay
    harness (scripts/replay_shot_reviews.py) to trial prompt variants against
    saved shots; the live path leaves it as the default.

    ``zoom_provider`` is a zero-argument callable returning a magnified view of
    the shot. By default it is only invoked if the model asks for a zoom. It is
    a callable rather than a second image argument so the cost of producing the
    zoom is not paid on the shots that do not need it -- and so the caller can
    cut it from the *original* photo, which is the whole point (see
    :func:`~backend.image_processing.zoom_image`).

    With ``always_zoom`` the zoom stops being the model's choice: both views go
    in a single call and the reply is final. Roadmap #4's replay runs showed
    the model's self-assessed certainty does not track its accuracy -- it calls
    a close miss a hit at 0.95 confidence and never once asks for the zoom that
    makes the truth obvious -- so the harness trials this mode before the live
    path adopts it.

    The one-zoom limit is enforced here rather than trusted to the prompt.
    """
    palettes = palettes or channel_palettes()
    schema = build_schema(palettes)

    if always_zoom and zoom_provider is not None:
        turns = [
            {
                "role": "user",
                "text": (
                    prompt
                    if prompt is not None
                    else build_prompt(palettes, zoom_offered=False)
                ),
                "image_data_url": image_data_url,
            },
            {
                "role": "user",
                "text": ZOOM_UPFRONT_TURN,
                "image_data_url": zoom_provider(),
            },
        ]
        # One call, both views: whatever comes back is the answer.
        raw = await client.complete(turns, schema)
        result = classify(parse_result(raw, palettes), scheme)
        result.zoom_used = True
        return result

    turns = [
        {
            "role": "user",
            "text": prompt if prompt is not None else build_prompt(palettes),
            "image_data_url": image_data_url,
        }
    ]

    raw = await client.complete(turns, schema)

    zoom_used = False
    if wants_zoom(raw) and zoom_provider is not None:
        logger.info("Vision model asked for a zoom; sending the magnified centre")
        zoom_used = True
        turns = turns + [
            {"role": "assistant", "text": json.dumps(raw)},
            {
                "role": "user",
                "text": ZOOM_FOLLOW_UP,
                "image_data_url": zoom_provider(),
            },
        ]
        # Whatever comes back now is the answer: the model has had its one look.
        raw = await client.complete(turns, schema)
    elif wants_zoom(raw):
        logger.warning("Vision model asked for a zoom but none is available")

    result = classify(parse_result(raw, palettes), scheme)
    result.zoom_used = zoom_used
    return result
