"""Reading a shot photo: the prompt, the response contract, and the verdict.

This is the vision *adapter* from the design brief (plan §8.1). It sits between
:mod:`backend.vision_client` (which just moves bytes) and
:mod:`backend.identity` (which is pure and knows nothing about photographs).

Two principles run through it:

**The model observes; Python decides.** The model is never asked "was this a
hit". It is asked, per channel, whether the garment is clearly visible and if so
what colour it is. :func:`classify` turns those observations into an outcome, so
the rule lives somewhere tests can pin it down and does not drift when the model
behind ``OPENROUTER_MODEL`` changes.

**An erasure is cheaper than a misread.** The code corrects two erasures but
only one misread (``d >= 2t + e + 1``), so "unknown" is offered for every
channel and the prompt asks about visibility before colour. Measured (plan
§12.1): without that, a model converts "I cannot see it" into a confident wrong
colour, which is the expensive failure.
"""

import logging
from typing import Dict
from typing import List
from typing import Optional

from .identity.config import COLOUR_BUCKETS
from .identity.config import DEFAULT_CHANNEL_NAMES
from .identity.config import default_scheme
from .identity.config import hex_for
from .identity.config import palette_for_channel
from .identity.observations import ChannelObservation
from .identity.observations import Reading

logger = logging.getLogger(__name__)

UNKNOWN = "unknown"

# Outcomes. Only HIT_PLAYER counts against a player's hit points -- and nothing
# acts on these yet, they are shown to the admin as advice.
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
        person_at_aim_point: bool,
        channels: Dict[str, ChannelRead],
        reasoning: str = "",
        outcome: str = MISS,
        outcome_reason: str = "",
        slot: Optional[int] = None,
    ):
        self.person_at_aim_point = person_at_aim_point
        self.channels = channels
        self.reasoning = reasoning
        self.outcome = outcome
        self.outcome_reason = outcome_reason
        self.slot = slot

    @property
    def is_hit(self) -> bool:
        return self.outcome == HIT_PLAYER

    def to_dict(self) -> dict:
        """The JSON stored on the Shot and rendered as tags in the queue."""
        return {
            "person_at_aim_point": self.person_at_aim_point,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "is_hit": self.is_hit,
            "slot": self.slot,
            "reasoning": self.reasoning,
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
            "person_at_aim_point": {"type": "boolean"},
            "reasoning": {"type": "string"},
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
        "required": ["person_at_aim_point", "reasoning", "channels"],
        "additionalProperties": False,
    }


def build_prompt(palettes: Optional[Dict[str, List[str]]] = None) -> str:
    """The instructions sent alongside the photo."""
    palettes = palettes or channel_palettes()

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
has photographed someone in order to "shoot" them. The crosshair marks where the \
shot landed.

Your job is to report what the person at the crosshair is wearing. Report only \
what you can actually see. Do not guess.

FIRST: is there a person at the crosshair at all? If the crosshair is on empty \
ground, a wall, the sky, or nobody in particular, set "person_at_aim_point" to \
false and stop there.

If there is a person at the crosshair, answer these questions about THAT PERSON \
ONLY. There are usually other people in the frame -- passers-by who are not in \
the game. Ignore everyone except the person at the crosshair.

{chr(10).join(questions)}

Answering "{UNKNOWN}" is a correct and useful answer. It is much better than a \
guess: a wrong colour is worse than no colour. Give each answer a confidence \
between 0 and 1.

Some colour names cover a range, so use these buckets:
{buckets}

Reply with JSON only, matching this shape:
{{
  "person_at_aim_point": true,
  "reasoning": "one or two sentences on what you can and cannot see",
  "channels": {{
{_example_channels(palettes)}
  }}
}}"""


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

    person = raw.get("person_at_aim_point")
    if not isinstance(person, bool):
        raise ShotVisionError(
            f"'person_at_aim_point' must be true or false; got {person!r}"
        )

    reasoning = raw.get("reasoning") or ""
    if not isinstance(reasoning, str):
        raise ShotVisionError(f"'reasoning' must be a string; got {reasoning!r}")

    if not person:
        return ShotVisionResult(
            person_at_aim_point=False,
            channels={name: ChannelRead(False, None, 0.0) for name in palettes},
            reasoning=reasoning,
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
        person_at_aim_point=True, channels=channels, reasoning=reasoning
    )


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
    """Per-channel symbol indices in channel order, None for an erasure."""
    scheme = scheme or default_scheme()
    symbols = []
    for channel in scheme.channels:
        read = result.channels.get(channel.name)
        if read is None or read.is_erasure:
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

    1. nobody at the aim point -> miss;
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

    if not result.person_at_aim_point:
        result.outcome = MISS
        result.outcome_reason = "nobody at the aim point"
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


def _slot_of(scheme, symbols: List[Optional[int]]) -> Optional[int]:
    """The assignable slot these symbols identify, if they identify exactly one.

    Codewords nobody could be wearing do not count as an identification: ones a
    restricted channel cannot express, and the never-assigned all-black slot 0.
    """
    usable = set(scheme.usable_slots())
    assignable = [
        slot
        for slot in (
            scheme.slot_of_codeword(codeword)
            for codeword in scheme.codewords_matching(symbols)
            if scheme.channels.is_representable(codeword)
        )
        if slot in usable
    ]
    return assignable[0] if len(assignable) == 1 else None


async def review_image(
    client, image_data_url: str, scheme=None, palettes=None
) -> ShotVisionResult:
    """Send one prepared image to the model and return the classified result."""
    palettes = palettes or channel_palettes()
    raw = await client.complete(
        image_data_url=image_data_url,
        prompt=build_prompt(palettes),
        schema=build_schema(palettes),
    )
    return classify(parse_result(raw, palettes), scheme)
