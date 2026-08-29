"""S4's deliberate misread: one armband photographed as the wrong colour.

The point of the scene is Reed-Solomon correcting a single misread channel,
so the wrong colour cannot be picked at random. It has to satisfy two things
against the *real* decoder, or the photograph tests nothing:

* the corrupted reading must still decode to the intended player, otherwise
  the scene is testing a failure rather than a correction; and
* it must not collide with anybody else's effective word, otherwise the
  "correction" is really an ambiguity that happened to land right.

Both are checked here, and a scenario that cannot satisfy them says so.
"""

from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from backend.identity.config import default_scheme
from backend.identity.overrides import overlap_distance


def _word_of(appearance: Dict[str, str], scheme) -> Tuple[int, ...]:
    return tuple(
        scheme.channels.by_name(name).label_to_index(appearance[name])
        for name in scheme.channels.names
    )


def choose_misread(
    world: dict, target_slug: str, channel: str = "armbands"
) -> Optional[dict]:
    """A wrong colour for ``channel`` that still decodes to ``target_slug``.

    Returns ``None`` when no such colour exists, which is a legitimate answer
    -- and one the caller must not paper over, since a misread that decodes to
    somebody else would quietly invert what the scene claims to prove.
    """
    scheme = default_scheme()
    players = world["identity"]["players"]
    target = players[target_slug]
    true_word = _word_of(target["appearance"], scheme)

    others: List[Tuple[str, Tuple[int, ...]]] = [
        (slug, _word_of(entry["appearance"], scheme))
        for slug, entry in players.items()
        if slug != target_slug
    ]

    true_colour = target["appearance"][channel]
    channel_obj = scheme.channels.by_name(channel)

    candidates = []
    for colour in channel_obj.labels:
        if colour == true_colour:
            continue
        corrupted = list(true_word)
        corrupted[scheme.channels.names.index(channel)] = channel_obj.label_to_index(
            colour
        )
        corrupted = tuple(corrupted)

        # Distance to the intended player, and to the nearest other player.
        to_target = overlap_distance(corrupted, true_word)
        nearest_other = min(
            (overlap_distance(corrupted, word), slug) for slug, word in others
        )
        # Strictly nearer the intended player than anybody else, so the
        # correction is unambiguous rather than lucky.
        if to_target < nearest_other[0]:
            candidates.append(
                {
                    "channel": channel,
                    "true_colour": true_colour,
                    "photographed_as": colour,
                    "distance_to_target": to_target,
                    "distance_to_nearest_other": nearest_other[0],
                    "nearest_other": nearest_other[1],
                }
            )

    if not candidates:
        return None
    # Deterministic: the widest margin, then the colour's own order.
    candidates.sort(
        key=lambda c: (
            -(c["distance_to_nearest_other"] - c["distance_to_target"]),
            c["photographed_as"],
        )
    )
    return candidates[0]
