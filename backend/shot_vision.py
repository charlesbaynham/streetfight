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

**Too little read is not a verdict.** :func:`classify` used to route "armbands
hidden and the other garments do not complete to a codeword" to
``HIT_BYSTANDER``; that mapping is retired (roadmap #11), because it produced
every one of #4's residual false misses. A hit on a person is now always
``HIT_PLAYER`` and the reading is handed on for what it is worth: with fewer
readable channels, identification is simply less confident, and
:mod:`backend.shot_escalation` -- or the admin -- is where an unconfident case
goes. Bystander survives as a *conclusion* the stronger model or a human can
reach, never as the route taken because too little was legible.

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

from .identity.config import DEFAULT_CHANNEL_NAMES
from .identity.config import DEFAULT_THRESHOLDS
from .identity.config import buckets_for_channel
from .identity.config import default_scheme
from .identity.config import hex_for
from .identity.config import palette_for_channel
from .identity.observations import ChannelObservation
from .identity.observations import Reading

logger = logging.getLogger(__name__)

UNKNOWN = "unknown"

# The one garment the game itself hands out, so the one whose colour says the
# person is playing at all. Nothing here gates on it any more (see
# :func:`classify`), but the escalation ladder still asks whether it was read.
ARMBANDS_CHANNEL = "armbands"

# A channel read below this confidence is treated as an erasure, exactly like
# not-visible/unknown: the code corrects two erasures but only one misread, so
# a shaky colour is worth less than an honest abstention. The same constant
# gates the auto-actions in backend.shot_auto_actions.
CONFIDENT_THRESHOLD = DEFAULT_THRESHOLDS.confident_threshold

# The reply field carrying "did the shot land on a person". Note that is not
# "is somebody standing at the centre": clothing, hands and shoes all count, and
# only a shot that entirely misses the person is a miss.
HIT_FIELD = "shot_hit_a_person"

ZOOM_FACTOR = 8

# The first question the model answers, before anything else: does the person
# fill less than half of the screen? That answer -- not the model's
# self-assessed certainty -- decides whether the zoom is spent. Replay trials
# (roadmap #4) showed the model calls a close miss a hit at 0.95 confidence and
# never once asks for the zoom that makes the truth obvious, so the choice is
# framed as something it can actually see: how big the person is.
SCREENING_FIELD = "person_fills_less_than_half"

# The zoom may be spent at most this many times on one shot: the screening
# question is asked on the full frame and repeated on the first zoom, and a
# target still small after that gets one final, closer view.
MAX_ZOOMS = 2

# The shape of the conversation -- which is not a detail of the prompt's
# wording but of the exchange itself, so the prompt, the schemas asked for and
# the follow-up turns all follow from it together. The live pipeline runs
# SCREENED; the other two exist for the replay harness and the admin workbench.
#
# - SCREENED: turn one asks only the screening question, and that answer
#   decides whether the next turn carries a zoomed view.
# - UPFRONT: the full frame and the first zoom go together in one call.
# - SINGLE: one turn, one image, no screening and no zoom -- the shape to pick
#   when trialling a prompt that asks for something else entirely, since then
#   nothing but the prompt and its schema governs what comes back.
ZOOM_SCREENED = "screened"
ZOOM_UPFRONT = "upfront"
ZOOM_SINGLE = "single"
ZOOM_MODES = (ZOOM_SCREENED, ZOOM_UPFRONT, ZOOM_SINGLE)

# Outcomes. Only HIT_PLAYER counts against a player's hit points. Shown to the
# admin as advice -- and, when a game's AI-review toggle is on, acted on for the
# head of the queue by backend.shot_auto_actions when confident enough.
#
# classify() no longer emits HIT_BYSTANDER (see the module docstring): the
# constant stays because reviews stored before roadmap #11 carry the string,
# the queue renders a label for it, the replay harness scores against it, and
# the escalated verdict maps onto it.
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
        zoom_count: int = 0,
        transcript: Optional[List[dict]] = None,
        raw_reply: Optional[dict] = None,
        parse_error: Optional[str] = None,
    ):
        self.shot_hit_a_person = shot_hit_a_person
        self.channels = channels
        self.reasoning = reasoning
        self.outcome = outcome
        self.outcome_reason = outcome_reason
        self.slot = slot
        self.confidence = confidence
        self.zoom_used = zoom_used
        # How many times the zoom was actually spent (0..MAX_ZOOMS). zoom_used
        # is kept alongside it as the boolean shorthand existing callers rely
        # on; this is the same fact, just not collapsed to a bool.
        self.zoom_count = zoom_count
        # Every request/reply exchanged with the model, for the admin replay
        # workbench. None on a live review -- see to_dict's include_transcript.
        self.transcript = transcript
        # Set only when a workbench replay asked for a contract of its own and
        # the answer therefore has no reading to parse: the reply as it landed,
        # and why it could not be read as one. Both stay None everywhere else,
        # so a live review's stored payload never grows them.
        self.raw_reply = raw_reply
        self.parse_error = parse_error

    @property
    def is_hit(self) -> bool:
        return self.outcome == HIT_PLAYER

    def to_dict(self, include_transcript: bool = False) -> dict:
        """The JSON stored on the Shot and rendered as tags in the queue.

        ``include_transcript`` adds every turn exchanged with the model --
        omitted by default so a live review's stored payload does not carry it
        on every shot; the admin replay workbench (nothing it returns is
        stored) asks for it explicitly.
        """
        result = {
            "shot_hit_a_person": self.shot_hit_a_person,
            "confidence": self.confidence,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "is_hit": self.is_hit,
            "slot": self.slot,
            "reasoning": self.reasoning,
            "zoom_used": self.zoom_used,
            "zoom_count": self.zoom_count,
            "channels": {
                name: dict(read.to_dict(), hex=hex_for(name, read.colour))
                for name, read in self.channels.items()
            },
        }
        if include_transcript:
            result["transcript"] = self.transcript or []
        if self.parse_error is not None:
            result["parse_error"] = self.parse_error
            result["raw_reply"] = self.raw_reply
        return result


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
        "required": [HIT_FIELD, "reasoning", "confidence", "channels"],
        "additionalProperties": False,
    }


def build_screening_schema() -> dict:
    """The first turn's schema: the screening question and nothing else.

    Asking for it through the reply rather than a provider tool-call API:
    OPENROUTER_MODEL is meant to be swapped freely, and a boolean in the JSON
    works on every model.
    """
    return {
        "type": "object",
        "properties": {SCREENING_FIELD: {"type": "boolean"}},
        "required": [SCREENING_FIELD],
        "additionalProperties": False,
    }


def screening_requests_zoom(raw) -> bool:
    """Whether a first-turn reply says the person fills less than half the screen.

    Checked *before* :func:`parse_result`, because a screening reply has not
    filled in the channels yet and ``parse_result`` is right to reject one.
    Anything but an explicit true means no zoom -- including a model that
    skipped the screening and answered in full, which the caller accepts as-is.
    """
    return isinstance(raw, dict) and raw.get(SCREENING_FIELD) is True


_HIT_TEST = f"""Did the shot hit a person? If the centre of the cross is on empty ground, \
a wall, foliage, the sky, or nobody in particular, set "{HIT_FIELD}" to false -- \
even if one of the red lines passes over or right next to a person elsewhere in \
the frame. The lines themselves are not the hit; only their centre point is."""

_ZOOM_UPFRONT_SENTENCES = """You MUST ultimately make a decision on whether the \
shot is hitting a person or not -- the zoomed view is already in front of you \
for exactly that."""

_HIT_DEFINITION = """It is a hit only if the centre of the cross itself lands on \
the person -- on their clothing, hands, or shoes. It is a miss if the centre \
point is on the background instead -- ground, a wall, foliage, a street light \
-- even if that background is right beside them."""

DEFAULT_DECISION_RULE = f"{_HIT_TEST}\n\n{_HIT_DEFINITION}"

# The same rule for when the zoom is provided up front rather than gated on the
# screening question: identical except that there is nothing left to ask for.
UPFRONT_ZOOM_DECISION_RULE = (
    f"{_HIT_TEST}\n\n{_ZOOM_UPFRONT_SENTENCES} {_HIT_DEFINITION}"
)


def build_prompt(
    palettes: Optional[Dict[str, List[str]]] = None,
    decision_rule: Optional[str] = None,
    zoom_mode: str = ZOOM_SCREENED,
) -> str:
    """The instructions sent alongside the photo.

    ``decision_rule`` is the paragraph(s) telling the model how to turn the
    cross's position into a hit/miss call -- pulled out as a parameter so
    roadmap #4's prompt variants (``scripts/replay_shot_reviews.py``) can swap
    it without duplicating the rest of the template (channel questions,
    colour buckets, JSON shape).

    ``zoom_mode`` must match the shape of the conversation
    :func:`review_image` is about to run (see the ``ZOOM_*`` constants): the
    wording explaining the zoom is part of the prompt, so a prompt written for
    one shape and sent into another tells the model it is about to be shown
    something it will not be.
    """
    palettes = palettes or channel_palettes()
    if decision_rule is None:
        decision_rule = (
            UPFRONT_ZOOM_DECISION_RULE
            if zoom_mode == ZOOM_UPFRONT
            else DEFAULT_DECISION_RULE
        )

    if zoom_mode == ZOOM_SCREENED:
        zoom_paragraph = f"""FIRST, before any of the questions below: does the person at \
the centre of the cross fill less than half of the screen? Reply to this \
message with {{"{SCREENING_FIELD}": true}} or {{"{SCREENING_FIELD}": false}} \
and nothing else. If they fill less than half, your reply is discarded and \
the next turn shows you a zoomed-in view of the middle of the photograph at \
higher resolution, and asks you the same question again -- a still-smaller \
target gets one final, closer view. Once the person fills at least half of \
the screen, or the zooms run out, you answer in full."""
    elif zoom_mode == ZOOM_UPFRONT:
        zoom_paragraph = """You are shown this photograph twice: the first image is the whole frame, and \
the second is a zoomed-in view containing only the middle 12.5% of it in higher \
resolution, with the same red cross redrawn at the same aim point -- only its \
centre pixel counts, exactly as in the full frame. Use whichever view is \
clearer, and trust the zoomed one when they disagree."""
    else:
        # ZOOM_SINGLE: one image, so there is no zoom to promise and none to
        # ask for.
        zoom_paragraph = """You are shown this photograph once, as the whole frame. There is no \
zoomed view and no closer look to ask for: judge it from what you have."""

    questions = []
    for name, palette in palettes.items():
        description = CHANNEL_DESCRIPTIONS.get(name, f"their {name}")
        options = ", ".join(f'"{colour}"' for colour in palette)
        # Per channel, not once for the whole prompt: the channels do not share
        # a vocabulary, and where they use the same word they can mean different
        # things by it (charcoal is "black" on the legs and not on a top).
        notes = "".join(
            f"\n       {colour}: {note}"
            for colour, note in buckets_for_channel(name).items()
        )
        if notes:
            notes = f"\n     Some of these cover a range:{notes}"
        questions.append(
            f"{name} ({description}):\n"
            f"  1. Can you clearly see it in this photo? If it is hidden, out of\n"
            f"     frame, in deep shadow, or too small or blurred to judge, the\n"
            f'     answer is no and the colour is "{UNKNOWN}".\n'
            f"  2. Only if you can clearly see it, which of these is it?\n"
            f"     {options}"
            f"{notes}\n"
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

Reply with JSON only, matching this shape:
{{
  "{HIT_FIELD}": true,
  "reasoning": "one or two sentences on what you can and cannot see",
  "confidence": 0.9,
  "channels": {{
{_example_channels(palettes)}
  }}
}}"""


# The turn after a zoom while a further zoom is still available: the screening
# question is repeated on the closer view.
ZOOM_FOLLOW_UP = (
    "Here is another image: the middle 12.5% of the previous one, at higher "
    "resolution. The same red cross marks the same aim point, redrawn for this "
    "cropped view -- only its centre pixel counts as the hit, exactly as "
    "before. Answer the same question again for this view: does the person now "
    f'fill less than half of the screen? Reply with {{"{SCREENING_FIELD}": '
    f'true}} or {{"{SCREENING_FIELD}": false}} and nothing else. If they still '
    "fill less than half, you will be shown one final, closer view; otherwise "
    "you will be asked to answer in full."
)

# The turn after the last zoom: no further views, so the full reading is due.
ZOOM_FINAL_FOLLOW_UP = (
    "Here is the final view: the middle 12.5% of the previous one, closer "
    "still, with the same red cross redrawn at the same aim point -- only its "
    "centre pixel counts, exactly as before. There are no more zooms. Answer "
    "in full now with the JSON described above."
)

# The second turn when the person fills at least half the screen: no zoom, just
# the request for the full reading.
FULL_READING_REQUEST = (
    "The person fills at least half of the screen, so the photograph you "
    "already have is enough. Now answer in full with the JSON described above."
)

# The second turn of the always-zoom path: the zoomed view, sent whether or not
# the screening would have asked for it.
ZOOM_UPFRONT_TURN = (
    "Here is the zoomed view promised above: the middle 12.5% of the first "
    "photograph, at higher resolution, with the same red cross redrawn at the "
    "same aim point. Answer in full now with the JSON described above."
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

    There are only two outcomes left here:

    1. the shot did not land on anybody -> miss;
    2. it landed on somebody -> a hit on a player, whatever was readable.

    The old rule used the armbands as the player gate -- armbands read means a
    player, armbands hidden means demand that the other three complete to a
    codeword, else bystander -- and it was wrong in the direction that costs a
    player a life they earned: plan §12.3 puts the armbands out of view roughly
    a fifth of the time, and all four of roadmap #4's residual false misses were
    exactly that case. Nothing about what we could *read* tells us whether the
    person is playing.

    So a reading with two or three legible garments is no longer discarded; it
    is passed on as what it is, an honestly weaker identification
    (:mod:`backend.shot_identification` scores it against a handful of living
    candidates rather than the whole code space), and
    :mod:`backend.shot_escalation` runs the ladder that decides whether it is
    good enough to act on. ``outcome_reason`` records what was legible so the
    admin queue can say why a shot went up the ladder.

    ``slot`` is still set when the symbols pick out exactly one assignable slot
    -- a harmless annotation for a canonically-dressed player, and often None
    now that fewer channels are demanded.
    """
    scheme = scheme or default_scheme()

    if not result.shot_hit_a_person:
        result.outcome = MISS
        result.outcome_reason = "the shot did not land on anybody"
        return result

    symbols = to_hard_symbols(result, scheme)
    result.outcome = HIT_PLAYER
    result.outcome_reason = _readability_reason(scheme, symbols)
    result.slot = _slot_of(scheme, symbols)
    return result


def _readability_reason(scheme, symbols: List[Optional[int]]) -> str:
    """ "read 3 of 4 garments confidently (armbands hidden)" -- what the reading
    is worth, in the words the admin queue shows."""
    hidden = [
        channel.name
        for channel, symbol in zip(scheme.channels, symbols)
        if symbol is None
    ]
    read = len(symbols) - len(hidden)
    reason = f"read {read} of {len(symbols)} garments confidently"
    if hidden:
        reason += f" ({', '.join(hidden)} hidden)"
    return reason


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


def readable_channel_count(review_dict: dict, scheme=None) -> int:
    """How many channels a *stored* review says anything usable about at all.

    The softer count: a shaky read still moves a posterior, so this asks only
    whether the channel was read, not whether it was read well. Zero means the
    reading is entirely erasures and carries **no** image evidence -- whatever
    a ranking built on it comes back with is its prior handed straight back,
    which is a thing to say "retake the photograph" about rather than a
    recognition (backend.reference_photos).
    """
    scheme = scheme or default_scheme()
    return sum(
        1
        for channel in scheme.channels
        if _stored_channel(review_dict, channel)[0] is not None
    )


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


def armbands_confident(review_dict: dict, scheme=None) -> bool:
    """Whether a *stored* review read the armbands at or above the threshold.

    The armbands are the one garment the game hands out, so reading them is
    what makes player-ness solid rather than inferred -- which is why the
    escalation ladder (backend.shot_auto_actions) treats three channels with
    the armbands among them differently from three without.
    """
    scheme = scheme or default_scheme()
    for channel in scheme.channels:
        if channel.name != ARMBANDS_CHANNEL:
            continue
        colour, confidence = _stored_channel(review_dict, channel)
        return colour is not None and confidence >= CONFIDENT_THRESHOLD
    return False


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
    zoom_mode: str = ZOOM_SCREENED,
    schema: Optional[dict] = None,
    tolerate_unparsed: bool = False,
) -> ShotVisionResult:
    """Review one prepared image, spending the zoom only on a small target.

    ``prompt`` overrides :func:`build_prompt` and ``schema`` overrides
    :func:`build_schema` -- used by the offline replay harness
    (scripts/replay_shot_reviews.py) and the admin workbench to trial variants
    against saved shots; the live path leaves both as the default. They are two
    halves of one contract: a reply's *shape* is fixed by the schema the model
    is asked for, so a custom prompt without a matching schema is asked a new
    question and made to answer the old one.

    ``tolerate_unparsed`` returns a reply that is not a standard reading as
    :attr:`ShotVisionResult.raw_reply` instead of raising -- for the workbench,
    where seeing what the model actually said is the whole point. A live review
    leaves it off: storing a meaningless verdict is worse than erroring.

    ``zoom_provider`` is a callable taking the zoom level (1, 2, ...) and
    returning a magnified view of the shot, so each further zoom compounds the
    factor against the *original* photo. It is a callable rather than an image
    argument so the cost of producing a zoom is not paid on the shots that do
    not need it -- and so the caller can cut it from the original photo, which
    is the whole point (see :func:`~backend.image_processing.zoom_image`).

    The default flow: turn one asks only the screening question -- does the
    person fill less than half of the screen? -- and the reply decides turn
    two. A small target gets the zoomed view and the question is repeated
    there, allowing one further zoom (``MAX_ZOOMS`` in total); anything else is
    asked for the full reading. Screening replies are discarded; a model that
    skips the screening and answers in full is accepted as-is.

    ``zoom_mode`` picks the shape of the exchange (see the ``ZOOM_*``
    constants). ZOOM_UPFRONT puts the full frame and the first zoom in a single
    call, the reply being final; ZOOM_SINGLE is one turn with one image and no
    screening at all, so the prompt and its schema are the only thing that
    decides what comes back. Both are kept for the replay harness's comparison
    runs and the workbench; the live path runs ZOOM_SCREENED.
    """
    palettes = palettes or channel_palettes()
    schema = schema if schema is not None else build_schema(palettes)
    opening = (
        prompt if prompt is not None else build_prompt(palettes, zoom_mode=zoom_mode)
    )

    def finalise(raw) -> ShotVisionResult:
        return _reading_or_raw(raw, palettes, scheme, tolerate_unparsed)

    if zoom_mode == ZOOM_UPFRONT and zoom_provider is not None:
        turns = [
            {
                "role": "user",
                "text": opening,
                "image_data_url": image_data_url,
            },
            {
                "role": "user",
                "text": ZOOM_UPFRONT_TURN,
                "image_data_url": _call_zoom_provider(zoom_provider, 1),
            },
        ]
        # One call, both views: whatever comes back is the answer.
        raw = await client.complete(turns, schema)
        result = finalise(raw)
        result.zoom_used = True
        result.zoom_count = 1
        result.transcript = [_transcript_turn(turn) for turn in turns] + [
            _assistant_turn(raw, client)
        ]
        return result

    turns = [
        {
            "role": "user",
            "text": opening,
            "image_data_url": image_data_url,
        }
    ]

    if zoom_mode == ZOOM_SINGLE:
        # Nothing to screen for and nothing to follow up: one turn, answered
        # against whatever contract the caller asked for.
        raw = await client.complete(turns, schema)
        result = finalise(raw)
        result.transcript = [_transcript_turn(turns[0]), _assistant_turn(raw, client)]
        return result

    raw = await client.complete(turns, build_screening_schema())
    zooms_used = 0
    transcript = [_transcript_turn(turns[0]), _assistant_turn(raw, client)]
    reasoning_details = client.last_reasoning_details

    while not _answered_in_full(raw):
        if (
            screening_requests_zoom(raw)
            and zoom_provider is not None
            and zooms_used < MAX_ZOOMS
        ):
            zooms_used += 1
            logger.info(
                "Target fills less than half the screen; sending zoom %s/%s",
                zooms_used,
                MAX_ZOOMS,
            )
            final_turn = zooms_used == MAX_ZOOMS
            follow_up = {
                "role": "user",
                "text": ZOOM_FINAL_FOLLOW_UP if final_turn else ZOOM_FOLLOW_UP,
                "image_data_url": _call_zoom_provider(zoom_provider, zooms_used),
            }
        else:
            if screening_requests_zoom(raw):
                logger.warning("Target is small but no further zoom is available")
            follow_up = {"role": "user", "text": FULL_READING_REQUEST}
            final_turn = True

        turns = turns + [
            _previous_answer_turn(raw, reasoning_details),
            follow_up,
        ]
        transcript.append(_transcript_turn(follow_up))
        raw = await client.complete(
            turns, schema if final_turn else build_screening_schema()
        )
        reasoning_details = client.last_reasoning_details
        transcript.append(_assistant_turn(raw, client))
        if final_turn:
            # Whatever comes back now is the answer.
            break

    result = finalise(raw)
    result.zoom_used = zooms_used > 0
    result.zoom_count = zooms_used
    result.transcript = transcript
    return result


def _reading_or_raw(raw, palettes, scheme, tolerate_unparsed: bool):
    """The parsed reading -- or, for a workbench replay whose prompt asked for
    something else, the reply exactly as it landed.

    A reply in another shape is not an error there: it is the answer to the
    question that was actually asked, and showing it is what the workbench is
    for. Everywhere else it stays an error, so nothing meaningless is stored.
    """
    try:
        return classify(parse_result(raw, palettes), scheme)
    except ShotVisionError as e:
        if not tolerate_unparsed:
            raise
        return ShotVisionResult(
            shot_hit_a_person=False,
            channels={name: ChannelRead(False, None, 0.0) for name in palettes},
            outcome_reason=f"Reply did not match the standard reading: {e}",
            raw_reply=raw if isinstance(raw, dict) else {"reply": raw},
            parse_error=str(e),
        )


def _call_zoom_provider(provider, level: int) -> str:
    """Call a zoom provider with backward-compat for zero-arg test lambdas."""
    try:
        return provider(level)
    except TypeError:
        return provider()


def _transcript_turn(turn: dict) -> dict:
    """One user turn for the admin replay workbench's transcript.

    The conversation is append-only -- nothing sent earlier is ever revised --
    so the transcript is a single flat, chronological list rather than a
    snapshot of the cumulative turns replayed on every call: that would show
    the same early turns over and over, once per later exchange. The image is
    reduced to a marker rather than its data URL -- the workbench already
    renders the actual images via admin_get_shot_vision_images, and a
    transcript entry would otherwise carry the same base64 photo repeatedly.
    """
    return {
        "role": turn["role"],
        "text": turn["text"],
        "has_image": bool(turn.get("image_data_url")),
    }


def _previous_answer_turn(raw: dict, reasoning_details: Optional[List[dict]]) -> dict:
    """The prior reply, as the assistant turn fed back into the next call.

    Carries ``reasoning_details`` (see :attr:`~backend.vision_client.
    VisionClient.last_reasoning_details`) when the model returned any --
    without it, a "thinking" model has no way to continue reasoning from the
    screening turn and instead starts over from nothing but this bare JSON
    answer, which measurably degrades the quality of the turns that follow
    (this is what the zoom follow-ups above are for).
    """
    turn = {"role": "assistant", "text": json.dumps(raw)}
    if reasoning_details:
        turn["reasoning_details"] = reasoning_details
    return turn


def _assistant_turn(raw: dict, client) -> dict:
    """One assistant turn for the transcript: the parsed reply, plus the
    model's own extended-thinking trace when the provider returned one
    (``client.last_reasoning`` -- OpenRouter's unified reasoning tokens).

    Distinct from ``raw["reasoning"]``, the short field the model fills in as
    part of the reply itself.
    """
    return {
        "role": "assistant",
        "reply": raw,
        "reasoning": client.last_reasoning,
    }


def _answered_in_full(raw) -> bool:
    """Whether a reply skipped the screening and gave the full reading."""
    return isinstance(raw, dict) and HIT_FIELD in raw and SCREENING_FIELD not in raw
