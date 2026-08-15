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


def parity_scheme():
    """The ``[3,2,2]`` parity config from the upgrade ladder (plan §2.5)."""
    return scheme_with_distance(2)


def all_candidates(scheme):
    """``{slot: codeword}`` for every identity that can actually be worn."""
    return {slot: scheme.codeword_of_slot(slot) for slot in scheme.usable_slots()}


def nth_usable(scheme, index):
    """A wearable slot, picked positionally so tests stay config-agnostic."""
    slots = scheme.usable_slots()
    return slots[index % len(slots)]


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
            # Wrap within the channel's own alphabet -- a vision model can only
            # ever report a colour that channel actually has.
            wrong = (symbol + 1) % scheme.channels.max_addressable_symbol(i)
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
    pytest.param(parity_scheme, id="parity-3-2-2"),
    pytest.param(default_scheme, id="rs-4-2-3"),
]


# -- clean reading ----------------------------------------------------------


@pytest.mark.parametrize("make_scheme", SCHEMES)
def test_clean_reading_identifies_player(make_scheme):
    scheme = make_scheme()
    target = nth_usable(scheme, 7)
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
    target = nth_usable(scheme, 11)
    reading = reading_for(scheme, scheme.codeword_of_slot(target), erase=(1,))
    result = run(scheme, reading)
    assert result.best == target
    assert not result.inconsistent  # erasure is correctable, not a fault
    assert result.confident


# -- single misread (detect vs correct, config-dependent) -------------------


def test_single_misread_parity_is_detected():
    # [3,2,2]: a lone misread cannot be corrected, only DETECTED -> inconsistent.
    scheme = parity_scheme()
    target = nth_usable(scheme, 9)
    reading = reading_for(scheme, scheme.codeword_of_slot(target), misread=(0,))
    result = run(scheme, reading)
    assert result.inconsistent


def test_single_misread_rs_is_corrected():
    # [4,2,3]: d=3 corrects one misread -> right player, NOT flagged inconsistent.
    scheme = default_scheme()
    target = nth_usable(scheme, 9)
    reading = reading_for(scheme, scheme.codeword_of_slot(target), misread=(0,))
    result = run(scheme, reading)
    assert result.best == target
    assert not result.inconsistent


# -- the compromise: erasure + misread on the parity code -------------------


def test_parity_erasure_plus_misread_is_the_compromise():
    # One hidden channel + one misread among the survivors: the parity code has
    # no check left and can silently decode to the WRONG player. This test pins
    # the documented limitation so it can't regress unnoticed.
    scheme = parity_scheme()
    target = nth_usable(scheme, 12)
    reading = reading_for(
        scheme, scheme.codeword_of_slot(target), erase=(0,), misread=(1,)
    )
    result = run(scheme, reading)
    assert result.best != target  # the compromise: confidently wrong


def test_gps_prior_recovers_the_compromise():
    # ...but a GPS-style prior favouring the true player rescues it (soft decode).
    scheme = parity_scheme()
    target = nth_usable(scheme, 12)
    reading = reading_for(
        scheme, scheme.codeword_of_slot(target), erase=(0,), misread=(1,)
    )
    prior = Prior({target: 100.0})
    result = run(scheme, reading, prior=prior)
    assert result.best == target


# -- prior breaks a tie -----------------------------------------------------


def test_prior_breaks_an_ambiguous_tie():
    scheme = default_scheme()
    a, b = nth_usable(scheme, 3), nth_usable(scheme, 17)
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
    target = nth_usable(scheme, 5)
    codeword = scheme.codeword_of_slot(target)
    obs = []
    for i, symbol in enumerate(codeword):
        channel = scheme.channels[i]
        dist = {channel.index_to_label(symbol): 0.8}
        # spread a little mass onto a neighbour to mimic a real model
        other = (symbol + 2) % scheme.channels.max_addressable_symbol(i)
        dist[channel.index_to_label(other)] = 0.2
        obs.append(ChannelObservation.distribution(dist))
    result = run(scheme, Reading(obs))
    assert result.best == target


# -- None-symbol candidates (overridden players) -----------------------------
#
# A candidate word may carry `None` at a position nobody can vouch for (an
# admin override on that player -- see overrides.py). These pin the two
# mechanisms decoder.py documents for that case: the likelihood loop skips a
# `None` candidate symbol (factor 1.0, like an erased observation already
# does), and `_hamming_distance` skips it too, which can flip `inconsistent`.


def test_none_candidate_symbol_is_immune_to_a_contradicting_reading():
    # Single candidate, so ranking can't rescue it: the masked channel must be
    # ignored on its own merits, not merely outcompeted by a rival.
    scheme = default_scheme()
    target = nth_usable(scheme, 8)
    codeword = scheme.codeword_of_slot(target)
    # The reading strongly (mis)reports channel 0 against the candidate's own
    # true colour there.
    reading = reading_for(scheme, codeword, misread=(0,))
    masked = {target: (None,) + tuple(codeword[1:])}

    result = decode(reading, masked, scheme.channels)

    assert result.best == target
    assert result.best_posterior == pytest.approx(1.0)  # only candidate
    assert result.min_distance_to_codeword == 0  # channel 0 skipped, not counted
    assert not result.inconsistent


def test_none_candidate_symbol_does_not_penalise_the_likelihood():
    # Two candidates, identical except channel 0: for the plain codewords the
    # reading's exact match at channel 0 favours candidate `a`. With channel 0
    # masked to None for `a`, that channel contributes a flat 1.0 for it
    # instead -- at least as favourable as any confidence-weighted match, so
    # `a`'s edge over `b` should not shrink.
    scheme = default_scheme()
    slots = scheme.usable_slots()
    a, b = slots[0], slots[1]
    assert scheme.codeword_of_slot(a)[0] != scheme.codeword_of_slot(b)[0]
    codeword_a = scheme.codeword_of_slot(a)
    reading = reading_for(scheme, codeword_a)  # exact match on every channel

    plain = {a: codeword_a, b: scheme.codeword_of_slot(b)}
    masked = {a: (None,) + tuple(codeword_a[1:]), b: scheme.codeword_of_slot(b)}

    plain_scores = dict(decode(reading, plain, scheme.channels).ranked)
    masked_scores = dict(decode(reading, masked, scheme.channels).ranked)

    assert masked_scores[a] / masked_scores[b] >= plain_scores[a] / plain_scores[b]


def test_none_candidate_symbol_can_flip_the_inconsistent_flag():
    # RS [4,2,3]: one erasure plus one (elsewhere) misread leaves no correction
    # budget (t = (d-1-e)//2 = 0), so the plain candidate set is flagged. But if
    # the misread channel is exactly the one an override has masked to None for
    # the true player, that position no longer counts as a disagreement for
    # them, and the flag clears.
    scheme = default_scheme()
    target = nth_usable(scheme, 20)
    codeword = scheme.codeword_of_slot(target)
    reading = reading_for(scheme, codeword, misread=(0,), erase=(1,))
    d = scheme.code.min_distance()

    plain = all_candidates(scheme)
    plain_result = decode(reading, plain, scheme.channels, code_min_distance=d)
    assert plain_result.inconsistent
    assert plain_result.min_distance_to_codeword == 1

    masked = dict(plain)
    masked[target] = (None,) + tuple(codeword[1:])
    masked_result = decode(reading, masked, scheme.channels, code_min_distance=d)

    assert masked_result.best == target
    assert masked_result.min_distance_to_codeword == 0
    assert not masked_result.inconsistent


def test_thresholds_are_configurable():
    scheme = default_scheme()
    target = nth_usable(scheme, 1)
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
