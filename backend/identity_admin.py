"""The impure bridge between ``User`` rows and the pure ``backend.identity``
package.

``backend/identity/`` only ever sees codewords, labels and channel sets --
never a database, a request, or a ``User`` row (package-wide rule, see
``backend/identity/overrides.py``). This module is where that pure world
meets the game: it reads/writes ``User.identity_slot`` and
``User.identity_overrides`` (via ``AdminInterface`` / ``UserInterface``),
translates the pure helpers' ``ValueError``s into admin-readable messages, and
assembles the report/suggestion payloads the admin identity page
(``react-ui/src/AdminIdentity.js``) is coded against.

A player's **effective word** is what they actually, physically wear: their
slot's canonical codeword with any per-channel overrides applied
(:func:`~backend.identity.overrides.effective_word`). Players with no slot
have no effective word and are excluded from every pairwise-distance
computation here -- an all-``None`` word would sit at distance 0 from
everyone and flood the report with false collision warnings.
"""

import json
import logging
from typing import Dict
from typing import List
from typing import Optional
from uuid import UUID

import pydantic

from .admin_interface import AdminInterface
from .identity.config import default_scheme
from .identity.config import hex_for
from .identity.overrides import Word
from .identity.overrides import effective_word
from .identity.overrides import nearest_slots
from .identity.overrides import overlap_distance
from .identity.overrides import overrides_for
from .identity.overrides import pairwise_distances
from .identity.overrides import suggest_free_channels
from .identity.scheme import IdentityScheme
from .model import UserModel
from .user_interface import UserInterface

logger = logging.getLogger(__name__)

# Distance -> the report's traffic-light level. Only pairs strictly below the
# scheme's nominal minimum distance are reported at all (see build_report).
_LEVEL_BY_DISTANCE = {0: "critical", 1: "danger", 2: "warning"}


class IdentityAdminError(ValueError):
    """A bad identity-admin request. Translated to an HTTP 400 by the API
    layer (see ``_identity_admin_errors`` in ``backend/main.py``), same
    pattern as ``identity_demo.DemoError``.
    """


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class IdentitySetRequest(pydantic.BaseModel):
    user_id: UUID
    slot: Optional[int] = None
    overrides: Optional[Dict[str, Optional[str]]] = None
    force: bool = False


class IdentitySuggestRequest(pydantic.BaseModel):
    game_id: UUID
    user_id: Optional[UUID] = None
    fixed: Dict[str, Optional[str]] = {}
    free: List[str] = []


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _parse_overrides(raw: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    """The stored JSON text back into a sparse overrides dict, or None."""
    if raw is None:
        return None
    return json.loads(raw)


def _word_to_appearance(word: Word, scheme: IdentityScheme) -> Dict[str, Optional[str]]:
    """``{channel_name: label_or_None}`` for an effective word."""
    return {
        channel.name: (None if symbol is None else channel.index_to_label(symbol))
        for channel, symbol in zip(scheme.channels, word)
    }


def _effective_words(
    users: List[UserModel], scheme: IdentityScheme
) -> Dict[UUID, Word]:
    """Effective words for the slot-holding subset of ``users``.

    Players with no slot are omitted entirely -- see the module docstring for
    why an all-None word can't safely stand in for "no identity yet".
    """
    words: Dict[UUID, Word] = {}
    for user in users:
        if user.identity_slot is None:
            continue
        codeword = scheme.codeword_of_slot(user.identity_slot)
        overrides = _parse_overrides(user.identity_overrides) or {}
        words[user.id] = effective_word(codeword, overrides, scheme.channels)
    return words


def _player_row(user: UserModel, scheme: IdentityScheme) -> dict:
    """The report/response shape for one player."""
    overrides = _parse_overrides(user.identity_overrides)

    canonical_appearance = None
    effective_appearance = None
    if user.identity_slot is not None:
        codeword = scheme.codeword_of_slot(user.identity_slot)
        canonical_appearance = scheme.channels.codeword_to_appearance(codeword)
        word = effective_word(codeword, overrides or {}, scheme.channels)
        effective_appearance = _word_to_appearance(word, scheme)

    return {
        "user_id": user.id,
        "name": user.name,
        "team_name": user.team_name,
        "slot": user.identity_slot,
        "overrides": overrides,
        "canonical_appearance": canonical_appearance,
        "effective_appearance": effective_appearance,
        "overridden": bool(overrides),
    }


def _channels_payload(scheme: IdentityScheme) -> List[dict]:
    out = []
    for i, channel in enumerate(scheme.channels):
        labels = channel.labels[: scheme.channels.max_addressable_symbol(i)]
        out.append(
            {
                "name": channel.name,
                "labels": labels,
                "hex": {label: hex_for(channel.name, label) for label in labels},
            }
        )
    return out


# ---------------------------------------------------------------------------
# GET /admin_identity_report
# ---------------------------------------------------------------------------


def build_report(game_id: UUID) -> dict:
    scheme = default_scheme()
    users = AdminInterface().get_users_for_game(game_id)  # 404s if game missing

    players = [_player_row(u, scheme) for u in users]

    words = _effective_words(users, scheme)
    names_by_id = {u.id: u.name for u in users}
    nominal_min_distance = scheme.code.min_distance()

    dist_pairs = pairwise_distances(words)  # ascending by distance
    pairs = [
        {
            "user_id_a": a,
            "name_a": names_by_id[a],
            "user_id_b": b,
            "name_b": names_by_id[b],
            "distance": distance,
            "level": _LEVEL_BY_DISTANCE[distance],
        }
        for a, b, distance in dist_pairs
        if distance < nominal_min_distance
    ]

    effective_min_distance = dist_pairs[0][2] if len(words) >= 2 else None

    taken_slots = {u.identity_slot for u in users if u.identity_slot is not None}
    free_slots = sorted(s for s in scheme.usable_slots() if s not in taken_slots)

    return {
        "channels": _channels_payload(scheme),
        "players": players,
        "pairs": pairs,
        "effective_min_distance": effective_min_distance,
        "nominal_min_distance": nominal_min_distance,
        "free_slots": free_slots,
    }


# ---------------------------------------------------------------------------
# POST /admin_identity_set
# ---------------------------------------------------------------------------


def set_identity(request: IdentitySetRequest) -> dict:
    scheme = default_scheme()
    admin = AdminInterface()
    user = admin.get_user_model(request.user_id)  # 404s if user missing

    slot = request.slot
    overrides = request.overrides

    if slot is None and overrides is not None:
        raise IdentityAdminError("assign a slot first")

    if slot is not None and slot not in scheme.usable_slots():
        raise IdentityAdminError(f"slot {slot} is not a usable slot")

    game_users = admin.get_users_for_game(user.game_id) if user.game_id else []
    others = [u for u in game_users if u.id != user.id]
    names_by_id = {u.id: u.name for u in game_users}

    if slot is not None:
        holder = next((u for u in others if u.identity_slot == slot), None)
        if holder is not None:
            raise IdentityAdminError(f"slot {slot} is already used by {holder.name}")

        codeword = scheme.codeword_of_slot(slot)
        try:
            word = effective_word(codeword, overrides or {}, scheme.channels)
        except ValueError as e:
            raise IdentityAdminError(str(e))

        if not request.force:
            other_words = _effective_words(others, scheme)
            for other_id, other_word in other_words.items():
                if overlap_distance(word, other_word) == 0:
                    raise IdentityAdminError(
                        f"identical outfit to {names_by_id[other_id]}"
                    )

    overrides_json = json.dumps(overrides) if overrides is not None else None

    with UserInterface(request.user_id) as ui:
        ui.set_identity(slot, overrides_json)

    updated = admin.get_user_model(request.user_id)
    return _player_row(updated, scheme)


# ---------------------------------------------------------------------------
# POST /admin_identity_suggest
# ---------------------------------------------------------------------------


def suggest_identity(request: IdentitySuggestRequest) -> dict:
    scheme = default_scheme()
    users = AdminInterface().get_users_for_game(request.game_id)  # 404s if missing

    others_users = [u for u in users if u.id != request.user_id]
    others = _effective_words(others_users, scheme)
    names_by_id = {u.id: u.name for u in users}

    # Slots held by other in-game players -- the target's own current slot
    # (if any) is deliberately not in here, so it stays a candidate for
    # nearest_slots below.
    taken_slots = {
        u.identity_slot
        for u in users
        if u.identity_slot is not None and u.id != request.user_id
    }
    avoid = [
        scheme.codeword_of_slot(slot)
        for slot in scheme.usable_slots()
        if slot not in taken_slots
    ]

    try:
        suggestions = suggest_free_channels(
            request.fixed, request.free, others, scheme.channels, avoid=avoid
        )
    except ValueError as e:
        raise IdentityAdminError(str(e))

    out = []
    for suggestion in suggestions:
        candidate_slots = nearest_slots(suggestion.word, scheme, taken=taken_slots)
        if not candidate_slots:
            # No free slot left for anyone -- drop this candidate rather than
            # erroring; the caller sees an (possibly empty) suggestions list.
            continue
        slot = candidate_slots[0]
        out.append(
            {
                "assignment": suggestion.assignment,
                "min_distance": suggestion.min_distance,
                "closest_players": [
                    {
                        "user_id": pid,
                        "name": names_by_id.get(pid),
                        "distance": suggestion.min_distance,
                    }
                    for pid in suggestion.closest
                ],
                "slot": slot,
                "overrides": overrides_for(suggestion.word, slot, scheme),
                "effective_appearance": _word_to_appearance(suggestion.word, scheme),
            }
        )

    return {"suggestions": out}
