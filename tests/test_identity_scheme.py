"""Tests for IdentityScheme: deterministic, unique assignment; capacity limits;
appearance<->codeword<->slot consistency; and the restricted-channel handling."""

import pytest

from backend.identity.config import DEFAULT_Q
from backend.identity.config import TROUSERS_PALETTE
from backend.identity.config import default_scheme
from backend.identity.scheme import IdentityScheme

# 49 codewords, less the 14 whose trousers symbol has no colour, less slot 0.
NUM_USABLE = 34


def test_default_scheme_capacity():
    scheme = default_scheme()
    assert scheme.capacity == 49
    assert scheme.channels.n == 4
    assert scheme.code.k == 2
    assert scheme.code.min_distance() == 3


def test_usable_slots_excludes_unwearable_codewords_and_slot_zero():
    scheme = default_scheme()
    slots = scheme.usable_slots()

    assert len(slots) == NUM_USABLE
    assert 0 not in slots

    trousers_index = scheme.channels.names.index("trousers")
    for slot in slots:
        assert scheme.codeword_of_slot(slot)[trousers_index] < len(TROUSERS_PALETTE)


def test_slot_zero_is_all_black():
    scheme = default_scheme()
    assert scheme.appearance_of_slot(0) == {
        "tshirt": "black",
        "trousers": "black",
        "hat": "black",
        "armbands": "black",
    }


def test_unwearable_slots_raise_rather_than_inventing_a_colour():
    scheme = default_scheme()
    unusable = set(range(scheme.capacity)) - set(scheme.usable_slots()) - {0}
    assert unusable  # the restricted trousers palette must rule *something* out

    for slot in unusable:
        with pytest.raises(ValueError):
            scheme.appearance_of_slot(slot)


def test_assignment_is_deterministic_and_unique():
    scheme = default_scheme()
    players = [f"player-{i}" for i in range(NUM_USABLE)]
    assignment = scheme.assign(players)

    assert assignment == scheme.assign(players)  # deterministic
    assert sorted(assignment.values()) == scheme.usable_slots()


def test_assignment_only_hands_out_wearable_outfits():
    scheme = default_scheme()
    players = [f"player-{i}" for i in range(NUM_USABLE)]
    # Would raise if any assigned slot were unwearable
    appearances = scheme.appearances_for(scheme.assign(players))
    assert len(appearances) == NUM_USABLE


def test_assignment_rejects_too_many_players():
    scheme = default_scheme()
    with pytest.raises(ValueError):
        scheme.assign([f"player-{i}" for i in range(NUM_USABLE + 1)])


def test_slot_codeword_roundtrip():
    scheme = default_scheme()
    for slot in range(scheme.capacity):
        codeword = scheme.codeword_of_slot(slot)
        assert scheme.slot_of_codeword(codeword) == slot


def test_appearance_matches_codeword():
    scheme = default_scheme()
    for slot in scheme.usable_slots():
        codeword = scheme.codeword_of_slot(slot)
        appearance = scheme.appearance_of_slot(slot)
        assert scheme.channels.appearance_to_codeword(appearance) == codeword


def test_every_codeword_satisfies_the_documented_closed_form():
    # Plan §11: with t-shirt and trousers as the free pair,
    #   hat      = (2*trousers -   t-shirt) mod 7
    #   armbands = (3*trousers - 2*t-shirt) mod 7
    scheme = default_scheme()
    for slot in range(scheme.capacity):
        tshirt, trousers, hat, armbands = scheme.codeword_of_slot(slot)
        assert hat == (2 * trousers - tshirt) % DEFAULT_Q
        assert armbands == (3 * trousers - 2 * tshirt) % DEFAULT_Q


def test_appearances_are_all_distinct():
    scheme = default_scheme()
    players = [f"p{i}" for i in range(NUM_USABLE)]
    appearances = scheme.appearances_for(scheme.assign(players))
    seen = {tuple(sorted(a.items())) for a in appearances.values()}
    assert len(seen) == NUM_USABLE


def test_any_two_channels_identify_the_player():
    # The headline guarantee of the [4,2,3] code (plan §2.4): whichever two
    # garments happen to be visible, they pin down a unique player.
    scheme = default_scheme()
    n = scheme.channels.n
    for first in range(n):
        for second in range(first + 1, n):
            pairs = {
                (scheme.codeword_of_slot(s)[first], scheme.codeword_of_slot(s)[second])
                for s in range(scheme.capacity)
            }
            assert len(pairs) == scheme.capacity


def test_scheme_rejects_mismatched_channels_and_code():
    from backend.identity.code import parity_code
    from backend.identity.config import default_channel_set

    channels = default_channel_set()  # n = 4
    code = parity_code(3, DEFAULT_Q)  # n = 3
    with pytest.raises(ValueError):
        IdentityScheme(channels=channels, code=code)


# -- codewords_matching -----------------------------------------------------


def _erase(codeword, *channel_indices):
    return [
        None if i in channel_indices else symbol for i, symbol in enumerate(codeword)
    ]


def test_codewords_matching_with_no_erasures_finds_exactly_the_word():
    scheme = default_scheme()
    for slot in scheme.usable_slots():
        codeword = scheme.codeword_of_slot(slot)
        assert scheme.codewords_matching(list(codeword)) == [codeword]


def test_one_erasure_still_identifies_a_unique_codeword():
    scheme = default_scheme()
    for slot in scheme.usable_slots():
        codeword = scheme.codeword_of_slot(slot)
        for erased in range(scheme.channels.n):
            matches = scheme.codewords_matching(_erase(codeword, erased))
            assert matches == [codeword]


def test_one_erasure_plus_a_misread_matches_nothing():
    # d = 3 with one erasure leaves one check symbol, so a corrupted reading is
    # detected rather than silently decoded.
    scheme = default_scheme()
    codeword = scheme.codeword_of_slot(scheme.usable_slots()[0])

    corrupted = list(codeword)
    corrupted[0] = (corrupted[0] + 1) % DEFAULT_Q
    corrupted[3] = None

    assert scheme.codewords_matching(corrupted) == []


def test_two_erasures_vouch_for_nothing():
    # k = 2, so any two readable symbols always complete to exactly one
    # codeword whatever they are. The check is vacuous and callers must not
    # treat a match here as evidence.
    scheme = default_scheme()
    for a in range(DEFAULT_Q):
        for b in range(DEFAULT_Q):
            matches = scheme.codewords_matching([a, b, None, None])
            assert len(matches) == 1


def test_all_erased_matches_every_codeword():
    scheme = default_scheme()
    assert len(scheme.codewords_matching([None] * 4)) == scheme.capacity


def test_codewords_matching_rejects_the_wrong_number_of_channels():
    scheme = default_scheme()
    with pytest.raises(ValueError):
        scheme.codewords_matching([0, 1, 2])
