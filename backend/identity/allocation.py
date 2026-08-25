"""Allocating blocks of slots to teams so that one channel reads as the team.

The decoder does not care which slot a player holds -- any two correctly-read
garments identify them (plan §4). But *people* care: at 30m, in the dark, a
player wants to know "friend or foe" without mentally decoding four colours
against a printed key. So the pre-allocation deliberately spends one channel
(:data:`~backend.identity.config.TEAM_CHANNEL`, the hat) on that: every member
of a team is handed a slot whose hat is the same colour, and no two teams share
a hat colour.

That costs nothing in error-correction terms -- the slots handed out are still
distinct codewords of the same scheme -- it merely constrains *which* of the
usable slots each team draws from.

The constraint has a hard ceiling: a hat colour only covers as many slots as
there are codewords carrying it (five each in the default scheme, four for
black). Past that a team needs a second colour, and
:func:`allocate_team_slots` gives it one *whole* extra colour rather than
sharing a part-used one, so a hat colour still names exactly one team. Slots
are emitted primary-colour-first, so a team that never fills its block never
reaches the second colour at all.

This module is pure: slots, labels and schemes only, no database (the
package-wide rule -- see :mod:`backend.identity.overrides`).
"""

from typing import Dict
from typing import Iterable
from typing import List
from typing import Sequence
from typing import Tuple


def group_slots_by_channel(scheme, channel_name: str) -> List[Tuple[str, List[int]]]:
    """Usable slots bucketed by the label they wear in ``channel_name``.

    Returned largest bucket first (ties broken by the channel's label order),
    each bucket's slots ascending -- so allocation hands out the roomiest
    colours first and is deterministic across calls.
    """
    channel = scheme.channels.by_name(channel_name)
    index = scheme.channels.names.index(channel_name)

    buckets: Dict[str, List[int]] = {}
    for slot in scheme.usable_slots():
        label = channel.index_to_label(scheme.codeword_of_slot(slot)[index])
        buckets.setdefault(label, []).append(slot)

    return sorted(
        buckets.items(), key=lambda kv: (-len(kv[1]), channel.label_to_index(kv[0]))
    )


class TeamAllocation:
    """One team's slots, plus the ``channel_name`` labels they actually wear.

    ``labels`` is in the order the slots use them, so ``labels[0]`` is the
    team's primary colour -- the one to buy hats in -- and a second entry means
    the block outgrew one colour.
    """

    def __init__(self, slots: Sequence[int], labels: Sequence[str]):
        self.slots = list(slots)
        self.labels = list(labels)

    def __repr__(self) -> str:
        return f"TeamAllocation(slots={self.slots!r}, labels={self.labels!r})"


def allocate_team_slots(
    scheme, n_teams: int, slots_per_team: int, channel_name: str
) -> List[TeamAllocation]:
    """``n_teams`` blocks of ``slots_per_team`` slots, grouped by team colour.

    Teams take whole colour buckets in turn, biggest bucket first, so with a
    small enough ``slots_per_team`` every team gets exactly one colour and the
    hat alone tells you who is on whose side. A team needing more slots than
    one bucket holds picks up further buckets in later rounds -- the minimum
    number of colours, with its slots ordered so the first bucketful is all one
    colour and only the overflow spills into the next.

    Colours run out before slots do (a part-used bucket is never shared), so
    when the buckets are exhausted the remaining need is filled from whatever
    usable slots are still unallocated, in ascending order. Those trailing
    slots break the colour rule -- they are last in each team's list, and the
    ``labels`` of the allocation say which colours a team really covers.

    Raises ``ValueError`` if the request exceeds the scheme's usable slots
    outright.
    """
    if n_teams < 1:
        raise ValueError(f"need at least one team; got {n_teams}")
    if slots_per_team < 1:
        raise ValueError(f"need at least one slot per team; got {slots_per_team}")

    usable = scheme.usable_slots()
    needed = n_teams * slots_per_team
    if needed > len(usable):
        raise ValueError(
            f"{n_teams} teams x {slots_per_team} slots needs {needed} outfits, "
            f"but the scheme only has {len(usable)}"
        )

    buckets = group_slots_by_channel(scheme, channel_name)
    label_of = {slot: label for label, slots in buckets for slot in slots}
    team_slots: List[List[int]] = [[] for _ in range(n_teams)]

    # Round-robin whole buckets: everyone gets their primary colour before
    # anyone gets a second one, so the teams that fit in one colour keep one.
    next_bucket = 0
    while next_bucket < len(buckets):
        hungry = [slots for slots in team_slots if len(slots) < slots_per_team]
        if not hungry:
            break
        for slots in hungry:
            if next_bucket >= len(buckets):
                break
            _, bucket = buckets[next_bucket]
            next_bucket += 1
            slots.extend(bucket[: slots_per_team - len(slots)])

    # Buckets exhausted with teams still short: fall back to the leftovers,
    # which necessarily reuse colours already claimed by another team.
    taken = {slot for slots in team_slots for slot in slots}
    leftovers = [slot for slot in usable if slot not in taken]
    for slots in team_slots:
        while len(slots) < slots_per_team:
            slots.append(leftovers.pop(0))

    return [
        TeamAllocation(slots=slots, labels=_ordered_unique(label_of[s] for s in slots))
        for slots in team_slots
    ]


def colour_capacity(scheme, channel_name: str) -> Dict[str, int]:
    """``{label: number of usable slots wearing it}`` -- 5 per colour in the
    default scheme, 4 for black (slot 0 is excluded).
    """
    return {
        label: len(slots)
        for label, slots in group_slots_by_channel(scheme, channel_name)
    }


def assign_team_colours(
    scheme, channel_name: str, existing: Dict[object, object]
) -> Dict[object, str]:
    """Colour each team in ``existing`` (team key -> pinned colour, or ``None``).

    Pinned teams keep their colour; unpinned teams take the remaining colour
    buckets in :func:`group_slots_by_channel` order (roomiest first), assigned
    in ``existing``'s own insertion order so the result is deterministic.

    Honouring pinned colours -- rather than recomputing every team's colour
    from scratch each time -- is what makes adding a team later never re-colour
    an existing one. That is the entire reason a team's colour is *stored*
    rather than *derived*: derived state would recompute, and reshuffle, on
    every call.

    Raises ``ValueError`` if there are more teams than the channel has colours.
    """
    buckets = group_slots_by_channel(scheme, channel_name)
    all_labels = [label for label, _ in buckets]

    if len(existing) > len(all_labels):
        raise ValueError(
            f"{len(existing)} teams need a colour each, "
            f"but {channel_name!r} only has {len(all_labels)}"
        )

    taken = {colour for colour in existing.values() if colour is not None}
    available = iter(label for label in all_labels if label not in taken)

    result: Dict[object, str] = {}
    for team, colour in existing.items():
        result[team] = colour if colour is not None else next(available)
    return result


def _ordered_unique(labels: Iterable[str]) -> List[str]:
    """``labels`` deduplicated, keeping first-seen order."""
    out: List[str] = []
    for label in labels:
        if label not in out:
            out.append(label)
    return out
