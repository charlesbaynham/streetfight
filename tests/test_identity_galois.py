"""Field-axiom tests for the prime-field arithmetic (no DB, no network)."""

import pytest

from backend.identity.galois import GF
from backend.identity.galois import is_prime


@pytest.mark.parametrize("p", [2, 3, 5, 7, 11, 13])
def test_is_prime_accepts_primes(p):
    assert is_prime(p)


@pytest.mark.parametrize("n", [0, 1, 4, 6, 8, 9, 15, 25])
def test_is_prime_rejects_composites(n):
    assert not is_prime(n)


@pytest.mark.parametrize("p", [4, 6, 8, 9, 1, 0])
def test_gf_rejects_composite_modulus(p):
    with pytest.raises(ValueError):
        GF(p)


@pytest.mark.parametrize("p", [5, 7])
def test_additive_inverse(p):
    field = GF(p)
    for a in range(p):
        assert field.add(a, field.neg(a)) == 0


@pytest.mark.parametrize("p", [5, 7])
def test_multiplicative_inverse(p):
    field = GF(p)
    for a in range(1, p):
        assert field.mul(a, field.inv(a)) == 1


def test_zero_has_no_inverse():
    field = GF(5)
    with pytest.raises(ZeroDivisionError):
        field.inv(0)


def test_arithmetic_reduces_mod_p():
    field = GF(5)
    assert field.add(3, 4) == 2
    assert field.sub(1, 3) == 3
    assert field.mul(3, 4) == 2
    assert field.div(3, 4) == field.mul(3, field.inv(4))
