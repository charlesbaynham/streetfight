"""Minimal prime-field ``GF(p)`` arithmetic.

Pure Python, no dependencies. Only prime fields are supported (``p`` must be
prime). This is all the algebra the parity *and* Reed-Solomon codes need.

Non-prime prime powers (e.g. 4, 8, 9) would need ``GF(p^m)`` extension-field
arithmetic, which is out of scope: round the colour count up to the next prime
instead (see the plan, §3).
"""


def is_prime(n: int) -> bool:
    """Return ``True`` if ``n`` is a prime number."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


class GF:
    """Arithmetic over the prime field ``GF(p)``.

    Elements are plain ``int``s in ``[0, p)``. Every operation reduces its
    result mod ``p``.
    """

    def __init__(self, p: int):
        if not is_prime(p):
            raise ValueError(f"GF(p) requires a prime modulus; {p} is not prime")
        self.p = p

    def __repr__(self) -> str:
        return f"GF({self.p})"

    def _check(self, a: int) -> int:
        return a % self.p

    def add(self, a: int, b: int) -> int:
        return (a + b) % self.p

    def sub(self, a: int, b: int) -> int:
        return (a - b) % self.p

    def neg(self, a: int) -> int:
        return (-a) % self.p

    def mul(self, a: int, b: int) -> int:
        return (a * b) % self.p

    def inv(self, a: int) -> int:
        """Multiplicative inverse of ``a`` via Fermat's little theorem.

        ``a^(p-2) == a^-1 (mod p)`` for non-zero ``a``.
        """
        a = self._check(a)
        if a == 0:
            raise ZeroDivisionError("0 has no multiplicative inverse in GF(p)")
        return pow(a, self.p - 2, self.p)

    def div(self, a: int, b: int) -> int:
        return self.mul(a, self.inv(b))
