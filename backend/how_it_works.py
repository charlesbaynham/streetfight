"""What the ``/how-it-works`` essay needs from the running game.

The essay (``react-ui/src/HowItWorks.js``) explains the identity scheme to the
players wearing it, and two of its three figures are *about* that scheme: the
grid of safe outfits, and where the reader's own outfit sits on it. So they
are served from :func:`~backend.identity.config.default_scheme` rather than
drawn once and checked in as a picture. A palette edit, a channel added, or a
change to the code's parameters must not be able to leave a published essay
quietly lying about what the players are wearing.

Nothing here writes, and nothing here creates a ``User`` row: the essay is
linked from the outfit picker's footer and opens in a new tab, so a player who
has not picked yet (or a passer-by with no session at all) must get the
general figures and no personal ones, not an empty player.
"""

import logging
from typing import List
from typing import Optional
from typing import Tuple
from uuid import UUID

from fastapi import HTTPException

from .admin_interface import AdminInterface
from .identity.config import default_scheme
from .identity.overrides import Word
from .identity.overrides import overlap_distance
from .identity.scheme import IdentityScheme
from .identity_admin import appearance_payload
from .identity_admin import effective_words
from .identity_admin import provided_channels

logger = logging.getLogger(__name__)

# How many of the reader's nearest neighbours the essay shows. Three is enough
# to see that the nearest is a long way off, and short enough to read on a
# phone.
NEIGHBOURS_SHOWN = 3


def _position(word: Word, q: int) -> Optional[Tuple[int, int]]:
    """Where a four-symbol word sits on the grid of all possible outfits.

    Rows are the pair the player chooses (t-shirt, trousers), columns the pair
    we hand out (hat, armband), so the grid's two axes are also the two halves
    of the story the essay tells. ``None`` for a word with an uninformative
    position: it is somewhere along a line rather than at a point, and drawing
    it at a point would be a lie.
    """
    if len(word) != 4 or any(symbol is None for symbol in word):
        return None
    return (word[0] * q + word[1], word[2] * q + word[3])


def codeword_grid(scheme: IdentityScheme) -> Optional[dict]:
    """Every codeword as one cell of a square grid of *all* the combinations.

    The figure this feeds (F3) makes two points at once. The lit cells are
    sparse -- 49 of 2401 -- which is the price of the spacing. And because the
    code is MDS with ``k = 2``, fixing any two garments determines the other
    two, so exactly one cell is lit in each row and each column: the grid is a
    permutation matrix. That is a property of the scheme, not of the drawing,
    and ``tests/test_how_it_works.py`` asserts it rather than trusting it.

    ``None`` when the scheme is not four channels wide, since then there is no
    pair-of-pairs to put on two axes. The page hides the figure rather than
    inventing a projection.
    """
    if scheme.channels.n != 4:
        return None

    q = scheme.code.q
    usable = set(scheme.usable_slots())
    cells = []
    for slot in range(scheme.capacity):
        position = _position(scheme.codeword_of_slot(slot), q)
        if position is None:  # pragma: no cover - codewords are never partial
            continue
        row, col = position
        cells.append({"slot": slot, "row": row, "col": col, "usable": slot in usable})

    names = list(scheme.channels.names)
    return {
        "size": q * q,
        "total": (q * q) ** 2,
        "cells": cells,
        "row_channels": names[:2],
        "col_channels": names[2:],
    }


def _outfit(word: Word, scheme: IdentityScheme, slot: Optional[int]) -> dict:
    """One outfit as the essay draws it: the garments, and where it sits."""
    position = _position(word, scheme.code.q)
    return {
        "slot": slot,
        "appearance": appearance_payload(word, scheme),
        "row": None if position is None else position[0],
        "col": None if position is None else position[1],
    }


def _caller(user_id: UUID):
    """The reader's own ``User`` row, or ``None``.

    ``get_user_model`` raises rather than creating, which is what we want:
    a reader who has never played is a stranger to this page, not a new
    player.
    """
    try:
        return AdminInterface().get_user_model(user_id)
    except HTTPException:
        return None


def _roster(caller) -> List:
    """Everyone in the reader's game, or nothing if they are not in one yet."""
    if caller.game_id is None:
        return []
    return AdminInterface().get_users_for_game(caller.game_id)


def off_codeword_positions(roster: List, scheme: IdentityScheme) -> List[dict]:
    """Where the players who are *not* wearing a codeword sit on the grid.

    A player who overrode a garment -- because they owned no shirt in any of
    the colours the scheme offered them, mostly -- is no longer at one of the
    49 lit cells. They are still perfectly identifiable (identification scores
    the photograph against what each player is actually wearing, not against
    the codebook) but they have spent some of their own separation to get
    there, and the figure should say so rather than quietly leave them off.

    Anonymous, unlike the neighbours: this is the whole roster, and thirty
    names would bury the figure. A player whose override blanks a channel
    outright has no single cell to sit in and is left out.
    """
    seen = set()
    for word in effective_words(roster, scheme).values():
        if scheme.code.is_codeword(word):
            continue
        position = _position(word, scheme.code.q)
        if position is not None:
            seen.add(position)
    return [{"row": row, "col": col} for row, col in sorted(seen)]


def _neighbours(
    caller, word: Word, scheme: IdentityScheme, roster: List
) -> Tuple[List[dict], int]:
    """The outfits nearest the reader's, closest first and **named**, with a
    count of how many players are tied at that nearest distance.

    That count is not decoration. Half of every MDS codeword's neighbours sit
    at exactly the minimum distance -- 24 of the other 48 here -- so in a
    thirty-player game roughly fifteen people are equally the closest, and
    which three come back is an arbitrary tiebreak on roster order. Showing
    three names without the count would claim a ranking that does not exist.

    Naming them does hand a player the outfits of the three people most easily
    confused with them, which is real information in a game where everyone is
    hiding. Charles's call (2026-09-16), and the right one: knowing who you
    might be mistaken for is the part of the scheme a player can act on, and
    it is what makes the figure about them rather than about the maths.
    """
    others = {other.id: other for other in roster if other.id != caller.id}

    scored = [
        (overlap_distance(word, other_word), other_id, other_word)
        for other_id, other_word in effective_words(
            list(others.values()), scheme
        ).items()
    ]
    scored.sort(key=lambda entry: entry[0])
    if not scored:
        return [], 0

    return [
        dict(
            _outfit(other_word, scheme, slot=None),
            distance=distance,
            name=others[other_id].name,
        )
        for distance, other_id, other_word in scored[:NEIGHBOURS_SHOWN]
    ], sum(1 for distance, _, _ in scored if distance == scored[0][0])


def how_it_works(user_id: UUID) -> dict:
    """Everything the essay's figures are drawn from, for this reader."""
    scheme = default_scheme()
    code = scheme.code

    you = None
    neighbours: List[dict] = []
    closest_count = 0
    overridden: List[dict] = []
    caller = _caller(user_id)
    word = None if caller is None else effective_words([caller], scheme).get(caller.id)
    if caller is not None and word is not None:
        roster = _roster(caller)
        you = dict(
            _outfit(word, scheme, caller.identity_slot),
            name=caller.name,
            provided=provided_channels(scheme),
        )
        neighbours, closest_count = _neighbours(caller, word, scheme, roster)
        overridden = off_codeword_positions(roster, scheme)

    return {
        "scheme": {
            "n": code.n,
            "k": code.k,
            "q": code.q,
            "distance": code.min_distance(),
            "capacity": scheme.capacity,
            "usable": len(scheme.usable_slots()),
            "combinations": code.q**code.n,
            "channels": list(scheme.channels.names),
        },
        "grid": codeword_grid(scheme),
        "you": you,
        "neighbours": neighbours,
        # How many players share the nearest distance -- see _neighbours.
        "closest_count": closest_count,
        # Players wearing something the codebook never offered -- see
        # off_codeword_positions. Anonymous, and includes the reader if they
        # overrode a garment themselves.
        "overridden": overridden,
    }
