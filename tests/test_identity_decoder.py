"""Behavioural tests for the soft decoder -- the core of the module.

These encode the coding-theory guarantees *and* the documented compromise so
neither can regress silently. They are parametrised over two configs to prove
the decoder is config-agnostic:

* the initial ``[3,2,2]`` parity scheme, and
* the ``[4,2,3]`` Reed-Solomon upgrade.

No DB, no network, no Pillow: readings, candidates and priors are fed directly.
"""

import pytest

from backend.identity.config import default_scheme
from backend.identity.config import scheme_with_distance
from backend.identity.decoder import DecoderThresholds
from backend.identity.decoder import decode
from backend.identity.observations import ChannelObservation
from backend.identity.observations import Prior
from backend.identity.observations import Reading

HIGH = 0.9  # vision confidence for a clean per-channel read


# -- helpers ----------------------------------------------------------------


def all_candidates(scheme):
    """``{slot: codeword}`` for every identity the scheme can express."""
    return {slot: scheme.codeword_of_slot(slot) for slot in range(scheme.capacity)}


def correct_obs(scheme, channel_index, symbol, confidence=HIGH):
    channel = scheme.channels[channel_index]
    return ChannelObservation.best_guess(channel.index_to_label(symbol), confidence)


def reading_for(scheme, codeword, erase=(), misread=()):
    """Build a Reading for a target ``codeword``.

    ``erase`` -- channel indices reported as obscured.
    ``misread`` -- channel indices reported as a (deterministic) wrong colour.
    """
    obs = []
    for i, symbol in enumerate(codeword):
        if i in erase:
            obs.append(ChannelObservation.erasure())
        elif i in misread:
            wrong = (symbol + 1) % scheme.channels.q
            obs.append(correct_obs(scheme, i, wrong))
        else:
            obs.append(correct_obs(scheme, i, symbol))
    return Reading(obs)


def run(scheme, reading, prior=None, candidates=None):
    return decode(
        reading,
        candidates if candidates is not None else all_candidates(scheme),
        scheme.channels,
        prior=prior,
        code_min_distance=scheme.code.min_distance(),
    )


# Param: (scheme factory, label) for the config-agnostic suite.
SCHEMES = [
    pytest.param(default_scheme, id="parity-3-2-2"),
    pytest.param(lambda: scheme_with_distance(3), id="rs-4-2-3"),
]


# -- clean reading ----------------------------------------------------------


@pytest.mark.parametrize("make_scheme", SCHEMES)
def test_clean_reading_identifies_player(make_scheme):
    scheme = make_scheme()
    target = 7
    reading = reading_for(scheme, scheme.codeword_of_slot(target))
    result = run(scheme, reading)
    assert result.best == target
    assert result.best_posterior > 0.99
    assert result.confident
    assert not result.inconsistent
    assert not result.ambiguous


# -- single erasure (erasure correction) ------------------------------------


@pytest.mark.parametrize("make_scheme", SCHEMES)
def test_single_erasure_is_corrected(make_scheme):
    scheme = make_scheme()
    target = 11
    reading = reading_for(scheme, scheme.codeword_of_slot(target), erase=(1,))
    result = run(scheme, reading)
    assert result.best == target
    assert not result.inconsistent  # erasure is correctable, not a fault
    assert result.confident


# -- single misread (detect vs correct, config-dependent) -------------------


def test_single_misread_parity_is_detected():
    # [3,2,2]: a lone misread cannot be corrected, only DETECTED -> inconsistent.
    scheme = default_scheme()
    target = 9
    reading = reading_for(scheme, scheme.codeword_of_slot(target), misread=(0,))
    result = run(scheme, reading)
    assert result.inconsistent


def test_single_misread_rs_is_corrected():
    # [4,2,3]: d=3 corrects one misread -> right player, NOT flagged inconsistent.
    scheme = scheme_with_distance(3)
    target = 9
    reading = reading_for(scheme, scheme.codeword_of_slot(target), misread=(0,))
    result = run(scheme, reading)
    assert result.best == target
    assert not result.inconsistent


# -- the compromise: erasure + misread on the parity code -------------------


def test_parity_erasure_plus_misread_is_the_compromise():
    # One hidden channel + one misread among the survivors: the parity code has
    # no check left and can silently decode to the WRONG player. This test pins
    # the documented limitation so it can't regress unnoticed.
    scheme = default_scheme()
    target = 12
    reading = reading_for(
        scheme, scheme.codeword_of_slot(target), erase=(0,), misread=(1,)
    )
    result = run(scheme, reading)
    assert result.best != target  # the compromise: confidently wrong


def test_gps_prior_recovers_the_compromise():
    # ...but a GPS-style prior favouring the true player rescues it (soft decode).
    scheme = default_scheme()
    target = 12
    reading = reading_for(
        scheme, scheme.codeword_of_slot(target), erase=(0,), misread=(1,)
    )
    prior = Prior({target: 100.0})
    result = run(scheme, reading, prior=prior)
    assert result.best == target


# -- prior breaks a tie -----------------------------------------------------


def test_prior_breaks_an_ambiguous_tie():
    scheme = default_scheme()
    a, b = 3, 17
    candidates = {a: scheme.codeword_of_slot(a), b: scheme.codeword_of_slot(b)}
    # Everything erased -> the reading carries no information: a pure tie.
    reading = Reading([ChannelObservation.erasure() for _ in range(scheme.channels.n)])

    no_prior = run(scheme, reading, candidates=candidates)
    assert no_prior.ambiguous
    assert no_prior.ranked[0][1] == pytest.approx(no_prior.ranked[1][1])

    primed = run(scheme, reading, prior=Prior({a: 10.0, b: 1.0}), candidates=candidates)
    assert primed.best == a


# -- distribution-style observations also work ------------------------------


def test_distribution_observation_decodes():
    scheme = default_scheme()
    target = 5
    codeword = scheme.codeword_of_slot(target)
    obs = []
    for i, symbol in enumerate(codeword):
        channel = scheme.channels[i]
        dist = {channel.index_to_label(symbol): 0.8}
        # spread a little mass onto a neighbour to mimic a real model
        other = (symbol + 2) % scheme.channels.q
        dist[channel.index_to_label(other)] = 0.2
        obs.append(ChannelObservation.distribution(dist))
    result = run(scheme, Reading(obs))
    assert result.best == target


def test_thresholds_are_configurable():
    scheme = default_scheme()
    target = 1
    reading = reading_for(scheme, scheme.codeword_of_slot(target))

    def confident_under(threshold):
        return decode(
            reading,
            all_candidates(scheme),
            scheme.channels,
            thresholds=DecoderThresholds(confident_threshold=threshold),
            code_min_distance=scheme.code.min_distance(),
        ).confident

    # A loose threshold accepts the clean read; an impossibly strict one rejects
    # it -- proving the flag thresholds are configuration, not hard-coded.
    assert confident_under(0.6)
    assert not confident_under(1.0 + 1e-9)
