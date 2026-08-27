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
# list outgrew that). It is a wholly separate physical set from the main
# palette, simulated and chosen for legs specifically (plan §9.1):
#
#   symbol  colour     hex        L*   hue    availability
#   0       black      #1A1A1A    11   --     very high
#   1       grey       #808080    54   --     very high
#   2       off-white  #F0EFEA    94   --     moderate
#   3       blue       #2E5FA3    42   270°   very high
#   4       red        #C1272D    42   30°    moderate
#   5       olive      #6B7A3A    49   105°   good
#   6       mustard    #C9962B    66   80°    low
#
# Three achromatics spread right across the lightness range (11 / 54 / 94) plus
# four chromatics spread around the hue circle. That is what makes it robust
# under bad light: the achromatics are told apart by L* alone, which survives a
# colour cast that would wreck a hue judgement, and the chromatics never have to
# be separated from a neutral by hue.
#
# Only the *cardinality* reaches the code, so none of this has to match the main
# palette and none of it does -- even blue and red carry their own, more
# leg-like hexes. The names are the vocabulary players and the vision model both
# answer in, so every one of them that covers a range is defined in
# COLOUR_BUCKETS below, per channel: "black" excludes charcoal on a top (there
# is no grey to catch it) and includes it on the legs (grey is a whole two
# stops away). Keep the two audiences reading the same definitions -- the
# scoring downstream assumes a player and the model mean the same thing by a
# colour name.
TROUSERS_PALETTE = [
    "black",
    "grey",
    "off-white",
    "blue",
    "red",
    "olive",
    "mustard",
]

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
    # Trousers list every shade that differs from the main palette; "black" is
    # the one they share, so it is defined once, above.
    "trousers": {
        "grey": "#808080",
        "off-white": "#F0EFEA",
        "blue": "#2E5FA3",
        "red": "#C1272D",
        "olive": "#6B7A3A",
        "mustard": "#C9962B",
    },
}

# Wide, dispute-free buckets -- one person's "burgundy" is another's "red".
# Keyed by palette name exactly like PALETTE_HEX: a channel with an alphabet of
# its own defines the terms that differ, and falls back to "main" for the rest.
# Both audiences that answer in these words render the same entry: the swatch
# note on the picking page, and each channel's options in the vision prompt.
# Kept short, because they have to read well under a swatch on a phone.
COLOUR_BUCKETS = {
    "main": {
        "green": "includes olive and khaki",
        "blue": "includes navy and denim",
        "black": "black, not charcoal",
    },
    # The trousers palette is a different physical set, so most of its terms
    # need defining. "black" is the one that actively contradicts the main
    # palette: with no grey on a top, charcoal has to stay out of black to keep
    # that bucket tight, but on the legs grey sits at L* 54 and charcoal is far
    # nearer black at L* 11, so charcoal belongs there.
    "trousers": {
        "black": "black or charcoal",
        "grey": "mid grey -- lighter than charcoal, darker than stone",
        "off-white": "white, cream, beige or stone -- most chinos",
        "red": "includes burgundy and rust",
        "olive": "olive, khaki or army green",
        "mustard": "mustard, ochre, tan or camel",
    },
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
    # Trousers come from the availability column of the §9.1 simulation rather
    # than a guess: very high -> ~0.9, good -> 0.45, moderate -> ~0.35,
    # low -> 0.08. Within a tier the ordering is the obvious one (blue jeans
    # before black before grey); across tiers it is the table's.
    "trousers": {
        "blue": 0.95,
        "black": 0.90,
        "grey": 0.85,
        "olive": 0.45,
        "off-white": 0.40,
        "red": 0.35,
        "mustard": 0.08,
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


def bucket_for(channel_name: str, colour: str):
    """What a colour name covers *in a given channel*, or None if it needs no
    explaining. Falls back to the main palette, like :func:`hex_for`.
    """
    own = COLOUR_BUCKETS.get(channel_name, {})
    return own.get(colour, COLOUR_BUCKETS["main"].get(colour))


def buckets_for_channel(channel_name: str):
    """``{colour: note}`` for the colours of ``channel_name`` that have one."""
    notes = (
        (colour, bucket_for(channel_name, colour))
        for colour in palette_for_channel(channel_name)
    )
    return {colour: note for colour, note in notes if note}


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
    :data:`CHANNEL_PALETTES` keep their own alphabet -- trousers have a set of
    their own entirely.
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
