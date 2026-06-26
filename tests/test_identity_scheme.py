"""Tests for IdentityScheme: deterministic, unique assignment; capacity limits;
and appearance<->codeword<->slot consistency."""

import pytest

from backend.identity.config import default_scheme
from backend.identity.scheme import IdentityScheme


def test_default_scheme_capacity():
    scheme = default_scheme()
    assert scheme.capacity == 25


def test_assignment_is_deterministic_and_unique():
    scheme = default_scheme()
    players = [f"player-{i}" for i in range(25)]
    assignment = scheme.assign(players)
    assert assignment == scheme.assign(players)  # deterministic
    slots = list(assignment.values())
    assert sorted(slots) == list(range(25))  # unique, dense


def test_assignment_rejects_too_many_players():
    scheme = default_scheme()
    with pytest.raises(ValueError):
        scheme.assign([f"player-{i}" for i in range(26)])


def test_slot_codeword_roundtrip():
    scheme = default_scheme()
    for slot in range(scheme.capacity):
        codeword = scheme.codeword_of_slot(slot)
        assert scheme.slot_of_codeword(codeword) == slot


def test_appearance_matches_codeword():
    scheme = default_scheme()
    for slot in range(scheme.capacity):
        codeword = scheme.codeword_of_slot(slot)
        appearance = scheme.appearance_of_slot(slot)
        assert scheme.channels.appearance_to_codeword(appearance) == codeword


def test_every_appearance_satisfies_parity():
    # For the [3,2,2] parity scheme, the colour indices sum to 0 mod 5.
    scheme = default_scheme()
    for slot in range(scheme.capacity):
        codeword = scheme.codeword_of_slot(slot)
        assert sum(codeword) % 5 == 0


def test_appearances_are_all_distinct():
    scheme = default_scheme()
    appearances = scheme.appearances_for(scheme.assign([f"p{i}" for i in range(25)]))
    seen = {tuple(sorted(a.items())) for a in appearances.values()}
    assert len(seen) == 25


def test_scheme_rejects_mismatched_channels_and_code():
    from backend.identity.code import parity_code
    from backend.identity.config import default_channel_set

    channels = default_channel_set()  # n = 3
    code = parity_code(4, 5)  # n = 4
    with pytest.raises(ValueError):
        IdentityScheme(channels=channels, code=code)
