"""The declarative initial configuration and a ``default_scheme()`` factory.

Changing the initial setup = editing **this one file**: add a colour to a
palette, add a :class:`Channel`, or switch the code to
:func:`reed_solomon_code`. Nothing in :mod:`backend.identity.decoder`,
:mod:`~backend.identity.scheme`, or :mod:`~backend.identity.channels` needs to
change -- that is the extensibility guarantee.

The values here are the ones chosen in ``docs/team_photo_identification_plan.md``
§9.1, selected by optimising the worst-case minimum CIEDE2000 distance across
daylight, warm-white LED and high-pressure sodium illuminants. The palettes are
still subject to live camera testing with the real hardware (plan §9), so keep
swapping a colour a one-line change here.
"""

from backend.identity.channels import Channel
from backend.identity.channels import ChannelSet
from backend.identity.code import build_code
from backend.identity.decoder import DecoderThresholds
from backend.identity.scheme import IdentityScheme

# The main palette, worn on t-shirt / hat / armbands. Seven colours, so q = 7
# (prime, which the dependency-free GF(q) arithmetic requires), and 7**2 = 49
# codewords.
DEFAULT_PALETTE = ["black", "purple", "red", "blue", "green", "orange", "yellow"]

# Trousers, also seven -- the whole point of widening this channel (plan §2.6:
# it carried five, which capped the scheme at 35 wearable slots, and the guest
# list outgrew that). It differs from the main palette in exactly one place:
# symbol 6 is **white** rather than yellow.
#
# That swap is what lets white live here at all. §9.1 excluded white from the
# main palette on measurement, not on sourcing -- it reflects whatever light
# hits it, so under sodium street lighting a white garment photographs orange,
# and white/yellow collapsed to ΔE 14. Merging the two into one symbol dissolves
# that pair: a channel cannot confuse two colours it calls by the same name.
# Cream, beige, chinos and yellow trousers are all "white" here, which is both
# what the guest instructions say and what the vision prompt asks for (see
# COLOUR_BUCKETS below -- and keep the two in step, since the deterministic
# decoding downstream assumes a player and the model mean the same thing by a
# colour name).
#
# It buys real wardrobe coverage: white/cream/beige is the third most commonly
# owned trousers colour (COLOUR_COMMONNESS below), and chinos are exactly what
# a guest reaches for when their jeans are all blue or black. What it does not
# fix is white against *orange*, which this channel does carry: that pair is one
# misread, in one channel, which d = 3 corrects outright.
TROUSERS_PALETTE = ["black", "purple", "red", "blue", "green", "orange", "white"]

# The field cardinality. Must be prime, and must be at least the size of the
# largest channel alphabet.
DEFAULT_Q = 7

# The wearable channels (slots), in the order the code evaluates them.
# Add/remove/reorder here -- e.g. a "shape" channel with a shape alphabet.
DEFAULT_CHANNEL_NAMES = ["tshirt", "trousers", "hat", "armbands"]

# Channels with an alphabet of their own; anything not listed uses
# DEFAULT_PALETTE. Only the *cardinality* reaches the code, so a channel here
# may carry a different physical set (trousers) or fewer labels than ``q``,
# which makes the codewords it cannot wear unassignable
# (``ChannelSet.is_representable``). A channel listed here may also give its own
# shades in PALETTE_HEX under the same name, for the colours that differ.
CHANNEL_PALETTES = {"trousers": TROUSERS_PALETTE}

# The channel spent on telling teams apart by eye: every member of a team is
# pre-allocated a slot with the same colour here, and no two teams share one
# (see backend/identity/allocation.py). The hat, because it is the highest and
# least likely garment to be obscured, and the easiest single item to hand out
# in a matching colour. Purely an allocation policy -- the decoder neither
# knows nor cares.
TEAM_CHANNEL = "hat"

# The channel we hand out at the gate (roadmap #9), and therefore choose
# ourselves rather than leaving to a guest's wardrobe. Together with
# TEAM_CHANNEL that makes the "wardrobe questions" -- the channels a player's
# own clothes must answer -- exactly ``channels - {TEAM_CHANNEL,
# PROVIDED_CHANNEL}``.
PROVIDED_CHANNEL = "armbands"

# The minimum distance the code must achieve. d = 3 over 4 channels gives the
# [4,2,3] Reed-Solomon code: correct two erasures, or one misread, or one
# erasure plus detect one misread. See the upgrade ladder in
# :func:`scheme_with_distance`.
DEFAULT_TARGET_DISTANCE = 3

# The hex each colour name refers to, so the admin UI, any printable guest sheet
# and the palette design all read from one place. Keyed by palette name: a
# channel with its own alphabet lists only the shades that *differ*, and falls
# back to "main" for the rest.
PALETTE_HEX = {
    "main": {
        "black": "#1A1A1A",
        "purple": "#6A1B9A",
        "red": "#B00020",
        "blue": "#0072CE",
        "green": "#00A651",
        "orange": "#FF8200",
        "yellow": "#FFF200",
    },
    "trousers": {
        "white": "#F2F3F4",
    },
}

# Wide, dispute-free buckets for the guests -- one person's "burgundy" is
# another's "red". Anything reading these colours (the guest instructions, the
# vision prompt) should say the same thing.
COLOUR_BUCKETS = {
    "green": "includes olive and khaki",
    "blue": "includes navy and denim",
    "black": "black, not charcoal",
    # Trousers only, and deliberately the widest bucket of the four: it is the
    # merged white/yellow symbol (see TROUSERS_PALETTE), so every pale leg goes
    # here and nothing on the legs is ever called yellow. Kept short because it
    # renders under a swatch on a phone as well as in the vision prompt.
    "white": "anything pale -- cream, beige, chinos, or yellow",
}

# Estimated ownership probability per garment *per colour* (plan §12.6): these
# are estimates, not measurements -- the ratios drive the ranking below, the
# absolute percentages do not. Used to break ties towards rare outfits: a
# colour few players own is a colour few passers-by wear, which generalises
# plan §11.1's hard all-black exclusion (all-black is simply the extreme of
# "common") into a graded preference rather than a single forbidden case.
COLOUR_COMMONNESS = {
    "tshirt": {
        "black": 0.95,
        "blue": 0.80,
        "red": 0.55,
        "green": 0.45,
        "purple": 0.25,
        "orange": 0.15,
        "yellow": 0.15,
    },
    "trousers": {
        "blue": 0.95,
        "black": 0.90,
        "white": 0.55,
        "green": 0.30,
        "red": 0.10,
        "purple": 0.06,
        "orange": 0.05,
    },
    "hat": {
        "black": 0.30,
        "blue": 0.18,
        "red": 0.12,
        "green": 0.10,
        "purple": 0.06,
        "orange": 0.05,
        "yellow": 0.05,
    },
}

# Decoder flag thresholds (tune per field experience).
DEFAULT_THRESHOLDS = DecoderThresholds(
    confident_threshold=0.6,
    ambiguous_margin=0.15,
    epsilon=1e-6,
)


def palette_for_channel(name: str):
    """The list of colours a given channel can physically take."""
    return list(CHANNEL_PALETTES.get(name, DEFAULT_PALETTE))


def hex_for(channel_name: str, colour: str):
    """The hex for a colour *in a given channel*, or None if it isn't in it.

    A channel with shades of its own lists only the ones that differ, under its
    own name in :data:`PALETTE_HEX`, and falls back to the main palette for the
    rest -- so a colour common to both is defined once.
    """
    if colour not in palette_for_channel(channel_name):
        return None
    own = PALETTE_HEX.get(channel_name, {})
    return own.get(colour, PALETTE_HEX["main"].get(colour))


def commonness_for(channel_name: str, colour: str) -> float:
    """How common this colour is in that garment, 0..1. Unknown -> 0.5.

    The neutral default keeps a colour or channel absent from
    :data:`COLOUR_COMMONNESS` (e.g. a new palette entry, or ``armbands``,
    which has no wardrobe data because it is provided rather than worn-in)
    from silently sorting to an extreme.
    """
    return COLOUR_COMMONNESS.get(channel_name, {}).get(colour, 0.5)


def default_channel_set(palette=None, channel_names=None, q=None) -> ChannelSet:
    """Build the initial :class:`ChannelSet` (four channels, seven colours each).

    ``palette`` overrides the *main* palette only; channels named in
    :data:`CHANNEL_PALETTES` keep their own alphabet -- trousers swap yellow
    for white.
    """
    palette = list(palette if palette is not None else DEFAULT_PALETTE)
    channel_names = list(
        channel_names if channel_names is not None else DEFAULT_CHANNEL_NAMES
    )
    q = q if q is not None else DEFAULT_Q
    channels = [
        Channel(name=name, labels=CHANNEL_PALETTES.get(name, palette))
        for name in channel_names
    ]
    return ChannelSet(channels=channels, q=q)


def default_scheme() -> IdentityScheme:
    """The initial scheme: 4 colour channels, 7 colours, ``[4,2,3]`` Reed-Solomon.

    Capacity is ``7**2`` = 49 codewords, of which **48** are usable: every
    channel carries a full seven colours, so the only one withheld is the
    all-black slot 0 (see :meth:`IdentityScheme.usable_slots`).

    At ``d = 3`` the guarantee is: correct up to two erasures, **or** correct one
    misread, **or** correct one erasure and detect one misread. Equivalently:
    any two correctly-read garments identify the player, whichever two they are.
    """
    return scheme_with_distance(DEFAULT_TARGET_DISTANCE)


def scheme_with_distance(target_distance: int, k: int = 2) -> IdentityScheme:
    """Convenience for the upgrade ladder (plan §2.5): build a scheme whose code
    achieves ``target_distance`` while keeping ``k`` free symbols (so the player
    capacity ``q**k`` is unchanged -- the default ``k=2`` keeps capacity 49).

    Holding ``k`` fixed means the channel count grows with the distance:
    ``n = k + d - 1`` (the MDS/Singleton relation). The ladder is therefore

    * ``d=2`` -> ``n=3`` -> ``[3,2,2]`` parity,
    * ``d=3`` -> ``n=4`` -> ``[4,2,3]`` Reed-Solomon (the default),
    * ``d=4`` -> ``n=5`` -> ``[5,2,4]`` Reed-Solomon.

    Channels reuse the default palettes; ``DEFAULT_CHANNEL_NAMES`` is truncated
    or extended with generically-named channels as the count changes.
    """
    n = k + target_distance - 1
    names = list(DEFAULT_CHANNEL_NAMES)
    while len(names) < n:
        names.append(f"channel{len(names) + 1}")
    names = names[:n]
    channels = default_channel_set(channel_names=names)
    code = build_code(n=n, q=DEFAULT_Q, target_distance=target_distance)
    return IdentityScheme(channels=channels, code=code)
