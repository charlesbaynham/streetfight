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
from backend.identity.config import default_scheme
from backend.identity_admin import IdentitySetRequest
from backend.identity_admin import build_join_codes
from backend.identity_admin import outfit_options_page
from backend.identity_admin import pick_outfit
from backend.identity_admin import set_identity
from backend.join_codes import JoinCodeModel
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
        channel: sorted(
            rng.sample(list(scheme.channels.by_name(channel).labels), 2)
        )
        for channel in _wardrobe_channels(scheme)
    }


def provision(seed: int, cast: List[dict]) -> dict:
    """Create the game, the teams and every player's outfit.

    Returns the identity facts the world file needs, keyed by player slug,
    plus the database ids -- which are *not* part of the reproducible world,
    only of this materialisation of it.
    """
    scheme = default_scheme()
    admin = AdminInterface()

    game_id = ids.game_id(seed)
    admin.create_game(game_id)

    team_ids: Dict[str, UUID] = {}
    for team_name in spec.TEAM_NAMES:
        slug = team_name.lower().replace(" ", "-")
        team_ids[team_name] = admin.create_team(
            game_id, team_name, ids.team_id(seed, slug)
        )

    # Pins each team's hat colour. Idempotent afterwards, and the moment the
    # printed cards become meaningful.
    join = build_join_codes(game_id)
    team_colours = {row["team_name"]: row["team_colour"] for row in join["teams"]}

    players: Dict[str, dict] = {}
    late_patches: List[tuple] = []

    for person in cast:
        rng = random.Random(f"{seed}:pick:{person['slug']}")
        user_id = ids.user_id(seed, person["slug"])
        team_id = team_ids[person["team"]]
        code = JoinCodeModel(game_id=game_id, team_id=team_id, slot=None)

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
    for person, user_id, row in late_patches:
        rng = random.Random(f"{seed}:patch:{person['slug']}")
        channel = spec.LATE_PATCH_CHANNEL
        current = row["effective_appearance"][channel]
        alternatives = [
            colour
            for colour in scheme.channels.by_name(channel).labels
            if colour != current
        ]
        replacement = rng.choice(sorted(alternatives))
        result = set_identity(
            IdentitySetRequest(
                user_id=user_id,
                slot=row["slot"],
                overrides={channel: replacement},
                force=True,
            )
        )
        entry = players[person["slug"]]
        entry["overrides"] = result.get("overrides") or {channel: replacement}
        entry["appearance"] = result["effective_appearance"]
        entry["late_patch"] = {"channel": channel, "from": current, "to": replacement}

    return {
        "game_id": str(game_id),
        "team_ids": {name: str(tid) for name, tid in team_ids.items()},
        "team_colours": team_colours,
        "players": players,
    }
