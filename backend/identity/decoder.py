"""The soft decoder: the heart of the module.

Given a :class:`Reading` (what the vision model saw), a set of candidate
players (each with their codeword), and an optional :class:`Prior` (e.g. GPS
proximity), produce a ranked list of player posteriors plus flags that
generalise the code's hard guarantees:

* ``inconsistent`` -- the (un-erased) reading cannot be explained by any
  codeword within the code's correction radius, i.e. a misread was *detected*
  but cannot be auto-corrected (this is "detect a misread" for the parity code).
* ``ambiguous`` -- the top two posteriors are within a margin (a tie).
* ``confident`` -- the top posterior is above a threshold.

The decoder is **completely independent** of the vision/LLM and the database:
tests feed it ``Reading``\\s, candidate codewords, and priors directly.

It combines two views:

* a **soft** likelihood (confidence-weighted) that drives the ranking and lets
  a GPS prior break ties or rescue the erasure-plus-misread compromise, and
* a **hard-decision** analysis (nearest codeword over the readable channels)
  that drives the ``inconsistent`` flag in line with coding theory
  (``2t + e + 1 <= d``).
"""

from typing import Dict
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Tuple

from backend.identity.channels import ChannelSet
from backend.identity.observations import Prior
from backend.identity.observations import Reading

Codeword = Tuple[int, ...]


class DecoderThresholds:
    """Tunable thresholds for the decoder's flags (all config, plan §5.6)."""

    def __init__(
        self,
        confident_threshold: float = 0.6,
        ambiguous_margin: float = 0.15,
        epsilon: float = 1e-6,
    ):
        self.confident_threshold = confident_threshold
        self.ambiguous_margin = ambiguous_margin
        self.epsilon = epsilon


class DecodeResult:
    """The decoder's output: a ranking plus flags."""

    def __init__(
        self,
        ranked: List[Tuple[object, float]],
        inconsistent: bool,
        ambiguous: bool,
        confident: bool,
        min_distance_to_codeword: Optional[int],
    ):
        self.ranked = ranked
        self.inconsistent = inconsistent
        self.ambiguous = ambiguous
        self.confident = confident
        self.min_distance_to_codeword = min_distance_to_codeword

    def __repr__(self) -> str:
        return (
            f"DecodeResult(ranked={self.ranked!r}, inconsistent={self.inconsistent}, "
            f"ambiguous={self.ambiguous}, confident={self.confident})"
        )

    @property
    def best(self) -> Optional[object]:
        """The top-ranked player id, or ``None`` if there are no candidates."""
        return self.ranked[0][0] if self.ranked else None

    @property
    def best_posterior(self) -> float:
        return self.ranked[0][1] if self.ranked else 0.0


def _hamming_distance(
    reading: Reading,
    codeword: Sequence[int],
    channels: ChannelSet,
) -> int:
    """Hamming distance between the reading's hard-decision symbols and a
    codeword, counted **over readable (non-erased) channels only**."""
    dist = 0
    for obs, channel, expected in zip(reading, channels, codeword):
        best = obs.best_symbol(channel)
        if best is None:  # erased -> contributes nothing
            continue
        if best != expected:
            dist += 1
    return dist


def decode(
    reading: Reading,
    candidates: Mapping[object, Sequence[int]],
    channels: ChannelSet,
    prior: Optional[Prior] = None,
    thresholds: Optional[DecoderThresholds] = None,
    code_min_distance: Optional[int] = None,
) -> DecodeResult:
    """Decode a reading into a ranked list of candidate players.

    Parameters
    ----------
    reading:
        One :class:`ChannelObservation` per channel, in channel order.
    candidates:
        ``{player_id: codeword}`` -- the players in play and their codewords
        (e.g. alive players on other teams).
    channels:
        The :class:`ChannelSet` (used to resolve symbol labels and ``q``).
    prior:
        Optional :class:`Prior` over the candidate players (defaults uniform).
    thresholds:
        Optional :class:`DecoderThresholds` (defaults to sensible values).
    code_min_distance:
        The code's minimum distance ``d`` (used for the ``inconsistent``
        flag's correction-radius test). If omitted, the flag falls back to a
        plain "no exact codeword match" check.
    """
    if len(reading) != channels.n:
        raise ValueError(
            f"reading has {len(reading)} channels but ChannelSet has {channels.n}"
        )
    thresholds = thresholds or DecoderThresholds()
    prior = prior or Prior()
    q = channels.q
    floor = thresholds.epsilon

    num_candidates = len(candidates)
    uniform = 1.0 / num_candidates if num_candidates else 0.0

    # -- soft likelihoods + prior -> posteriors ---------------------------
    scores: Dict[object, float] = {}
    for player_id, codeword in candidates.items():
        if len(codeword) != channels.n:
            raise ValueError(
                f"candidate {player_id!r} codeword length {len(codeword)} != n {channels.n}"
            )
        likelihood = 1.0
        for obs, channel, symbol in zip(reading, channels, codeword):
            likelihood *= obs.symbol_weight(symbol, channel, q, floor)
        scores[player_id] = prior.weight_for(player_id, uniform) * likelihood

    total = sum(scores.values())
    if total > 0:
        ranked = [(pid, s / total) for pid, s in scores.items()]
    else:
        # Degenerate (all-zero): fall back to the prior alone, else uniform.
        ranked = [(pid, prior.weight_for(pid, uniform)) for pid in candidates]
        norm = sum(s for _, s in ranked) or 1.0
        ranked = [(pid, s / norm) for pid, s in ranked]
    ranked.sort(key=lambda item: item[1], reverse=True)

    # -- hard-decision analysis for the inconsistent flag -----------------
    min_dist: Optional[int] = None
    if candidates:
        min_dist = min(
            _hamming_distance(reading, cw, channels) for cw in candidates.values()
        )

    num_erasures = reading.num_erasures
    inconsistent = False
    if min_dist is not None:
        if code_min_distance is not None:
            # Misreads correctable alongside e erasures: 2t + e + 1 <= d.
            t = max((code_min_distance - 1 - num_erasures) // 2, 0)
            inconsistent = min_dist > t
        else:
            inconsistent = min_dist > 0

    # -- ambiguity / confidence ------------------------------------------
    confident = bool(ranked) and ranked[0][1] >= thresholds.confident_threshold
    ambiguous = (
        len(ranked) >= 2 and (ranked[0][1] - ranked[1][1]) < thresholds.ambiguous_margin
    )

    return DecodeResult(
        ranked=ranked,
        inconsistent=inconsistent,
        ambiguous=ambiguous,
        confident=confident,
        min_distance_to_codeword=min_dist,
    )
