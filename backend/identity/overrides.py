"""Per-player overrides: what to do when a guest's real outfit isn't their
assigned codeword.

The scheme (``scheme.py``) hands every player a slot, and the slot determines
a codeword, and the codeword determines an outfit -- but real guests do not
always turn up in it. "I couldn't find green trousers so I wore red" or a
last-minute joiner in whatever they happen to be wearing are the normal case,
not the exception, so the admin needs a way to record the *actual* outfit
without allocating a fresh scheme or lying about the player's slot.

An **override** is a sparse diff ``{channel_name: label_or_None}`` against a
player's assigned codeword: only the channels that differ from the assignment
need an entry, and ``None`` records "this garment is outside the palette /
unreadable" rather than any particular colour. Applying the diff to the slot's
codeword gives the player's **effective word** -- a :data:`Word`, which may
contain ``None`` positions and need not be a valid codeword at all. The
decoder (``decoder.py``) already tolerates ``None`` candidate symbols for
exactly this reason: an overridden player is scored like any other candidate,
just with fewer informative positions.

This module is pure and has three jobs, all in service of the admin overrides
workflow:

* turn a codeword + overrides into an effective word and back
  (:func:`effective_word`, :func:`overrides_for`);
* measure how well effective words separate from each other, counting only
  the positions both sides actually say something about
  (:func:`overlap_distance`, :func:`pairwise_distances`); and
* help the admin *choose* colours for the channels they still control --
  typically armbands handed out at the gate -- so the new player is as
  distinguishable as possible from everyone else already in play
  (:func:`suggest_free_channels`), and pick which slot to record the override
  against (:func:`nearest_slots`).

No database, web or vision imports (package-wide rule): this module only ever
sees codewords, labels and channel sets, never a ``User`` row.
"""

from itertools import product
from typing import Dict
from typing import Iterable
from typing import List
from typing import Mapping
from typing import NamedTuple
from typing import Optional
from typing import Sequence
from typing import Tuple

from backend.identity.channels import ChannelSet
from backend.identity.scheme import IdentityScheme

# A codeword-shaped tuple where ``None`` marks a position nobody can vouch for
# (out-of-palette garment, or simply "we don't know yet"). Unlike a
# ``Codeword`` this need not be a valid codeword of any code.
Word = Tuple[Optional[int], ...]


def effective_word(
    codeword: Sequence[int],
    overrides: Mapping[str, Optional[str]],
    channels: ChannelSet,
) -> Word:
    """Apply a sparse ``{channel_name: label_or_None}`` diff to ``codeword``.

    Channels absent from ``overrides`` keep the assigned symbol; a ``None``
    value marks that position as uninformative rather than substituting a
    colour. Raises ``ValueError`` (readable, not a ``KeyError``) for an
    override naming a channel the scheme doesn't have, or a label the named
    channel doesn't carry.
    """
    if len(codeword) != channels.n:
        raise ValueError(
            f"codeword length {len(codeword)} != number of channels {channels.n}"
        )
    unknown = set(overrides) - set(channels.names)
    if unknown:
        raise ValueError(
            f"overrides reference unknown channels: {sorted(unknown)}; "
            f"known: {channels.names}"
        )
    word: List[Optional[int]] = []
    for channel, symbol in zip(channels, codeword):
        if channel.name in overrides:
            label = overrides[channel.name]
            word.append(None if label is None else channel.label_to_index(label))
        else:
            word.append(symbol)
    return tuple(word)


def overlap_distance(a: Word, b: Word) -> int:
    """Hamming distance between two words, counted only where both sides are
    non-``None``.

    Conservative on purpose: an unknown position can't be shown to differ, so
    it provides no separation. Two all-``None`` words are distance 0, not "no
    comparison possible" -- callers that need to special-case "nothing is
    known at all" should check that themselves (:func:`suggest_free_channels`
    does, for the empty-``others`` case).
    """
    if len(a) != len(b):
        raise ValueError(f"word lengths differ: {len(a)} != {len(b)}")
    return sum(1 for x, y in zip(a, b) if x is not None and y is not None and x != y)


def pairwise_distances(
    words: Mapping[object, Word],
) -> List[Tuple[object, object, int]]:
    """Every unordered pair of ``words`` with its :func:`overlap_distance`,
    ascending by distance.

    Ties keep the pairs in the order they're generated -- ``(i, j)`` with
    ``i`` before ``j`` in ``words`` iteration order -- via a stable sort, so
    the result is deterministic for a given input mapping.
    """
    ids = list(words)
    pairs = [
        (ids[i], ids[j], overlap_distance(words[ids[i]], words[ids[j]]))
        for i in range(len(ids))
        for j in range(i + 1, len(ids))
    ]
    pairs.sort(key=lambda item: item[2])
    return pairs


class Suggestion(NamedTuple):
    """One candidate assignment for the admin's free (self-chosen) channels."""

    assignment: Dict[str, str]  # free channel name -> chosen label
    word: Word  # the resulting full effective word (fixed + free + None elsewhere)
    min_distance: int  # min overlap_distance to `others`; see suggest_free_channels
    closest: List[object]  # the `others` ids achieving that minimum


def suggest_free_channels(
    fixed: Mapping[str, Optional[str]],
    free: Sequence[str],
    others: Mapping[object, Word],
    channels: ChannelSet,
    avoid: Iterable[Word] = (),
    limit: int = 5,
) -> List[Suggestion]:
    """Suggest colours for the channels the admin still controls.

    ``fixed`` are the channels already pinned by what the guest is physically
    wearing (a label, or ``None`` if that garment is out-of-palette); ``free``
    are the channels the admin can still choose for them (typically
    ``["armbands"]``, handed out at the gate). Channels in neither are treated
    as ``None`` -- unknown, not zero.

    Every combination of labels across ``free`` is tried (only the
    addressable symbols per channel, i.e. ``channels.max_addressable_symbol``;
    at most ``q`` per free channel, so brute force is cheap). Candidates are
    ranked, best first, by:

    1. maximise the minimum :func:`overlap_distance` to ``others`` (the other
       in-play players -- don't create a new confusable pair);
    2. tie-break: maximise the minimum distance to ``avoid`` (codewords of
       still-unassigned usable slots -- prefer not to burn a future slot by
       squatting on its outfit);
    3. tie-break: maximise the distance from the all-zero word (the all-black
       "passer-by" outfit, plan §11.1 -- prefer standing out from it too);
    4. final tie-break: ascending symbol order, so the result is deterministic.

    When ``others`` is empty there is no real constraint from criterion 1;
    ``min_distance`` is then reported as ``channels.n`` (the maximum any
    overlap distance over this many channels could be), and ``closest`` is
    ``[]``. The same sentinel is used internally for an empty ``avoid``.
    """
    overlap = set(fixed) & set(free)
    if overlap:
        raise ValueError(f"channels listed in both fixed and free: {sorted(overlap)}")
    unknown = (set(fixed) | set(free)) - set(channels.names)
    if unknown:
        raise ValueError(
            f"unknown channels: {sorted(unknown)}; known: {channels.names}"
        )

    n = channels.n
    sentinel = n  # documented above: "no real constraint" for empty others/avoid

    base: List[Optional[int]] = []
    free_positions: List[int] = []
    for i, channel in enumerate(channels):
        if channel.name in fixed:
            label = fixed[channel.name]
            base.append(None if label is None else channel.label_to_index(label))
        elif channel.name in free:
            free_positions.append(i)
            base.append(None)  # filled in per-combination below
        else:
            base.append(None)

    free_channels = [(i, channels[i]) for i in free_positions]
    symbol_ranges = [
        range(channels.max_addressable_symbol(i)) for i, _ in free_channels
    ]
    all_zero: Word = tuple(0 for _ in range(n))
    avoid = list(avoid)
    others_items = list(others.items())

    scored = []
    for combo in product(*symbol_ranges):
        word = list(base)
        assignment: Dict[str, str] = {}
        for (i, channel), symbol in zip(free_channels, combo):
            word[i] = symbol
            assignment[channel.name] = channel.index_to_label(symbol)
        word = tuple(word)

        if others_items:
            distances = [(pid, overlap_distance(word, ow)) for pid, ow in others_items]
            min_to_others = min(d for _, d in distances)
            closest = [pid for pid, d in distances if d == min_to_others]
        else:
            min_to_others = sentinel
            closest = []

        min_to_avoid = (
            min(overlap_distance(word, aw) for aw in avoid) if avoid else sentinel
        )
        dist_from_zero = overlap_distance(word, all_zero)

        scored.append(
            (
                min_to_others,
                min_to_avoid,
                dist_from_zero,
                combo,
                assignment,
                word,
                closest,
            )
        )

    # Descending on the three ranking criteria, ascending (symbol order) as
    # the final deterministic tie-break.
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))

    return [
        Suggestion(
            assignment=assignment,
            word=word,
            min_distance=min_to_others,
            closest=closest,
        )
        for min_to_others, _min_to_avoid, _dist_from_zero, _combo, assignment, word, closest in scored[
            :limit
        ]
    ]


def nearest_slots(
    word: Word,
    scheme: IdentityScheme,
    taken: Iterable[int] = (),
) -> List[int]:
    """Usable slots not in ``taken``, ascending by overrides needed for
    ``word`` to become that slot's outfit.

    "Overrides needed" counts the positions where ``word`` has a concrete
    (non-``None``) symbol that disagrees with the slot's codeword; ``None``
    positions cost the same (one override, to record the erasure) against
    every slot, so they don't discriminate and are left out of the ranking.
    Ties break on ascending slot number, for a deterministic result.
    """
    taken_set = set(taken)
    candidates = [slot for slot in scheme.usable_slots() if slot not in taken_set]

    def overrides_needed(slot: int) -> int:
        codeword = scheme.codeword_of_slot(slot)
        return sum(1 for w, c in zip(word, codeword) if w is not None and w != c)

    return sorted(candidates, key=lambda slot: (overrides_needed(slot), slot))


def overrides_for(
    word: Word,
    slot: int,
    scheme: IdentityScheme,
) -> Dict[str, Optional[str]]:
    """The sparse diff to store so that ``effective_word`` reconstructs
    ``word`` from ``slot``'s codeword.

    Positions where ``word`` agrees with the slot's codeword are omitted
    (nothing to override); round-trips through :func:`effective_word`:
    ``effective_word(scheme.codeword_of_slot(slot),
    overrides_for(word, slot, scheme), scheme.channels) == word``.
    """
    codeword = scheme.codeword_of_slot(slot)
    if len(word) != len(codeword):
        raise ValueError(f"word length {len(word)} != codeword length {len(codeword)}")
    overrides: Dict[str, Optional[str]] = {}
    for channel, w, c in zip(scheme.channels, word, codeword):
        if w is None:
            overrides[channel.name] = None
        elif w != c:
            overrides[channel.name] = channel.index_to_label(w)
    return overrides
