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
# (prime, which the dependency-free GF(q) arithmetic requires).
DEFAULT_PALETTE = ["black", "purple", "red", "blue", "green", "orange", "yellow"]

# Trousers are deliberately restricted (plan §2.6): guests supply their own
# clothing and yellow, orange and purple trousers are not things people own.
# This is a *different physical set*, not a subset -- the code only ever sees
# indices, and a misread can only confuse colours within one channel, so white
# is safe here even though it is excluded from the main palette (under sodium
# street lighting a white shirt photographs orange).
TROUSERS_PALETTE = ["black", "blue", "green", "red", "white"]

# The field cardinality. Must be prime, and must be at least the size of the
# largest channel alphabet.
DEFAULT_Q = 7

# The wearable channels (slots), in the order the code evaluates them.
# Add/remove/reorder here -- e.g. a "shape" channel with a shape alphabet.
DEFAULT_CHANNEL_NAMES = ["tshirt", "trousers", "hat", "armbands"]

# Channels not listed here use DEFAULT_PALETTE.
CHANNEL_PALETTES = {"trousers": TROUSERS_PALETTE}

# The minimum distance the code must achieve. d = 3 over 4 channels gives the
# [4,2,3] Reed-Solomon code: correct two erasures, or one misread, or one
# erasure plus detect one misread. See the upgrade ladder in
# :func:`scheme_with_distance`.
DEFAULT_TARGET_DISTANCE = 3

# The hex each colour name refers to, so the admin UI, any printable guest sheet
# and the palette design all read from one place. Keyed by (channel_palette
# name, colour) because "black" is #1A1A1A on a t-shirt and #222222 on trousers.
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
        "black": "#222222",
        "blue": "#0072CE",
        "green": "#00A651",
        "red": "#B00020",
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
    "white": "includes cream and beige (e.g. chinos)",
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
    """The hex for a colour *in a given channel*, or None if it isn't in it."""
    key = "trousers" if channel_name in CHANNEL_PALETTES else "main"
    return PALETTE_HEX[key].get(colour)


def default_channel_set(palette=None, channel_names=None, q=None) -> ChannelSet:
    """Build the initial :class:`ChannelSet` (four channels, restricted trousers).

    ``palette`` overrides the *main* palette only; channels named in
    :data:`CHANNEL_PALETTES` keep their own alphabet.
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

    Capacity is ``7**2`` = 49 codewords, of which **34** are usable once the
    restricted trousers palette and the all-black slot 0 are excluded (see
    :meth:`IdentityScheme.usable_slots`).

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
