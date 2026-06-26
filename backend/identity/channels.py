"""Channels and channel sets: the bridge between physical symbols and
``GF(q)`` indices.

A :class:`Channel` is one categorical feature the vision model can read
independently (shirt colour, head colour, armband colour -- or, in future, a
*shape* printed on the shirt). Its ``labels`` are the ordered physical symbol
names. Different channels may carry **different** alphabets (colours vs shapes)
as long as each supplies at least ``q`` symbols, because the algebraic code only
ever sees the index ``[0, q)``, never the physical meaning.

A :class:`ChannelSet` is the ordered tuple of channels for a scheme; its length
must equal the code's ``n``. It converts between a codeword (tuple of indices)
and an *appearance* dict ``{channel_name: label}`` -- i.e. "what the player
physically wears".
"""

from typing import Dict
from typing import Iterable
from typing import List
from typing import Mapping
from typing import Sequence
from typing import Tuple


class Channel:
    """One wearable slot with an ordered alphabet of physical labels."""

    def __init__(self, name: str, labels: Sequence[str]):
        labels = list(labels)
        if len(labels) != len(set(labels)):
            raise ValueError(f"channel {name!r} has duplicate labels: {labels}")
        if not labels:
            raise ValueError(f"channel {name!r} needs at least one label")
        self.name = name
        self.labels = labels
        self._label_to_index = {label: i for i, label in enumerate(labels)}

    def __repr__(self) -> str:
        return f"Channel(name={self.name!r}, labels={self.labels!r})"

    @property
    def size(self) -> int:
        """Number of labels available in this channel's alphabet."""
        return len(self.labels)

    def label_to_index(self, label: str) -> int:
        try:
            return self._label_to_index[label]
        except KeyError:
            raise ValueError(
                f"channel {self.name!r} has no label {label!r}; known: {self.labels}"
            )

    def index_to_label(self, index: int) -> str:
        if not 0 <= index < len(self.labels):
            raise ValueError(
                f"channel {self.name!r} index {index} out of range [0, {len(self.labels)})"
            )
        return self.labels[index]

    def has_label(self, label: str) -> bool:
        return label in self._label_to_index


class ChannelSet:
    """An ordered collection of channels backing a code of length ``n``.

    ``q`` is the field cardinality (the common symbol count the code uses).
    Every channel must supply at least ``q`` labels; only the first ``q`` are
    addressable by codewords, but channels may carry extra labels.
    """

    def __init__(self, channels: Iterable[Channel], q: int):
        channels = list(channels)
        if not channels:
            raise ValueError("ChannelSet needs at least one channel")
        names = [c.name for c in channels]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate channel names: {names}")
        for c in channels:
            if c.size < q:
                raise ValueError(
                    f"channel {c.name!r} supplies {c.size} labels but q={q}; "
                    "every channel must provide at least q symbols"
                )
        self.channels = channels
        self.q = q

    def __len__(self) -> int:
        return len(self.channels)

    def __iter__(self):
        return iter(self.channels)

    def __getitem__(self, index: int) -> Channel:
        return self.channels[index]

    @property
    def n(self) -> int:
        """Length (number of channels) -- must equal the code's ``n``."""
        return len(self.channels)

    @property
    def names(self) -> List[str]:
        return [c.name for c in self.channels]

    def by_name(self, name: str) -> Channel:
        for c in self.channels:
            if c.name == name:
                return c
        raise ValueError(f"no channel named {name!r}; known: {self.names}")

    def codeword_to_appearance(self, codeword: Sequence[int]) -> Dict[str, str]:
        """Map a codeword (tuple of indices) to ``{channel_name: label}``."""
        if len(codeword) != self.n:
            raise ValueError(
                f"codeword length {len(codeword)} != number of channels {self.n}"
            )
        return {
            c.name: c.index_to_label(idx) for c, idx in zip(self.channels, codeword)
        }

    def appearance_to_codeword(self, appearance: Mapping[str, str]) -> Tuple[int, ...]:
        """Map an appearance ``{channel_name: label}`` back to a codeword."""
        missing = set(self.names) - set(appearance)
        if missing:
            raise ValueError(f"appearance missing channels: {sorted(missing)}")
        return tuple(c.label_to_index(appearance[c.name]) for c in self.channels)
