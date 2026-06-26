"""Linear block codes over ``GF(q)``.

A :class:`LinearCode` is, abstractly, a set of codewords (length-``n`` tuples of
symbols in ``[0, q)``) together with an ``encode`` map from messages. The
decoder and scheme depend **only** on this abstract interface, so swapping the
parity code for Reed-Solomon, adding a channel, or growing ``q`` constructs a
*different* ``LinearCode`` and nothing downstream changes. That is the
extensibility guarantee from the plan (§4).

Two concrete families are provided via factories:

* :func:`parity_code` -- the ``[n, n-1, 2]`` sum-parity code (the initial
  ``parity_code(3, 5)`` config), and
* :func:`reed_solomon_code` -- the ``[n, k, n-k+1]`` MDS code used for the
  ``[4,2,3]`` / ``[5,2,4]`` upgrades.

:func:`build_code` picks between them for a requested ``(n, q, target_distance)``
and raises a clear error when the request is infeasible.
"""

from itertools import product
from typing import Iterable
from typing import Iterator
from typing import List
from typing import Tuple

from backend.identity.galois import GF
from backend.identity.galois import is_prime

Codeword = Tuple[int, ...]
Message = Tuple[int, ...]


class LinearCode:
    """A linear ``[n, k]`` code over ``GF(q)``.

    Subclasses implement :meth:`encode`. Everything else (codeword enumeration,
    minimum distance, syndrome-free membership test) is derived generically so
    tests can assert the theoretical distance against a brute-force oracle.
    """

    def __init__(self, n: int, k: int, q: int):
        if not is_prime(q):
            raise ValueError(
                f"q must be prime for the dependency-free GF(q); {q} is not prime"
            )
        if not 0 < k <= n:
            raise ValueError(f"require 0 < k <= n; got n={n}, k={k}")
        self.n = n
        self.k = k
        self.q = q
        self.field = GF(q)

    # -- abstract surface -------------------------------------------------

    def encode(self, message: Message) -> Codeword:
        """Map a length-``k`` message (symbols over ``GF(q)``) to a codeword."""
        raise NotImplementedError

    # -- derived surface --------------------------------------------------

    @property
    def capacity(self) -> int:
        """Number of distinct codewords (= distinct identities), ``q**k``."""
        return self.q**self.k

    def messages(self) -> Iterator[Message]:
        """Enumerate every length-``k`` message over ``GF(q)``."""
        return product(range(self.q), repeat=self.k)

    def codewords(self) -> Iterator[Codeword]:
        """Enumerate every codeword (one per message)."""
        for message in self.messages():
            yield self.encode(message)

    def is_codeword(self, word: Iterable[int]) -> bool:
        """Return ``True`` if ``word`` is a valid codeword of this code."""
        word = tuple(word)
        if len(word) != self.n:
            return False
        return word in set(self.codewords())

    def min_distance(self) -> int:
        """Minimum Hamming distance, computed by brute force.

        Fine for these tiny codes, and it doubles as the test oracle for the
        theoretical ``d`` (``[3,2,2]``->2, ``[4,2,3]``->3, ``[5,2,4]``->4).
        """
        words: List[Codeword] = list(self.codewords())
        best = self.n
        for i in range(len(words)):
            for j in range(i + 1, len(words)):
                dist = sum(1 for a, b in zip(words[i], words[j]) if a != b)
                if dist < best:
                    best = dist
        return best


class ParityCode(LinearCode):
    """The ``[n, n-1, 2]`` sum-parity code over ``GF(q)``.

    The first ``n-1`` symbols are free (the message); the last symbol is chosen
    so that ``sum(symbols) % q == 0``. Minimum distance is 2, so it can correct
    one erasure *or* detect one misread.
    """

    def __init__(self, n: int, q: int):
        if n < 2:
            raise ValueError(f"parity code needs n >= 2; got n={n}")
        super().__init__(n=n, k=n - 1, q=q)

    def encode(self, message: Message) -> Codeword:
        if len(message) != self.k:
            raise ValueError(f"message must have length k={self.k}; got {len(message)}")
        body = tuple(m % self.q for m in message)
        parity = (-sum(body)) % self.q
        return body + (parity,)


class ReedSolomonCode(LinearCode):
    """The ``[n, k, n-k+1]`` (MDS) Reed-Solomon code over ``GF(q)``.

    A message ``(m_0, ..., m_{k-1})`` defines the polynomial
    ``f(x) = m_0 + m_1 x + ... + m_{k-1} x^{k-1}``; the codeword is ``f``
    evaluated at ``n`` distinct points of ``GF(q)``. Requires ``n <= q``.
    """

    def __init__(self, n: int, k: int, q: int, points: Iterable[int] = None):
        if n > q:
            raise ValueError(
                f"Reed-Solomon requires n <= q (distinct eval points); got n={n}, q={q}"
            )
        super().__init__(n=n, k=k, q=q)
        if points is None:
            points = range(n)
        self.points = tuple(p % q for p in points)
        if len(set(self.points)) != n:
            raise ValueError("Reed-Solomon evaluation points must be distinct")

    def encode(self, message: Message) -> Codeword:
        if len(message) != self.k:
            raise ValueError(f"message must have length k={self.k}; got {len(message)}")
        coeffs = [m % self.q for m in message]
        word = []
        for x in self.points:
            acc = 0
            power = 1
            for c in coeffs:
                acc = self.field.add(acc, self.field.mul(c, power))
                power = self.field.mul(power, x)
            word.append(acc)
        return tuple(word)


def parity_code(n: int, q: int) -> ParityCode:
    """Build the ``[n, n-1, 2]`` sum-parity code over ``GF(q)``."""
    return ParityCode(n=n, q=q)


def reed_solomon_code(n: int, k: int, q: int) -> ReedSolomonCode:
    """Build the ``[n, k, n-k+1]`` Reed-Solomon (MDS) code over ``GF(q)``."""
    return ReedSolomonCode(n=n, k=k, q=q)


def build_code(n: int, q: int, target_distance: int) -> LinearCode:
    """Return a code over ``GF(q)`` of length ``n`` with distance
    ``target_distance``, picking the simplest construction that achieves it.

    * ``target_distance == 2`` -> parity code (maximises capacity at ``d=2``).
    * ``target_distance > 2``  -> Reed-Solomon MDS code with ``k = n - d + 1``.

    Raises a clear :class:`ValueError` when the request is infeasible:

    * ``d`` must satisfy ``1 <= d <= n`` (the ``d <= n`` ceiling), and
    * an MDS code needs ``n <= q`` and ``k = n - d + 1 >= 1``.
    """
    if target_distance < 1:
        raise ValueError(f"target_distance must be >= 1; got {target_distance}")
    if target_distance > n:
        raise ValueError(
            f"infeasible: minimum distance cannot exceed n ({target_distance} > {n}); "
            "add channels (increase n) to buy more fault tolerance"
        )
    if target_distance == 1:
        # d=1 is the trivial full code: every word is a codeword. Model it as a
        # length-n parity-free code via Reed-Solomon with k=n.
        return reed_solomon_code(n=n, k=n, q=q)
    if target_distance == 2:
        return parity_code(n=n, q=q)
    k = n - target_distance + 1
    if k < 1:
        raise ValueError(
            f"infeasible: k = n - d + 1 = {k} < 1 for n={n}, d={target_distance}"
        )
    if n > q:
        raise ValueError(
            f"infeasible: a d={target_distance} MDS code needs n <= q, but n={n} > q={q}; "
            "increase the colour count q (to the next prime) or reduce n"
        )
    return reed_solomon_code(n=n, k=k, q=q)
