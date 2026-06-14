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
from typing import Iterable
from typing import List
from typing import Mapping
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

    def assign(self, player_ids: Iterable) -> Dict:
        """Deterministically assign each player a slot ``0, 1, 2, ...``.

        Returns ``{player_id: slot}``. Raises if there are more players than
        :attr:`capacity`. Order follows the iterable, so callers control which
        player gets which slot.
        """
        player_ids = list(player_ids)
        if len(player_ids) > self.capacity:
            raise ValueError(
                f"{len(player_ids)} players exceed scheme capacity {self.capacity}"
            )
        return {player_id: slot for slot, player_id in enumerate(player_ids)}

    def codewords_for(self, assignment: Mapping) -> Dict:
        """Map a ``{player_id: slot}`` assignment to ``{player_id: codeword}``."""
        return {
            player_id: self.codeword_of_slot(slot)
            for player_id, slot in assignment.items()
        }

    def appearances_for(self, assignment: Mapping) -> Dict[object, Dict[str, str]]:
        """Map a ``{player_id: slot}`` assignment to ``{player_id: appearance}``."""
        return {
            player_id: self.appearance_of_slot(slot)
            for player_id, slot in assignment.items()
        }
