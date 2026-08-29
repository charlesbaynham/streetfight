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
from itertools import product
from threading import RLock
from typing import Dict
from typing import List
from typing import NamedTuple
from typing import Optional
from uuid import UUID

import pydantic

from . import ticker_message_dispatcher as tk
from .admin_interface import AdminInterface
from .identity.allocation import assign_team_colours
from .identity.allocation import colour_capacity
from .identity.config import PROVIDED_CHANNEL
from .identity.config import TEAM_CHANNEL
from .identity.config import buckets_for_channel
from .identity.config import commonness_for
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
from .join_codes import JoinCodeModel
from .join_codes import make_team_join_url
from .model import TeamModel
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


class OutfitUnavailableError(IdentityAdminError):
    """A ``pick_outfit`` claim failed re-validation against freshly read
    state: the appearance is no longer wearable from the declared wardrobe,
    no longer clears the distance gate, or its slot was just taken. Raised
    only from inside ``pick_outfit_lock`` - see ``_revalidate_appearance``.

    Deliberately a single, generic outcome covering every re-validation
    failure (never a substituted outfit) so the frontend can say "someone
    just took that, please choose again" without needing to know why. The
    API layer (``_identity_admin_errors``) maps this to HTTP 409, distinct
    from the plain 400 a malformed request gets, so it stays distinguishable
    end to end.
    """


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class IdentitySetRequest(pydantic.BaseModel):
    user_id: UUID
    slot: Optional[int] = None
    overrides: Optional[Dict[str, Optional[str]]] = None
    force: bool = False


class IdentityClearRequest(pydantic.BaseModel):
    user_id: UUID


class IdentitySuggestRequest(pydantic.BaseModel):
    game_id: UUID
    user_id: Optional[UUID] = None
    fixed: Dict[str, Optional[str]] = {}
    free: List[str] = []


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _parse_json_column(raw: Optional[str]) -> Optional[Dict]:
    """A stored JSON-text column (identity_overrides, identity_wardrobe) back
    into its dict, or None."""
    if raw is None:
        return None
    return json.loads(raw)


def _word_to_appearance(word: Word, scheme: IdentityScheme) -> Dict[str, Optional[str]]:
    """``{channel_name: label_or_None}`` for an effective word."""
    return {
        channel.name: (None if symbol is None else channel.index_to_label(symbol))
        for channel, symbol in zip(scheme.channels, word)
    }


def effective_words(users: List[UserModel], scheme: IdentityScheme) -> Dict[UUID, Word]:
    """Effective words for the slot-holding subset of ``users``.

    Players with no slot are omitted entirely -- see the module docstring for
    why an all-None word can't safely stand in for "no identity yet".
    """
    words: Dict[UUID, Word] = {}
    for user in users:
        if user.identity_slot is None:
            continue
        codeword = scheme.codeword_of_slot(user.identity_slot)
        overrides = _parse_json_column(user.identity_overrides) or {}
        words[user.id] = effective_word(codeword, overrides, scheme.channels)
    return words


def provided_channels(scheme: IdentityScheme) -> List[str]:
    """The garments we hand out at the door rather than leave to a wardrobe:
    the team hat and the armband. Both have been bought (roadmap #9), and both
    are put on the player by the admin doing the kit check, which is why
    :func:`expected_outfit` marks them -- that admin is standing at the box
    and needs to know which colours to take out of it.

    The complement of :func:`_wardrobe_channels`, and defined in the same terms
    so the two can never disagree about which channels a player supplies.
    """
    return [
        name
        for name in scheme.channels.names
        if name in (TEAM_CHANNEL, PROVIDED_CHANNEL)
    ]


def expected_outfit(
    slot: Optional[int], overrides_raw: Optional[str], scheme: IdentityScheme
) -> Optional[Dict[str, dict]]:
    """What a player is supposed to turn up in, per channel.

    Shaped like a vision review's ``channels`` -- ``{name: {"colour", "hex"}}``
    -- so the kit-check page can render the expectation and the reading with
    one component and put them side by side, which is the only way to see
    *which* garment is wrong rather than merely that something is.

    The **effective** word, not the canonical codeword: an override is what the
    player actually agreed to wear, and it is what the decoder scores the
    photograph against, so it is what "expected" has to mean here. ``None`` for
    a player who has not picked an outfit -- there is nothing to expect of
    them yet, and nothing to check a photo against either.
    """
    if slot is None:
        return None

    provided = set(provided_channels(scheme))
    overrides = _parse_json_column(overrides_raw) or {}
    word = effective_word(scheme.codeword_of_slot(slot), overrides, scheme.channels)
    return {
        name: {
            "colour": colour,
            "hex": None if colour is None else hex_for(name, colour),
            "provided": name in provided,
        }
        for name, colour in _word_to_appearance(word, scheme).items()
    }


def _player_row(user: UserModel, scheme: IdentityScheme) -> dict:
    """The report/response shape for one player."""
    overrides = _parse_json_column(user.identity_overrides)
    wardrobe = _parse_json_column(user.identity_wardrobe)

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
        "wardrobe": wardrobe,
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
                # Per channel, because the channels do not share a vocabulary:
                # "black" excludes charcoal on a top and includes it on the legs.
                "notes": buckets_for_channel(channel.name),
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

    words = effective_words(users, scheme)
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


def _validate_slot_assignment(
    scheme: IdentityScheme,
    user_id: UUID,
    slot: int,
    overrides: Optional[Dict[str, Optional[str]]],
    game_users: List[UserModel],
    force: bool = False,
):
    """Reject an unusable/held slot, an unwearable override, or (unless
    ``force``) an effective word at zero overlap-distance from another
    player's. Raises :class:`IdentityAdminError`; returns nothing.
    """
    others = [u for u in game_users if u.id != user_id]
    names_by_id = {u.id: u.name for u in game_users}

    if slot not in scheme.usable_slots():
        raise IdentityAdminError(f"slot {slot} is not a usable slot")

    holder = next((u for u in others if u.identity_slot == slot), None)
    if holder is not None:
        raise IdentityAdminError(f"slot {slot} is already used by {holder.name}")

    codeword = scheme.codeword_of_slot(slot)
    try:
        word = effective_word(codeword, overrides or {}, scheme.channels)
    except ValueError as e:
        raise IdentityAdminError(str(e))

    if not force:
        other_words = effective_words(others, scheme)
        for other_id, other_word in other_words.items():
            if overlap_distance(word, other_word) == 0:
                raise IdentityAdminError(f"identical outfit to {names_by_id[other_id]}")


def set_identity(request: IdentitySetRequest) -> dict:
    scheme = default_scheme()
    admin = AdminInterface()
    user = admin.get_user_model(request.user_id)  # 404s if user missing

    slot = request.slot
    overrides = request.overrides

    if slot is None and overrides is not None:
        raise IdentityAdminError("assign a slot first")

    game_users = admin.get_users_for_game(user.game_id) if user.game_id else []

    if slot is not None:
        _validate_slot_assignment(
            scheme, user.id, slot, overrides, game_users, force=request.force
        )

    overrides_json = json.dumps(overrides) if overrides is not None else None

    with UserInterface(request.user_id) as ui:
        ui.set_identity(slot, overrides_json)

    updated = admin.get_user_model(request.user_id)
    return _player_row(updated, scheme)


# ---------------------------------------------------------------------------
# POST /admin_clear_identity
# ---------------------------------------------------------------------------


def clear_identity(user_id: UUID) -> dict:
    """Null a player's slot, overrides and wardrobe, freeing that outfit for
    everyone else (plan C5) -- the escape hatch for a final pick: a player
    who wants to choose again has to ask an admin, and this is also the tool
    an admin reaches for at the door on game night when someone turns up in
    the wrong clothes.

    The player stays in their team -- clearing membership entirely is
    ``admin_delete_user``'s job, not this.
    """
    scheme = default_scheme()
    admin = AdminInterface()
    admin.get_user_model(user_id)  # 404s if user missing

    with UserInterface(user_id) as ui:
        ui.clear_identity()

    updated = admin.get_user_model(user_id)
    return _player_row(updated, scheme)


# ---------------------------------------------------------------------------
# POST /join_game (player-facing, via a signed join code)
# ---------------------------------------------------------------------------


def claim_join_slot(user_id: UUID, code: JoinCodeModel) -> dict:
    """Join the code's team and claim its identity slot for ``user_id``.

    The signature must already have been checked by the caller (the API
    layer 403s on a bad one). Validation reuses the same rules as an admin
    slot assignment, with no overrides and no force - so a slot rendered
    indistinguishable by another player's override is rejected too. A
    re-scan of a code the scanner already holds is an idempotent no-op; a
    scan of a *different* code while already in a team is a move, allowed
    whenever the same validation passes (the old slot frees itself).
    """
    scheme = default_scheme()
    admin = AdminInterface()

    game_users = admin.get_users_for_game(code.game_id)  # 404s if game missing
    team = admin.get_team_model(code.team_id)  # 404s if team missing
    if team.game_id != code.game_id:
        raise IdentityAdminError("join code's team does not belong to its game")

    scanner = next((u for u in game_users if u.id == user_id), None)
    if (
        scanner is not None
        and scanner.team_id == code.team_id
        and scanner.identity_slot == code.slot
    ):
        # Re-scan of the scanner's own code
        return _player_row(scanner, scheme)

    _validate_slot_assignment(
        scheme, user_id, code.slot, overrides=None, game_users=game_users, force=False
    )

    # The atomic write: team + slot in one transaction, with the slot-holder
    # check re-run inside it (409 on losing the race). Then the same ticker
    # announcement AdminInterface.add_user_to_team makes.
    with UserInterface(user_id) as ui:
        ui.join_team_and_claim_slot(code.team_id, code.slot)

        u = ui.get_user()

        user_name = u.name
        team_name = u.team.name
        game_id = u.team.game_id

        tk.send_ticker_message(
            tk.TickerMessageType.USER_JOINED_TEAM,
            {"user": user_name, "team": team_name},
            game_id=game_id,
            session=ui.get_session(),
        )

    updated = admin.get_user_model(user_id)
    return _player_row(updated, scheme)


# ---------------------------------------------------------------------------
# Player-facing outfit picking (join_options / outfit_options / pick_outfit)
#
# A *team* join code (JoinCodeModel.slot is None, see build_join_codes/C3)
# lets the scanner choose their own outfit rather than claiming a fixed slot.
# Authorised the same way /join_game is - possession of a validly-signed
# code, checked by the caller (backend/main.py's _decoded_join_code) before
# any of these run.
# ---------------------------------------------------------------------------


class Option(NamedTuple):
    """One ranked candidate outfit - see :func:`outfit_options`."""

    appearance: Dict[str, str]
    slot: int
    overrides: Dict[str, Optional[str]]
    overrides_needed: int
    rarity: float
    min_distance: int
    is_canonical: bool


def _team_for_pick(admin: AdminInterface, code: JoinCodeModel) -> TeamModel:
    """Shared preamble for the three outfit-picking entry points: reject a
    per-slot code (that's the older claim-a-fixed-outfit flow, not this one)
    and a code whose team doesn't belong to its game.
    """
    if code.slot is not None:
        raise IdentityAdminError(
            "this join code claims a specific outfit slot - scan a team code "
            "to pick your own instead"
        )
    team = admin.get_team_model(code.team_id)  # 404s if missing
    if team.game_id != code.game_id:
        raise IdentityAdminError("join code's team does not belong to its game")
    return team


def _wardrobe_channels(scheme: IdentityScheme) -> List[str]:
    """The channels a player's own clothes must answer: every channel except
    the team-pinned hat and the armband we hand out (plan C4)."""
    provided = set(provided_channels(scheme))
    return [name for name in scheme.channels.names if name not in provided]


def _validate_wardrobe(scheme: IdentityScheme, wardrobe: Dict[str, List[str]]) -> None:
    """A player's wardrobe can only name real channels and real colours on
    them. The palette a player ticks from is server-rendered, but nothing
    stops a stale or hand-crafted client sending something else.
    """
    unknown_channels = set(wardrobe) - set(_wardrobe_channels(scheme))
    if unknown_channels:
        raise IdentityAdminError(
            f"wardrobe names channels this scheme doesn't have: {sorted(unknown_channels)}"
        )
    for channel_name, labels in wardrobe.items():
        channel = scheme.channels.by_name(channel_name)
        bad = [label for label in labels if not channel.has_label(label)]
        if bad:
            raise IdentityAdminError(f"channel {channel_name!r} has no colour(s) {bad}")


def outfit_options(
    scheme: IdentityScheme,
    team_colour: str,
    wardrobe: Dict[str, List[str]],
    game_users: List[UserModel],
    user_id: Optional[UUID],
    threshold: int,
) -> List[Option]:
    """Every wearable, currently-free outfit for a player joining
    ``team_colour``, ranked best first (plan C4).

    Enumerates the product of the player's declared colours on each wardrobe
    channel (or that channel's whole palette, when nothing was declared -
    "no constraint", not "no options") times every armband colour, hat
    pinned to ``team_colour``. An empty ``wardrobe`` entry for a channel is
    therefore as unconstrained as an absent one.

    Each candidate is gated on ``threshold`` (its minimum
    :func:`~backend.identity.overrides.overlap_distance` to every other
    placed player's effective word in the game, ``user_id`` excluded) and on
    having a free slot at all (:func:`~backend.identity.overrides.nearest_slots`
    against every slot already claimed by someone else). Survivors are
    ranked ``(overrides needed, -rarity, -min_distance, symbols)``: distance
    from a canonical codeword beats rarity absolutely - an option needing no
    overrides always outranks a rarer one needing even one - and rarity (the
    summed ``1 - commonness`` over the *wardrobe* channels only; the hat is
    fixed and the armband is ours) only breaks ties within a tier. The final
    ``symbols`` key (the candidate's own codeword-shaped word, numeric) makes
    the order fully deterministic.

    Finally, the ranked list is collapsed to **one option per distinct
    combination of the wardrobe channels** (e.g. one per tshirt+trousers
    pair): the armband is ours to assign, not the player's to choose, so
    letting it vary would offer a choice the player has no stake in - rows
    differing only in armband colour would even render identically once the
    picker stops displaying it (plan revision, roadmap #10). Because the
    list is already ranked, the survivor kept from each group is
    automatically its best-separating armband. Done here, inside
    :func:`outfit_options` itself, so ``total`` and the pagination in
    :func:`outfit_options_page` stay honest.
    """
    wardrobe_channels = _wardrobe_channels(scheme)

    others_users = [u for u in game_users if u.id != user_id]
    others = effective_words(others_users, scheme)
    taken_slots = {
        u.identity_slot
        for u in game_users
        if u.identity_slot is not None and u.id != user_id
    }

    choice_lists: List[List[str]] = []
    for i, channel in enumerate(scheme.channels):
        addressable = channel.labels[: scheme.channels.max_addressable_symbol(i)]
        if channel.name == TEAM_CHANNEL:
            choice_lists.append([team_colour])
        elif channel.name == PROVIDED_CHANNEL:
            choice_lists.append(addressable)
        else:
            declared = [
                label
                for label in wardrobe.get(channel.name) or []
                if label in addressable
            ]
            choice_lists.append(declared or addressable)

    scored = []
    for combo in product(*choice_lists):
        appearance = dict(zip(scheme.channels.names, combo))
        word = tuple(
            scheme.channels.by_name(name).label_to_index(label)
            for name, label in appearance.items()
        )

        min_distance = (
            min(overlap_distance(word, other_word) for other_word in others.values())
            if others
            else scheme.channels.n
        )
        if min_distance < threshold:
            continue

        slots = nearest_slots(word, scheme, taken=taken_slots)
        if not slots:
            continue
        slot = slots[0]
        overrides = overrides_for(word, slot, scheme)
        rarity = sum(
            1 - commonness_for(name, appearance[name]) for name in wardrobe_channels
        )

        scored.append(
            (
                Option(
                    appearance=appearance,
                    slot=slot,
                    overrides=overrides,
                    overrides_needed=len(overrides),
                    rarity=rarity,
                    min_distance=min_distance,
                    is_canonical=len(overrides) == 0,
                ),
                word,
            )
        )

    scored.sort(
        key=lambda item: (
            item[0].overrides_needed,
            -item[0].rarity,
            -item[0].min_distance,
            item[1],
        )
    )

    seen_combos = set()
    deduped = []
    for option, _word in scored:
        combo = tuple(option.appearance[name] for name in wardrobe_channels)
        if combo in seen_combos:
            continue
        seen_combos.add(combo)
        deduped.append(option)
    return deduped


def join_options(user_id: UUID, code: JoinCodeModel) -> dict:
    """The outfit-picking page's first load: team identity, the colour
    palette, and the caller's own state if they already have one.

    Deliberately non-mutating and **creates no ``User`` row** - a team link
    pasted into a group chat gets prefetched by a link-preview bot, and that
    must not burn an outfit. The caller is found by scanning the game's
    existing roster rather than calling ``UserInterface.get_user()``, which
    would lazily create the row.
    """
    scheme = default_scheme()
    admin = AdminInterface()
    team = _team_for_pick(admin, code)

    game_users = admin.get_users_for_game(code.game_id)
    caller = next((u for u in game_users if u.id == user_id), None)

    return {
        "team_id": team.id,
        "team_name": team.name,
        "team_colour": team.identity_colour,
        "team_channel": TEAM_CHANNEL,
        "provided_channel": PROVIDED_CHANNEL,
        "wardrobe_channels": _wardrobe_channels(scheme),
        "channels": _channels_payload(scheme),
        "you": _player_row(caller, scheme) if caller is not None else None,
    }


OUTFIT_OPTIONS_PAGE_SIZE = 12


def outfit_options_page(
    user_id: UUID,
    code: JoinCodeModel,
    wardrobe: Dict[str, List[str]],
    relaxed: bool,
    page: int,
) -> dict:
    """One page of :func:`outfit_options`, for ``POST /outfit_options``.

    A POST because the wardrobe is a request body, but it writes nothing.
    ``threshold`` is ``scheme.code.min_distance()`` (as ``build_report``
    already uses, not a literal 3); ``relaxed`` loosens it by one, matching
    the page's "Yes, I'm sure I don't have any more clothes" button.

    Never refuses a player (plan §12.6): only once the caller has already
    confirmed ``relaxed`` and *that* pass is also empty (two teammates both
    owning only black, say) does this fall back to the best achievable
    options regardless of distance, flagged via ``exhausted`` so the page can
    say so. A plain (non-relaxed) empty result is not that case - it is the
    ordinary "offer the relaxed button" empty state.
    """
    scheme = default_scheme()
    admin = AdminInterface()
    team = _team_for_pick(admin, code)
    if team.identity_colour is None:
        raise IdentityAdminError(
            "team has no colour pinned yet - generate join codes first"
        )

    _validate_wardrobe(scheme, wardrobe)
    game_users = admin.get_users_for_game(code.game_id)

    threshold = scheme.code.min_distance()
    gate = threshold - 1 if relaxed else threshold
    options = outfit_options(
        scheme, team.identity_colour, wardrobe, game_users, user_id, gate
    )

    exhausted = False
    if relaxed and not options:
        exhausted = True
        options = outfit_options(
            scheme, team.identity_colour, wardrobe, game_users, user_id, 0
        )

    total = len(options)
    page = max(page, 0)
    start = page * OUTFIT_OPTIONS_PAGE_SIZE
    end = start + OUTFIT_OPTIONS_PAGE_SIZE
    page_options = options[start:end]

    return {
        "options": [option._asdict() for option in page_options],
        "page": page,
        "page_size": OUTFIT_OPTIONS_PAGE_SIZE,
        "total": total,
        "threshold": threshold,
        "relaxed": relaxed,
        "exhausted": exhausted,
    }


def _revalidate_appearance(
    scheme: IdentityScheme,
    team_colour: str,
    wardrobe: Dict[str, List[str]],
    game_users: List[UserModel],
    user_id: UUID,
    appearance: Dict[str, str],
    threshold: int,
) -> Option:
    """Re-derive ``appearance``'s slot/overrides from freshly read state
    (called inside ``pick_outfit_lock``, after re-reading ``game_users``).

    Never trusts the client's own reasoning about which option this was: it
    re-enumerates every currently wearable, currently free outfit exactly as
    :func:`outfit_options` does, with no distance gate at all, and requires
    an exact appearance match. A colour outside the declared wardrobe, a slot
    someone else just took, and a stale/fabricated appearance all come out
    the same way - simply absent from the recomputed set - so there is
    nothing here for a malicious client to distinguish.

    An appearance that clears the gate this file offered but has since
    dropped below the *relaxed* threshold (because someone else was placed
    nearby in the meantime) is rejected too, unless nothing else currently
    clears the relaxed threshold either - the same "never refuse a player"
    escape hatch ``outfit_options_page`` applies, so a legitimately exhausted
    pick is never bounced on a technicality.
    """
    all_options = outfit_options(scheme, team_colour, wardrobe, game_users, user_id, 0)
    matching = next((o for o in all_options if o.appearance == appearance), None)
    if matching is None:
        raise OutfitUnavailableError(
            "That outfit isn't available any more - someone may have just "
            "taken it. Please choose again."
        )

    relaxed_threshold = threshold - 1
    if matching.min_distance < relaxed_threshold and any(
        o.min_distance >= relaxed_threshold for o in all_options
    ):
        raise OutfitUnavailableError(
            "Someone just took that outfit - please choose again."
        )

    return matching


# Serialises pick_outfit's read -> validate -> write, the same precedent as
# make_user_lock (backend/user_interface.py): the deployment is a single
# uvicorn process, so a plain in-process lock is sufficient today. If this
# ever runs multi-process, the upgrade is a `with_for_update` row lock taken
# when game_users is read, not this lock.
pick_outfit_lock = RLock()


def pick_outfit(
    user_id: UUID,
    code: JoinCodeModel,
    wardrobe: Dict[str, List[str]],
    appearance: Dict[str, str],
    confirmed: bool,
) -> dict:
    """Claim ``appearance`` for ``user_id`` in ``code``'s team, for
    ``POST /pick_outfit``.

    ``confirmed`` must be exactly ``True`` - the page's "I own these and
    I'll wear them on the night" checkbox - or the request is rejected with
    a readable error before anything is read or written.

    A revisit by someone who already holds a slot in this team is an
    idempotent no-op (mirrors ``claim_join_slot``'s re-scan branch): their
    unchanged ``_player_row`` comes back and no second ticker message is
    sent. Otherwise ``appearance`` is re-validated against freshly read state
    under ``pick_outfit_lock`` (see ``_revalidate_appearance``) before the
    write - the client's belief about which option this was is never
    trusted. ``join_team_and_claim_slot``'s own in-transaction holder check
    (backend/user_interface.py) stays as the final backstop.
    """
    if confirmed is not True:
        raise IdentityAdminError(
            "tick the confirmation box - you must own and wear these colours "
            "on the night - before picking an outfit"
        )

    scheme = default_scheme()
    admin = AdminInterface()
    team = _team_for_pick(admin, code)
    if team.identity_colour is None:
        raise IdentityAdminError(
            "team has no colour pinned yet - generate join codes first"
        )

    _validate_wardrobe(scheme, wardrobe)
    threshold = scheme.code.min_distance()

    with pick_outfit_lock:
        game_users = admin.get_users_for_game(code.game_id)

        scanner = next((u for u in game_users if u.id == user_id), None)
        if (
            scanner is not None
            and scanner.team_id == code.team_id
            and scanner.identity_slot is not None
        ):
            # Idempotent revisit - same shape as claim_join_slot's re-scan.
            return _player_row(scanner, scheme)

        option = _revalidate_appearance(
            scheme,
            team.identity_colour,
            wardrobe,
            game_users,
            user_id,
            appearance,
            threshold,
        )

        overrides_json = json.dumps(option.overrides) if option.overrides else None
        wardrobe_json = json.dumps(wardrobe)

        with UserInterface(user_id) as ui:
            ui.join_team_and_claim_slot(
                code.team_id, option.slot, overrides_json, wardrobe_json
            )

            u = ui.get_user()

            user_name = u.name
            team_name = u.team.name
            game_id = u.team.game_id

            tk.send_ticker_message(
                tk.TickerMessageType.USER_JOINED_TEAM,
                {"user": user_name, "team": team_name},
                game_id=game_id,
                session=ui.get_session(),
            )

        updated = admin.get_user_model(user_id)
        row = _player_row(updated, scheme)
        row["min_distance"] = option.min_distance
        return row


# ---------------------------------------------------------------------------
# GET /admin_join_qr_codes
# ---------------------------------------------------------------------------


def build_join_codes(game_id: UUID) -> dict:
    """One signed *team* join QR per team, each pinned to its own hat colour.

    Teams are ordered by creation time (:meth:`AdminInterface.get_teams_for_game`)
    and coloured via :func:`~backend.identity.allocation.assign_team_colours`,
    which honours any colour a team already has (``Team.identity_colour``) and
    only assigns fresh colours to teams that don't. **Generating these codes
    therefore writes to the database on what looks like a GET** - this is
    deliberate, not an oversight: it is the moment the admin commits a team to
    its hat colour, and it is idempotent after the first call (calling again,
    even after adding a new team, leaves every already-coloured team exactly
    as it was - see ``assign_team_colours``'s docstring for why). There is no
    separate "pin now" step; if there were, it would be a footgun on game
    night - an admin who forgot to press it before printing cards would print
    colours that later generation could still reshuffle.

    A player scans the printed code and picks their own outfit from the
    team's colour (see the C4 endpoints) rather than being handed a fixed
    slot - contrast :func:`make_join_url`, the older per-slot code that
    ``claim_join_slot`` still serves unchanged.
    """
    scheme = default_scheme()
    teams = AdminInterface().get_teams_for_game(game_id)  # 404s if game missing

    if not teams:
        raise IdentityAdminError("game has no teams - create the teams first")

    try:
        colours = assign_team_colours(
            scheme, TEAM_CHANNEL, {t.id: t.identity_colour for t in teams}
        )
    except ValueError as e:
        raise IdentityAdminError(str(e))

    capacity = colour_capacity(scheme, TEAM_CHANNEL)
    admin = AdminInterface()

    out = []
    for team in teams:
        colour = colours[team.id]
        if team.identity_colour != colour:
            admin.set_team_identity_colour(team.id, colour)

        out.append(
            {
                "team_id": team.id,
                "team_name": team.name,
                "team_colour": colour,
                "team_colour_hex": hex_for(TEAM_CHANNEL, colour),
                "capacity": capacity[colour],
                "encoded_url": make_team_join_url(game_id, team.id),
            }
        )

    return {"team_channel": TEAM_CHANNEL, "teams": out}


# ---------------------------------------------------------------------------
# POST /admin_identity_suggest
# ---------------------------------------------------------------------------


def suggest_identity(request: IdentitySuggestRequest) -> dict:
    scheme = default_scheme()
    users = AdminInterface().get_users_for_game(request.game_id)  # 404s if missing

    others_users = [u for u in users if u.id != request.user_id]
    others = effective_words(others_users, scheme)
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
