"""The declarative initial configuration and a ``default_scheme()`` factory.

Changing the initial setup = editing **this one file**: add a colour to the
palette, add a :class:`Channel`, or switch the code to
:func:`reed_solomon_code`. Nothing in :mod:`backend.identity.decoder`,
:mod:`~backend.identity.scheme`, or :mod:`~backend.identity.channels` needs to
change -- that is the extensibility guarantee.

**The palette is a placeholder, not final** (plan §9): the five colours below
are decent starting defaults. The genuinely best-distinguishable palette will be
chosen by live camera tests with the real hardware, so keep swapping colours
here a one-line change and do not treat these as fixed.
"""

from backend.identity.channels import Channel
from backend.identity.channels import ChannelSet
from backend.identity.code import build_code
from backend.identity.code import parity_code
from backend.identity.decoder import DecoderThresholds
from backend.identity.scheme import IdentityScheme

# Placeholder palette (see module docstring): red / yellow / green / blue /
# purple. Index <-> colour: 0=red, 1=yellow, 2=green, 3=blue, 4=purple.
DEFAULT_PALETTE = ["red", "yellow", "green", "blue", "purple"]

# The field cardinality q = number of colours. 5 is prime, so the simple
# dependency-free GF(q) arithmetic is valid.
DEFAULT_Q = len(DEFAULT_PALETTE)

# The wearable channels (slots). Initially three, all using the colour palette.
# Add/remove/reorder channels here -- e.g. a "shape" channel with a shape
# alphabet, or splitting the armband into left + right.
DEFAULT_CHANNEL_NAMES = ["shirt", "head", "armband"]

# Decoder flag thresholds (tune per field experience).
DEFAULT_THRESHOLDS = DecoderThresholds(
    confident_threshold=0.6,
    ambiguous_margin=0.15,
    epsilon=1e-6,
)


def default_channel_set(palette=None, channel_names=None, q=None) -> ChannelSet:
    """Build the initial :class:`ChannelSet` (three colour channels)."""
    palette = list(palette if palette is not None else DEFAULT_PALETTE)
    channel_names = list(
        channel_names if channel_names is not None else DEFAULT_CHANNEL_NAMES
    )
    q = q if q is not None else len(palette)
    channels = [Channel(name=name, labels=palette) for name in channel_names]
    return ChannelSet(channels=channels, q=q)


def default_scheme() -> IdentityScheme:
    """The initial scheme: 3 colour channels, 5 colours, ``[3,2,2]`` parity.

    Capacity = ``5**2`` = **25** distinct player identities.
    """
    channels = default_channel_set()
    code = parity_code(n=len(DEFAULT_CHANNEL_NAMES), q=DEFAULT_Q)
    return IdentityScheme(channels=channels, code=code)


def scheme_with_distance(target_distance: int, k: int = 2) -> IdentityScheme:
    """Convenience for the upgrade ladder (plan §2.5): build a scheme whose code
    achieves ``target_distance`` while keeping ``k`` free symbols (so the player
    capacity ``q**k`` is unchanged -- the default ``k=2`` keeps capacity 25).

    Holding ``k`` fixed means the channel count grows with the distance:
    ``n = k + d - 1`` (the MDS/Singleton relation). The ladder is therefore

    * ``d=2`` -> ``n=3`` -> ``[3,2,2]`` parity (the default),
    * ``d=3`` -> ``n=4`` -> ``[4,2,3]`` Reed-Solomon,
    * ``d=4`` -> ``n=5`` -> ``[5,2,4]`` Reed-Solomon.

    Channels reuse the default palette; ``DEFAULT_CHANNEL_NAMES`` is extended
    with generically-named channels as the count grows.
    """
    n = k + target_distance - 1
    names = list(DEFAULT_CHANNEL_NAMES)
    while len(names) < n:
        names.append(f"channel{len(names) + 1}")
    names = names[:n]
    channels = default_channel_set(channel_names=names)
    code = build_code(n=n, q=DEFAULT_Q, target_distance=target_distance)
    return IdentityScheme(channels=channels, code=code)
