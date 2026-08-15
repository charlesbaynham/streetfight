"""Admin-only sandbox around :mod:`backend.identity`.

This exists so the admin can *play* with the colour-code identity scheme before
any of it is wired to a camera: build a scheme from arbitrary parameters, hand
the decoder a reading by hand (pretending to be the not-yet-existing vision
model), and run a Monte-Carlo simulation to see how a scheme copes with
erasures and misreads.

Everything here is **stateless**: the scheme is described by the request, built
on the fly, and thrown away. Nothing touches the database, so nothing here can
affect a running game.
"""

import logging
import random
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple

import pydantic

from .identity.channels import Channel
from .identity.channels import ChannelSet
from .identity.code import LinearCode
from .identity.code import ParityCode
from .identity.code import ReedSolomonCode
from .identity.code import build_code
from .identity.code import parity_code
from .identity.code import reed_solomon_code
from .identity.config import CHANNEL_PALETTES
from .identity.config import DEFAULT_CHANNEL_NAMES
from .identity.config import DEFAULT_PALETTE
from .identity.config import DEFAULT_TARGET_DISTANCE
from .identity.config import DEFAULT_THRESHOLDS
from .identity.decoder import DecoderThresholds
from .identity.decoder import decode
from .identity.observations import ChannelObservation
from .identity.observations import Prior
from .identity.observations import Reading
from .identity.scheme import IdentityScheme

logger = logging.getLogger(__name__)

# Sanity limits so a typo in the admin UI can't ask for a 10-minute brute force.
MAX_CHANNELS = 12
MAX_PALETTE = 26
MAX_CAPACITY = 100_000
MAX_CODEBOOK_ROWS = 200
MAX_TRIALS = 20_000
# Above this capacity, min_distance() (which is O(capacity^2)) is too slow, so
# fall back to the construction's theoretical distance.
MAX_BRUTE_FORCE_CAPACITY = 625


class DemoError(ValueError):
    """A bad demo request. Translated to an HTTP 400 by the API layer."""


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChannelSpec(pydantic.BaseModel):
    """One wearable channel. ``labels`` defaults to the scheme's palette."""

    name: str
    labels: Optional[List[str]] = None


class SchemeSpec(pydantic.BaseModel):
    """Everything needed to build an :class:`IdentityScheme` from scratch."""

    palette: List[str] = list(DEFAULT_PALETTE)
    # Channels default to the main palette; the ones with their own restricted
    # alphabet (trousers) carry it explicitly.
    channels: List[ChannelSpec] = [
        ChannelSpec(name=name, labels=CHANNEL_PALETTES.get(name))
        for name in DEFAULT_CHANNEL_NAMES
    ]
    # "auto" picks the simplest construction reaching target_distance;
    # "parity" and "reed_solomon" force one.
    code_type: str = "auto"
    # d = 3 is the configured scheme (plan §2.4): with 4 channels and "auto"
    # this builds the [4,2,3] Reed-Solomon code that default_scheme() uses.
    target_distance: Optional[int] = DEFAULT_TARGET_DISTANCE
    k: Optional[int] = None
    # Field size. Defaults to the palette length; set it lower to keep spare
    # (unused) colours in the palette, or when the palette length isn't prime.
    q: Optional[int] = None


class ThresholdSpec(pydantic.BaseModel):
    confident_threshold: float = DEFAULT_THRESHOLDS.confident_threshold
    ambiguous_margin: float = DEFAULT_THRESHOLDS.ambiguous_margin
    epsilon: float = DEFAULT_THRESHOLDS.epsilon


class ObservationSpec(pydantic.BaseModel):
    """What the (imaginary) vision model reported for one channel.

    ``kind`` is one of:

    * ``erasure`` -- channel obscured / unreadable,
    * ``best_guess`` -- ``symbol`` seen with ``confidence``,
    * ``distribution`` -- an explicit ``{label: weight}`` map.
    """

    kind: str = "best_guess"
    symbol: Optional[str] = None
    confidence: float = 1.0
    distribution: Optional[Dict[str, float]] = None


class CandidateSpec(pydantic.BaseModel):
    """A player in the running: a display name plus their identity slot."""

    name: str
    slot: int
    prior: Optional[float] = None


class DecodeRequest(pydantic.BaseModel):
    scheme: SchemeSpec = SchemeSpec()
    reading: List[ObservationSpec] = []
    candidates: List[CandidateSpec] = []
    thresholds: ThresholdSpec = ThresholdSpec()


class SimulateRequest(pydantic.BaseModel):
    scheme: SchemeSpec = SchemeSpec()
    thresholds: ThresholdSpec = ThresholdSpec()
    # The candidate set is slots 0..num_players-1 unless explicit candidates
    # are given (handy for testing a deliberately awkward subset).
    num_players: int = 10
    candidates: Optional[List[CandidateSpec]] = None
    trials: int = 1000
    p_erasure: float = 0.1
    p_misread: float = 0.1
    confidence: float = 0.8
    seed: int = 0


# ---------------------------------------------------------------------------
# Building a scheme from a spec
# ---------------------------------------------------------------------------


def build_scheme(spec: SchemeSpec) -> IdentityScheme:
    """Turn a :class:`SchemeSpec` into an :class:`IdentityScheme`.

    Raises :class:`DemoError` with a human-readable explanation for anything
    the admin got wrong -- that message is the whole point of the demo page.
    """
    palette = [label.strip() for label in spec.palette if label.strip()]
    if len(palette) != len(set(palette)):
        raise DemoError(f"palette has duplicate colours: {palette}")
    if not 1 <= len(palette) <= MAX_PALETTE:
        raise DemoError(f"palette must have 1..{MAX_PALETTE} colours")

    channel_specs = [c for c in spec.channels if c.name.strip()]
    if not channel_specs:
        raise DemoError("need at least one channel")
    if len(channel_specs) > MAX_CHANNELS:
        raise DemoError(f"at most {MAX_CHANNELS} channels")

    q = spec.q if spec.q is not None else len(palette)
    if q < 2:
        raise DemoError(f"q must be at least 2; got {q}")

    channels = []
    for c in channel_specs:
        labels = c.labels if c.labels else palette
        labels = [label.strip() for label in labels if label.strip()]
        try:
            channels.append(Channel(name=c.name.strip(), labels=labels))
        except ValueError as e:
            raise DemoError(str(e))

    try:
        channel_set = ChannelSet(channels=channels, q=q)
    except ValueError as e:
        raise DemoError(str(e))

    n = channel_set.n
    code = _build_code(spec, n=n, q=q)

    if code.capacity > MAX_CAPACITY:
        raise DemoError(
            f"capacity q**k = {code.capacity} exceeds the demo limit "
            f"{MAX_CAPACITY}; reduce k or the palette size"
        )

    try:
        return IdentityScheme(channels=channel_set, code=code)
    except ValueError as e:
        raise DemoError(str(e))


def _build_code(spec: SchemeSpec, n: int, q: int) -> LinearCode:
    code_type = (spec.code_type or "auto").strip().lower()
    try:
        if code_type == "parity":
            return parity_code(n=n, q=q)
        if code_type in ("reed_solomon", "reed-solomon", "rs"):
            k = spec.k
            if k is None:
                if spec.target_distance is None:
                    raise DemoError("Reed-Solomon needs either k or target_distance")
                k = n - spec.target_distance + 1
            return reed_solomon_code(n=n, k=k, q=q)
        if code_type == "auto":
            target = spec.target_distance
            if target is None:
                target = n - spec.k + 1 if spec.k is not None else 2
            return build_code(n=n, q=q, target_distance=target)
    except ValueError as e:
        raise DemoError(str(e))
    raise DemoError(
        f"unknown code_type {spec.code_type!r}; use 'auto', 'parity' or 'reed_solomon'"
    )


def _min_distance(code: LinearCode) -> Tuple[int, str]:
    """``(d, source)`` -- brute-forced when that's cheap, else theoretical."""
    if code.capacity <= MAX_BRUTE_FORCE_CAPACITY:
        return code.min_distance(), "computed"
    if isinstance(code, ParityCode):
        return 2, "theoretical"
    if isinstance(code, ReedSolomonCode):
        return code.n - code.k + 1, "theoretical"
    return code.min_distance(), "computed"


def _code_name(code: LinearCode) -> str:
    if isinstance(code, ParityCode):
        return "parity"
    if isinstance(code, ReedSolomonCode):
        return "reed_solomon"
    return type(code).__name__


# ---------------------------------------------------------------------------
# Scheme summary
# ---------------------------------------------------------------------------


def describe_scheme(spec: SchemeSpec, max_rows: int = MAX_CODEBOOK_ROWS) -> dict:
    """Scheme parameters, its guarantees, and (part of) its codebook."""
    scheme = build_scheme(spec)
    code = scheme.code
    d, d_source = _min_distance(code)

    max_rows = max(1, min(int(max_rows), MAX_CODEBOOK_ROWS))
    shown = min(scheme.capacity, max_rows)
    codebook = []
    for slot in range(shown):
        codeword = scheme.codeword_of_slot(slot)
        wearable = scheme.channels.is_representable(codeword)
        codebook.append(
            {
                "slot": slot,
                "codeword": list(codeword),
                # A restricted channel (plan §2.6) makes some codewords
                # unwearable: the algebra is fine, but no such garment exists.
                "wearable": wearable,
                "appearance": (
                    scheme.channels.codeword_to_appearance(codeword)
                    if wearable
                    else None
                ),
            }
        )

    return {
        "n": code.n,
        "k": code.k,
        "q": code.q,
        "capacity": scheme.capacity,
        "usable_capacity": len(scheme.usable_slots()),
        "min_distance": d,
        "min_distance_source": d_source,
        "code_type": _code_name(code),
        "channels": [
            {"name": c.name, "labels": list(c.labels)} for c in scheme.channels
        ],
        "guarantees": _guarantees(d),
        "codebook": codebook,
        "codebook_truncated": shown < scheme.capacity,
    }


def _guarantees(d: int) -> dict:
    """The textbook guarantees for a minimum distance ``d``."""
    return {
        "correctable_misreads": max((d - 1) // 2, 0),
        "detectable_misreads": max(d - 1, 0),
        "correctable_erasures": max(d - 1, 0),
        "summary": (
            f"d={d}: corrects {max((d - 1) // 2, 0)} misread(s), "
            f"detects {max(d - 1, 0)}, corrects {max(d - 1, 0)} erasure(s). "
            "Mixed faults obey 2*misreads + erasures + 1 <= d."
        ),
    }


# ---------------------------------------------------------------------------
# Decoding a hand-entered reading
# ---------------------------------------------------------------------------


def _thresholds(spec: ThresholdSpec) -> DecoderThresholds:
    return DecoderThresholds(
        confident_threshold=spec.confident_threshold,
        ambiguous_margin=spec.ambiguous_margin,
        epsilon=spec.epsilon,
    )


def _observation(obs_spec: ObservationSpec, channel: Channel) -> ChannelObservation:
    kind = (obs_spec.kind or "best_guess").strip().lower()
    if kind == "erasure":
        return ChannelObservation.erasure()
    if kind == "distribution":
        dist = obs_spec.distribution or {}
        dist = {label: weight for label, weight in dist.items() if weight}
        if not dist:
            raise DemoError(
                f"channel {channel.name!r}: distribution observation has no "
                "non-zero entries"
            )
        for label in dist:
            _check_label(channel, label)
        try:
            return ChannelObservation.distribution(dist)
        except ValueError as e:
            raise DemoError(f"channel {channel.name!r}: {e}")
    if kind == "best_guess":
        if obs_spec.symbol is None:
            raise DemoError(f"channel {channel.name!r}: best_guess needs a symbol")
        _check_label(channel, obs_spec.symbol)
        try:
            return ChannelObservation.best_guess(obs_spec.symbol, obs_spec.confidence)
        except ValueError as e:
            raise DemoError(f"channel {channel.name!r}: {e}")
    raise DemoError(
        f"channel {channel.name!r}: unknown observation kind {obs_spec.kind!r}"
    )


def _check_label(channel: Channel, label: str) -> None:
    if not channel.has_label(label):
        raise DemoError(
            f"channel {channel.name!r} has no label {label!r}; known: {channel.labels}"
        )


def _build_reading(
    specs: Sequence[ObservationSpec], channels: ChannelSet
) -> Tuple[Reading, List[Optional[int]]]:
    """Build a :class:`Reading` plus the per-channel hard decision."""
    if len(specs) != channels.n:
        raise DemoError(
            f"reading has {len(specs)} channels but the scheme has {channels.n}"
        )
    observations = [
        _observation(spec, channel) for spec, channel in zip(specs, channels)
    ]
    reading = Reading(observations)
    hard = [obs.best_symbol(channel) for obs, channel in zip(reading, channels)]
    return reading, hard


def _candidate_codewords(
    candidates: Sequence[CandidateSpec], scheme: IdentityScheme
) -> Dict[str, Tuple[int, ...]]:
    if not candidates:
        raise DemoError("need at least one candidate player")
    names = [c.name for c in candidates]
    if len(names) != len(set(names)):
        raise DemoError(f"candidate names must be unique; got {names}")
    out = {}
    for candidate in candidates:
        try:
            out[candidate.name] = scheme.codeword_of_slot(candidate.slot)
        except ValueError as e:
            raise DemoError(f"candidate {candidate.name!r}: {e}")
    return out


def _appearance_or_none(scheme: IdentityScheme, codeword: Sequence[int]):
    """``{channel: label}``, or None if a restricted channel can't express it."""
    if not scheme.channels.is_representable(codeword):
        return None
    return scheme.channels.codeword_to_appearance(codeword)


def _hard_distance(hard: Sequence[Optional[int]], codeword: Sequence[int]) -> int:
    """Hamming distance over the readable (non-erased) channels only."""
    return sum(
        1
        for seen, expected in zip(hard, codeword)
        if seen is not None and seen != expected
    )


def decode_reading(request: DecodeRequest) -> dict:
    """Decode a hand-entered reading against a hand-entered candidate set."""
    scheme = build_scheme(request.scheme)
    reading, hard = _build_reading(request.reading, scheme.channels)
    codewords = _candidate_codewords(request.candidates, scheme)

    prior_weights = {c.name: c.prior for c in request.candidates if c.prior is not None}
    prior = Prior(prior_weights) if prior_weights else None

    d, d_source = _min_distance(scheme.code)

    result = decode(
        reading=reading,
        candidates=codewords,
        channels=scheme.channels,
        prior=prior,
        thresholds=_thresholds(request.thresholds),
        code_min_distance=d,
    )

    posteriors = dict(result.ranked)
    slots = {c.name: c.slot for c in request.candidates}
    ranked = [
        {
            "name": name,
            "slot": slots[name],
            "posterior": posteriors[name],
            "codeword": list(codewords[name]),
            # None when a restricted channel cannot express this codeword --
            # the slot is decodable but nobody could be wearing it.
            "appearance": _appearance_or_none(scheme, codewords[name]),
            "distance": _hard_distance(hard, codewords[name]),
        }
        for name, _ in result.ranked
    ]

    hard_reading = [
        None if symbol is None else scheme.channels[i].index_to_label(symbol)
        for i, symbol in enumerate(hard)
    ]
    # Only meaningful when nothing was erased; None means "not applicable".
    hard_is_codeword = None if None in hard else scheme.code.is_codeword(hard)

    return {
        "ranked": ranked,
        "best": result.best,
        "best_posterior": result.best_posterior,
        "inconsistent": result.inconsistent,
        "ambiguous": result.ambiguous,
        "confident": result.confident,
        "min_distance_to_codeword": result.min_distance_to_codeword,
        "num_erasures": reading.num_erasures,
        "hard_reading": hard_reading,
        "hard_reading_is_codeword": hard_is_codeword,
        "code_min_distance": d,
        "code_min_distance_source": d_source,
        "auto_accept": bool(
            result.confident and not result.ambiguous and not result.inconsistent
        ),
    }


# ---------------------------------------------------------------------------
# Monte-Carlo simulation
# ---------------------------------------------------------------------------


def simulate(request: SimulateRequest) -> dict:
    """Throw random readings at a scheme and count how the decoder does.

    Each trial picks a true player, corrupts their codeword channel by channel
    (erasure with ``p_erasure``, otherwise a wrong colour with ``p_misread``),
    and decodes. The number that matters is ``auto_accept_wrong``: readings the
    decoder was confident and unflagged about, and got wrong.
    """
    if not 0 < request.trials <= MAX_TRIALS:
        raise DemoError(f"trials must be in 1..{MAX_TRIALS}")
    for name, value in (
        ("p_erasure", request.p_erasure),
        ("p_misread", request.p_misread),
        ("confidence", request.confidence),
    ):
        if not 0.0 <= value <= 1.0:
            raise DemoError(f"{name} must be in [0, 1]; got {value}")
    if request.p_erasure + request.p_misread > 1.0:
        raise DemoError("p_erasure + p_misread must be <= 1")

    scheme = build_scheme(request.scheme)
    channels = scheme.channels

    candidates = request.candidates
    if not candidates:
        # Simulate real players, so draw from the slots that can actually be
        # worn -- a restricted channel makes some codewords unassignable.
        usable = scheme.usable_slots()
        if not 0 < request.num_players <= len(usable):
            raise DemoError(
                f"num_players must be in 1..{len(usable)} (the usable slots of "
                f"this scheme; its raw capacity is {scheme.capacity})"
            )
        candidates = [
            CandidateSpec(name=f"player{slot}", slot=slot)
            for slot in usable[: request.num_players]
        ]

    codewords = _candidate_codewords(candidates, scheme)
    names = list(codewords)
    thresholds = _thresholds(request.thresholds)
    d, _ = _min_distance(scheme.code)

    rng = random.Random(request.seed)
    counts = {
        "trials": request.trials,
        "top_correct": 0,
        "top_wrong": 0,
        "auto_accept": 0,
        "auto_accept_correct": 0,
        "auto_accept_wrong": 0,
        "flagged": 0,
        "flagged_correct": 0,
        "flagged_wrong": 0,
        "inconsistent": 0,
        "ambiguous": 0,
        "confident": 0,
        "erasures": 0,
        "misreads": 0,
    }
    examples: List[dict] = []

    for _ in range(request.trials):
        true_name = rng.choice(names)
        true_codeword = codewords[true_name]

        observations = []
        seen_labels: List[Optional[str]] = []
        num_erasures = 0
        num_misreads = 0
        for index, (channel, symbol) in enumerate(zip(channels, true_codeword)):
            # A misread can only ever land on a colour that channel actually
            # has -- a restricted channel therefore has fewer ways to be wrong.
            channel_size = channels.max_addressable_symbol(index)
            roll = rng.random()
            if roll < request.p_erasure:
                observations.append(ChannelObservation.erasure())
                seen_labels.append(None)
                num_erasures += 1
                continue
            if roll < request.p_erasure + request.p_misread and channel_size > 1:
                wrong = rng.choice([s for s in range(channel_size) if s != symbol])
                num_misreads += 1
            else:
                wrong = symbol
            label = channel.index_to_label(wrong)
            observations.append(
                ChannelObservation.best_guess(label, request.confidence)
            )
            seen_labels.append(label)

        result = decode(
            reading=Reading(observations),
            candidates=codewords,
            channels=channels,
            thresholds=thresholds,
            code_min_distance=d,
        )

        correct = result.best == true_name
        auto = result.confident and not result.ambiguous and not result.inconsistent

        counts["erasures"] += num_erasures
        counts["misreads"] += num_misreads
        counts["top_correct" if correct else "top_wrong"] += 1
        counts["inconsistent"] += int(result.inconsistent)
        counts["ambiguous"] += int(result.ambiguous)
        counts["confident"] += int(result.confident)
        if auto:
            counts["auto_accept"] += 1
            counts["auto_accept_correct" if correct else "auto_accept_wrong"] += 1
        else:
            counts["flagged"] += 1
            counts["flagged_correct" if correct else "flagged_wrong"] += 1

        # Keep a few silent-failure examples: those are the ones worth staring at.
        if auto and not correct and len(examples) < 10:
            examples.append(
                {
                    "true_name": true_name,
                    "true_codeword": list(true_codeword),
                    "seen": seen_labels,
                    "decoded_as": result.best,
                    "posterior": result.best_posterior,
                    "num_erasures": num_erasures,
                    "num_misreads": num_misreads,
                }
            )

    trials = request.trials
    rates = {
        "top_correct": counts["top_correct"] / trials,
        "auto_accept": counts["auto_accept"] / trials,
        "auto_accept_wrong": counts["auto_accept_wrong"] / trials,
        "flagged": counts["flagged"] / trials,
        "inconsistent": counts["inconsistent"] / trials,
        "ambiguous": counts["ambiguous"] / trials,
    }
    if counts["auto_accept"]:
        rates["error_given_auto_accept"] = (
            counts["auto_accept_wrong"] / counts["auto_accept"]
        )
    else:
        rates["error_given_auto_accept"] = 0.0

    return {
        "counts": counts,
        "rates": rates,
        "silent_failure_examples": examples,
        "num_candidates": len(names),
        "code_min_distance": d,
    }


def demo_defaults() -> dict:
    """The config-file defaults, so the UI starts from the real scheme."""
    return {
        "palette": list(DEFAULT_PALETTE),
        "channel_names": list(DEFAULT_CHANNEL_NAMES),
        # Channels whose alphabet differs from the main palette carry it here,
        # so the workbench starts from the real (restricted) trousers channel
        # rather than silently widening it.
        "channels": [
            {"name": name, "labels": CHANNEL_PALETTES.get(name)}
            for name in DEFAULT_CHANNEL_NAMES
        ],
        "target_distance": DEFAULT_TARGET_DISTANCE,
        "thresholds": {
            "confident_threshold": DEFAULT_THRESHOLDS.confident_threshold,
            "ambiguous_margin": DEFAULT_THRESHOLDS.ambiguous_margin,
            "epsilon": DEFAULT_THRESHOLDS.epsilon,
        },
    }
