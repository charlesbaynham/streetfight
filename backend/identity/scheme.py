"""``IdentityScheme``: binds a :class:`ChannelSet`, a :class:`LinearCode`, and a
player-to-codeword assignment.

A player's identity is stored as a stable integer **slot** in
``[0, capacity)``. The codeword (and hence the physical *appearance*) is derived
from the slot via the code's ``encode`` -- so the database only ever needs to
remember the slot, not the colour palette. The slot ``s`` is interpreted as a
base-``q`` message of length ``k`` and encoded.

Note (plan §8.2): the scheme parameters (palette, channels, code) are
effectively fixed for the life of a game, because changing them changes what
every player must physically wear. Treat a parameter change as a new game
setup, not a live migration.
"""

from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple

from backend.identity.channels import ChannelSet
from backend.identity.code import LinearCode

Codeword = Tuple[int, ...]


class IdentityScheme:
    """The binding of channels + code that turns slots into appearances."""

    def __init__(self, channels: ChannelSet, code: LinearCode):
        if channels.n != code.n:
            raise ValueError(f"channel count {channels.n} != code length {code.n}")
        if channels.q != code.q:
            raise ValueError(f"channel q {channels.q} != code q {code.q}")
        self.channels = channels
        self.code = code

    @property
    def capacity(self) -> int:
        """Maximum number of distinct player identities, ``q**k``."""
        return self.code.capacity

    # -- slot <-> message -------------------------------------------------

    def _slot_to_message(self, slot: int) -> Tuple[int, ...]:
        if not 0 <= slot < self.capacity:
            raise ValueError(f"slot {slot} out of range [0, {self.capacity})")
        q, k = self.code.q, self.code.k
        digits: List[int] = []
        for _ in range(k):
            digits.append(slot % q)
            slot //= q
        return tuple(digits)

    def _message_to_slot(self, message: Sequence[int]) -> int:
        q = self.code.q
        slot = 0
        for digit in reversed(message):
            slot = slot * q + (digit % q)
        return slot

    # -- public surface ---------------------------------------------------

    def codeword_of_slot(self, slot: int) -> Codeword:
        """Codeword (tuple of channel indices) for a player's slot."""
        return self.code.encode(self._slot_to_message(slot))

    def slot_of_codeword(self, codeword: Sequence[int]) -> int:
        """Inverse of :meth:`codeword_of_slot` for a *valid* codeword.

        The first ``k`` symbols of the codewords this scheme emits are the
        message itself (both the parity and Reed-Solomon-at-``0..n-1``
        constructions are systematic in their leading ``k`` positions for the
        configs we use), so the slot is recovered from them. Raises if the word
        is not a codeword of this scheme.
        """
        codeword = tuple(codeword)
        if not self.code.is_codeword(codeword):
            raise ValueError(f"{codeword} is not a valid codeword of this scheme")
        # Find the message whose encoding matches (robust to non-systematic
        # codes); brute force is cheap for these tiny capacities.
        for message in self.code.messages():
            if self.code.encode(message) == codeword:
                return self._message_to_slot(message)
        raise ValueError(f"{codeword} is not a valid codeword of this scheme")

    def appearance_of_slot(self, slot: int) -> Dict[str, str]:
        """What to physically wear: ``{channel_name: label}`` for a slot."""
        return self.channels.codeword_to_appearance(self.codeword_of_slot(slot))

    def usable_slots(self) -> List[int]:
        """The slots that can actually be assigned to a player.

        Two things disqualify a slot:

        * its codeword is not wearable, because a restricted channel has no
          label for the symbol it asks for (plan §2.6), and
        * it is slot 0, the all-zero codeword. Plan §11.1: that is black in
          every channel, which is both the single most likely outfit for a
          passer-by to be wearing by accident and where the vision model's
          failure mode piles up (it says "black" when it cannot tell).

        Only the second bites in the configured scheme, whose channels are now
        all full width, so this is 48 of the 49 codewords. The first is still
        live machinery: narrowing a channel again is a one-line config change.
        """
        return [
            slot
            for slot in range(self.capacity)
            if slot != 0 and self.channels.is_representable(self.codeword_of_slot(slot))
        ]

    def codewords_matching(
        self, hard_symbols: Sequence[Optional[int]]
    ) -> List[Codeword]:
        """Every codeword agreeing with ``hard_symbols`` on its readable positions.

        ``hard_symbols`` is one entry per channel, ``None`` for an erasure. This
        answers "is this a *valid outfit*", not "which player is this" -- the
        latter needs a candidate set and belongs in
        :func:`~backend.identity.decoder.decode`.

        Note how weak the answer gets as erasures pile up. For an MDS code with
        ``k`` information symbols, any ``k`` readable positions determine the
        codeword uniquely, so with exactly ``k`` left this always returns one
        match and vouches for nothing. Callers that want the code to actually
        *check* something must require more than ``k`` readable channels.
        """
        if len(hard_symbols) != self.channels.n:
            raise ValueError(
                f"got {len(hard_symbols)} symbols but the scheme has "
                f"{self.channels.n} channels"
            )
        readable = [
            (i, symbol) for i, symbol in enumerate(hard_symbols) if symbol is not None
        ]
        return [
            codeword
            for codeword in (
                self.code.encode(message) for message in self.code.messages()
            )
            if all(codeword[i] == symbol for i, symbol in readable)
        ]

    # There is deliberately no assign() here. Allocating slots by position in a
    # list looks convenient and is a trap: a player joining after the game has
    # started shifts everyone below them onto a different codeword, i.e. a
    # different outfit, which they are not wearing. A player's slot has to be
    # stored against the player and assigned before the game (guests have to
    # turn up in the right clothing), so it belongs with the User record rather
    # than in this pure module. See plan §8.2.
