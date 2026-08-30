"""Materialise the cast into a database, through the real picking code.

Nothing here shortcuts the game's own logic. Teams are made with
``AdminInterface``, their hat colours are pinned by the real
``build_join_codes``, and every player picks an outfit through
``join_options`` -> ``outfit_options_page`` -> ``pick_outfit`` exactly as a
phone would. That is the point: a fixture that wrote rows straight into the
tables would not exercise the allocator, and the allocator is one of the
things a thirty-player game is meant to test.

The three picking behaviours are the plan's, and they differ only in what the
player claims to own:

* **canonical** -- owns one of everything, and takes the best option offered.

  Note what this locks and what it does not. It locks the *behaviour*: this
  player declares a full wardrobe and accepts what the allocator ranks first.
  It does not guarantee the outcome is override-free, and in practice it is
  not: with thirty of forty-nine codewords taken and every pick gated on
  Hamming distance against everyone already placed, the players who pick last
  can be offered nothing clean however much they own. The first run of this
  fixture produced three such players, and one who needed the relaxed gate.
  That is a real property of picking freely at this occupancy (the effect
  ``scripts/simulate_code_capacity.py`` exists to quantify), so it is recorded
  in the world file and reported at the gate rather than engineered away by
  reordering the picks.
* **constrained** -- declares a narrow wardrobe, so the best the allocator can
  offer needs one or more overrides. This is the player who turns up owning
  three t-shirts.
* **late_patch** -- picks canonically, and is then altered at the door with
  ``set_identity``, the way an admin fixes somebody who arrived in the wrong
  thing.
"""

import random
from typing import Dict
from typing import List
from uuid import UUID

from backend.admin_interface import AdminInterface
from backend.database import session_scope
from backend.identity.config import default_scheme
from backend.identity_admin import IdentitySetRequest
from backend.identity_admin import _player_row
from backend.identity_admin import build_join_codes
from backend.identity_admin import outfit_options_page
from backend.identity_admin import pick_outfit
from backend.identity_admin import set_identity
from backend.join_codes import JoinCodeModel
from backend.model import Game
from backend.model import Team
from backend.test_world import ids
from backend.test_world import spec
from backend.user_interface import UserInterface


def _wardrobe_channels(scheme) -> List[str]:
    from backend.identity_admin import _wardrobe_channels as real

    return real(scheme)


def _full_wardrobe(scheme) -> Dict[str, List[str]]:
    """Somebody who owns one of everything."""
    return {
        channel: list(scheme.channels.by_name(channel).labels)
        for channel in _wardrobe_channels(scheme)
    }


def _narrow_wardrobe(scheme, rng: random.Random) -> Dict[str, List[str]]:
    """Somebody who owns very little, so the allocator has to compromise.

    Two colours per wardrobe channel. With four channels and a minimum
    distance of three, that is usually too few for a clean codeword, which is
    exactly the case worth having in the fixture.
    """
    return {
        channel: sorted(rng.sample(list(scheme.channels.by_name(channel).labels), 2))
        for channel in _wardrobe_channels(scheme)
    }


def provision(seed: int, cast: List[dict]) -> dict:
    """Create the game, the teams and every player's outfit.

    Resumable: safe to call again over a game that a previous call left
    part-provisioned (``make_debug_entries`` is called that way by
    ``backend.demo_game`` -- see its docstring). The game and each team are
    only created if their row is missing (``create_team`` would otherwise hit
    a primary-key collision), and a player who already holds a team and an
    identity slot in this game is taken as-is rather than sent through
    ``outfit_options_page`` again -- that call gates on Hamming distance
    against everyone already placed *including this player*, so it can
    legitimately offer nothing to somebody who has already picked, and would
    raise the "no outfit could be offered" error below for exactly the
    players a resumed run should be skipping.

    Returns the identity facts the world file needs, keyed by player slug,
    plus the database ids -- which are *not* part of the reproducible world,
    only of this materialisation of it.
    """
    scheme = default_scheme()
    admin = AdminInterface()

    game_id = ids.game_id(seed)
    with session_scope() as session:
        game_present = session.get(Game, game_id) is not None
    if not game_present:
        admin.create_game(game_id)

    team_ids: Dict[str, UUID] = {}
    for team_name in spec.TEAM_NAMES:
        slug = team_name.lower().replace(" ", "-")
        team_id = ids.team_id(seed, slug)
        with session_scope() as session:
            team_present = session.get(Team, team_id) is not None
        if not team_present:
            admin.create_team(game_id, team_name, team_id)
        team_ids[team_name] = team_id

    # Pins each team's hat colour. Idempotent afterwards, and the moment the
    # printed cards become meaningful.
    join = build_join_codes(game_id)
    team_colours = {row["team_name"]: row["team_colour"] for row in join["teams"]}

    placed = {u.id: u for u in admin.get_users_for_game(game_id)}

    players: Dict[str, dict] = {}
    late_patches: List[tuple] = []

    for person in cast:
        user_id = ids.user_id(seed, person["slug"])
        team_id = team_ids[person["team"]]
        code = JoinCodeModel(game_id=game_id, team_id=team_id, slot=None)

        existing = placed.get(user_id)
        if (
            existing is not None
            and existing.team_id == team_id
            and existing.identity_slot is not None
        ):
            # Already picked in an earlier, interrupted call - take the row
            # the database already holds (including the stored
            # identity_wardrobe) instead of asking the allocator again.
            row = _player_row(existing, scheme)
            players[person["slug"]] = {
                "user_id": str(user_id),
                "team": person["team"],
                "team_colour": team_colours[person["team"]],
                "slot": row["slot"],
                "overrides": row.get("overrides") or {},
                "appearance": row["effective_appearance"],
                "canonical_appearance": row["canonical_appearance"],
                "wardrobe": row["wardrobe"],
                "picking": person["picking"],
                # Facts about the pick itself, not recoverable from the
                # database once it already happened. Only
                # `python -m backend.test_world world` reads them, and that
                # always provisions a fresh database, so this branch is never
                # what it sees.
                "relaxed": False,
                "exhausted": False,
            }
            if person["picking"] == "late_patch":
                late_patches.append((person, user_id, row))
            continue

        rng = random.Random(f"{seed}:pick:{person['slug']}")

        with UserInterface(user_id) as ui:
            ui.set_name(person["name"])

        if person["picking"] == "constrained":
            wardrobe = _narrow_wardrobe(scheme, rng)
        else:
            wardrobe = _full_wardrobe(scheme)

        page = outfit_options_page(user_id, code, wardrobe, relaxed=False, page=0)
        if not page["options"]:
            # The player said they own too little for a clean answer. The real
            # page's next move is the "I'm sure I have nothing else" button,
            # so take it rather than inventing a wardrobe they did not claim.
            page = outfit_options_page(user_id, code, wardrobe, relaxed=True, page=0)
        if not page["options"]:
            raise RuntimeError(
                f"no outfit could be offered to {person['slug']} even relaxed"
            )

        option = page["options"][0]
        row = pick_outfit(
            user_id,
            code,
            wardrobe,
            appearance=option["appearance"],
            confirmed=True,
        )

        players[person["slug"]] = {
            "user_id": str(user_id),
            "team": person["team"],
            "team_colour": team_colours[person["team"]],
            "slot": row["slot"],
            "overrides": row.get("overrides") or {},
            # The *effective* appearance: the codeword's colours with any
            # overrides applied. This is what the player actually wears, and
            # therefore what a photograph of them has to show.
            "appearance": row["effective_appearance"],
            "canonical_appearance": row["canonical_appearance"],
            "wardrobe": wardrobe,
            "picking": person["picking"],
            "relaxed": page["relaxed"],
            "exhausted": page["exhausted"],
        }

        if person["picking"] == "late_patch":
            late_patches.append((person, user_id, row))

    # The door patches happen after everybody has picked, because that is when
    # they happen in life: the admin is looking at a player who is already in
    # the game and already has a slot.
    #
    # The baseline is the *canonical* colour of the patched channel, not
    # whatever the player's row currently shows there. That makes the
    # replacement -- same seed, same baseline -- the same colour every time
    # this runs, so a resumed call finds the earlier patch already reflected
    # in `effective_appearance` and skips re-issuing it, rather than patching
    # an already-patched player again from a baseline the first patch moved.
    for person, user_id, row in late_patches:
        rng = random.Random(f"{seed}:patch:{person['slug']}")
        channel = spec.LATE_PATCH_CHANNEL
        current = row["canonical_appearance"][channel]
        alternatives = [
            colour
            for colour in scheme.channels.by_name(channel).labels
            if colour != current
        ]
        replacement = rng.choice(sorted(alternatives))

        entry = players[person["slug"]]
        if row["effective_appearance"][channel] == replacement:
            # Already patched by an earlier, interrupted call.
            entry["late_patch"] = {
                "channel": channel,
                "from": current,
                "to": replacement,
            }
            continue

        result = set_identity(
            IdentitySetRequest(
                user_id=user_id,
                slot=row["slot"],
                overrides={channel: replacement},
                force=True,
            )
        )
        entry["overrides"] = result.get("overrides") or {channel: replacement}
        entry["appearance"] = result["effective_appearance"]
        entry["late_patch"] = {"channel": channel, "from": current, "to": replacement}

    return {
        "game_id": str(game_id),
        "team_ids": {name: str(tid) for name, tid in team_ids.items()},
        "team_colours": team_colours,
        "players": players,
    }
