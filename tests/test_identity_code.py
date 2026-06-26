"""Tests for the linear codes: capacity, minimum distance, encode round-trips,
and infeasibility errors. The brute-force ``min_distance`` is the oracle for the
theoretical distances."""

import pytest

from backend.identity.code import build_code
from backend.identity.code import parity_code
from backend.identity.code import reed_solomon_code


def test_parity_code_3_5_basics():
    code = parity_code(3, 5)
    assert code.n == 3
    assert code.k == 2
    assert code.q == 5
    assert code.capacity == 25
    assert code.min_distance() == 2


def test_parity_codewords_sum_to_zero_mod_q():
    code = parity_code(3, 5)
    words = list(code.codewords())
    assert len(words) == 25
    assert len(set(words)) == 25
    for word in words:
        assert sum(word) % 5 == 0


def test_parity_encode_roundtrip_and_membership():
    code = parity_code(3, 5)
    for message in code.messages():
        word = code.encode(message)
        assert word[: code.k] == message  # systematic in the leading k
        assert code.is_codeword(word)


def test_parity_rejects_non_codeword():
    code = parity_code(3, 5)
    # (1, 1, 1) sums to 3, not 0 mod 5.
    assert not code.is_codeword((1, 1, 1))


def test_reed_solomon_distances():
    assert reed_solomon_code(4, 2, 5).min_distance() == 3
    assert reed_solomon_code(5, 2, 5).min_distance() == 4


def test_reed_solomon_capacity_and_roundtrip():
    code = reed_solomon_code(4, 2, 5)
    assert code.capacity == 25
    words = list(code.codewords())
    assert len(set(words)) == 25
    for message in code.messages():
        assert code.encode(message) == code.encode(message)


def test_build_code_picks_parity_for_d2():
    code = build_code(3, 5, target_distance=2)
    assert code.min_distance() == 2
    assert code.capacity == 25


def test_build_code_picks_rs_for_higher_distance():
    code = build_code(4, 5, target_distance=3)
    assert code.min_distance() == 3
    code = build_code(5, 5, target_distance=4)
    assert code.min_distance() == 4


def test_build_code_rejects_distance_above_n():
    # d <= n ceiling: d=4 at n=3 is infeasible.
    with pytest.raises(ValueError):
        build_code(3, 5, target_distance=4)


def test_reed_solomon_rejects_n_greater_than_q():
    with pytest.raises(ValueError):
        reed_solomon_code(6, 2, 5)


def test_build_code_rejects_rs_with_n_greater_than_q():
    with pytest.raises(ValueError):
        build_code(6, 5, target_distance=3)
