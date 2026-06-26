"""Data types describing what the vision model *read*, plus priors.

These are plain, dependency-free value objects. The decoder consumes them; the
vision adapter (in the integration layer, not this package) produces them.

A :class:`ChannelObservation` is, per channel, one of:

* a **distribution** over that channel's alphabet -- ``{label_or_index: prob}``
  (preferred: this is what a good vision model can emit), or
* a single best ``symbol`` + ``confidence`` (convenience; internally expanded to
  a distribution with ``confidence`` on the symbol and the remainder spread
  uniformly over the other ``q-1`` symbols), or
* an **erasure** -- the channel was unreadable / obscured.

A :class:`Reading` is one observation per channel, in channel order. A
:class:`Prior` is an optional ``{player_id: probability}`` weighting (e.g. from
GPS proximity); it defaults to uniform over the candidate set.
"""

from typing import Dict
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Union

Symbol = Union[int, str]


class ChannelObservation:
    """A single channel's reading: a distribution, a best-guess, or an erasure.

    Construct via the factory classmethods :meth:`distribution`,
    :meth:`best_guess`, or :meth:`erasure` rather than the raw initialiser.
    """

    def __init__(self, distribution: Optional[Dict[Symbol, float]]):
        # ``None`` means erasure. Otherwise a {symbol: probability} mapping
        # whose keys are resolved against the channel at decode time (a symbol
        # may be a label string or an integer index).
        self._distribution = distribution

    def __repr__(self) -> str:
        if self.is_erasure:
            return "ChannelObservation(erasure)"
        return f"ChannelObservation({self._distribution!r})"

    @property
    def is_erasure(self) -> bool:
        return self._distribution is None

    @classmethod
    def erasure(cls) -> "ChannelObservation":
        """The channel was obscured / unreadable."""
        return cls(None)

    @classmethod
    def distribution(cls, dist: Mapping[Symbol, float]) -> "ChannelObservation":
        """A full probability distribution over (some of) the channel's symbols.

        Probabilities need not sum to 1 -- the decoder reads the weight on the
        candidate's true symbol and floors absent symbols. Negative weights are
        rejected.
        """
        dist = dict(dist)
        if not dist:
            raise ValueError("distribution observation needs at least one entry")
        for sym, prob in dist.items():
            if prob < 0:
                raise ValueError(f"negative probability {prob} for symbol {sym!r}")
        return cls(dist)

    @classmethod
    def best_guess(cls, symbol: Symbol, confidence: float) -> "ChannelObservation":
        """A single best symbol with a confidence in ``[0, 1]``.

        Stored as a one-entry distribution; the decoder spreads the residual
        ``1 - confidence`` over the other symbols using the field size ``q``.
        """
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]; got {confidence}")
        obs = cls({symbol: confidence})
        obs._is_best_guess = True
        return obs

    # Internal flag distinguishing best_guess (residual spread by the decoder)
    # from an explicit distribution (floored as-is).
    _is_best_guess = False

    def symbol_weight(self, symbol_index: int, channel, q: int, floor: float) -> float:
        """Likelihood contribution for a candidate whose true symbol at this
        channel has index ``symbol_index``.

        * erasure -> ``1.0`` (no information),
        * best_guess -> ``confidence`` on the matching symbol else
          ``(1 - confidence) / (q - 1)``,
        * distribution -> the weight assigned to that symbol (floored to
          ``floor`` so a never-mentioned true symbol can still win on a prior).
        """
        if self.is_erasure:
            return 1.0
        resolved = self._resolve(channel)
        if getattr(self, "_is_best_guess", False):
            ((only_symbol, confidence),) = resolved.items()
            if only_symbol == symbol_index:
                return confidence
            if q <= 1:
                return floor
            return max((1.0 - confidence) / (q - 1), floor)
        return max(resolved.get(symbol_index, 0.0), floor)

    def best_symbol(self, channel) -> Optional[int]:
        """Hard-decision argmax symbol index, or ``None`` for an erasure."""
        if self.is_erasure:
            return None
        resolved = self._resolve(channel)
        return max(resolved, key=resolved.get)

    def _resolve(self, channel) -> Dict[int, float]:
        """Resolve symbol keys (labels or indices) to channel indices."""
        out: Dict[int, float] = {}
        for sym, prob in self._distribution.items():
            if isinstance(sym, str):
                idx = channel.label_to_index(sym)
            else:
                idx = int(sym)
            out[idx] = out.get(idx, 0.0) + prob
        return out


class Reading:
    """One :class:`ChannelObservation` per channel, in channel order."""

    def __init__(self, observations: Sequence[ChannelObservation]):
        self.observations: List[ChannelObservation] = list(observations)

    def __len__(self) -> int:
        return len(self.observations)

    def __iter__(self):
        return iter(self.observations)

    def __getitem__(self, index: int) -> ChannelObservation:
        return self.observations[index]

    @property
    def num_erasures(self) -> int:
        return sum(1 for obs in self.observations if obs.is_erasure)


class Prior:
    """An optional ``{player_id: weight}`` prior over candidate players."""

    def __init__(self, weights: Optional[Mapping] = None):
        self.weights: Dict = dict(weights) if weights else {}
        for player_id, w in self.weights.items():
            if w < 0:
                raise ValueError(f"negative prior weight {w} for player {player_id!r}")

    def weight_for(self, player_id, default: float) -> float:
        return self.weights.get(player_id, default)

    @property
    def is_empty(self) -> bool:
        return not self.weights
