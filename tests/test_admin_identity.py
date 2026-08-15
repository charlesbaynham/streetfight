import json

import pytest
from fastapi.exceptions import HTTPException

from backend import identity_admin
from backend.identity.config import default_scheme
from backend.identity_admin import IdentityAdminError
from backend.identity_admin import IdentitySetRequest
from backend.identity_admin import IdentitySuggestRequest
from backend.model import User
from backend.user_interface import UserInterface

SCHEME = default_scheme()


# Mock "schedule_update_event" since we don't have an asyncio loop, same
# pattern as tests/test_admin_mode.py and tests/test_items.py.
@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def set_identity_raw(db_session, user_id, slot, overrides=None):
    """Write identity_slot/identity_overrides directly, bypassing all
    admin_identity_set validation -- used to build fixture scenarios (e.g. a
    deliberately confusable pair) that the API itself would reject.
    """
    user = db_session.get(User, user_id)
    user.identity_slot = slot
    user.identity_overrides = json.dumps(overrides) if overrides is not None else None
    db_session.commit()


def add_player(db_session, user_factory, team_id, name=None):
    user_id = user_factory()
    with UserInterface(user_id) as ui:
        ui.join_team(team_id)
        if name is not None:
            ui.set_name(name)
    return user_id


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def test_report_empty_game(one_game):
    report = identity_admin.build_report(one_game)

    assert report["players"] == []
    assert report["pairs"] == []
    assert report["effective_min_distance"] is None
    assert report["nominal_min_distance"] == 3
    assert sorted(report["free_slots"]) == sorted(SCHEME.usable_slots())
    assert [c["name"] for c in report["channels"]] == [
        "tshirt",
        "trousers",
        "hat",
        "armbands",
    ]
    # hex is keyed by the addressable labels for that channel
    tshirt = next(c for c in report["channels"] if c["name"] == "tshirt")
    assert tshirt["hex"]["purple"] == "#6A1B9A"
    trousers = next(c for c in report["channels"] if c["name"] == "trousers")
    assert set(trousers["labels"]) == {"black", "blue", "green", "red", "white"}


def test_report_unknown_game_404():
    import uuid

    with pytest.raises(HTTPException) as exc_info:
        identity_admin.build_report(uuid.uuid4())
    assert exc_info.value.status_code == 404


def test_report_players_with_and_without_slots(
    db_session, one_game, one_team, user_factory
):
    u1 = add_player(db_session, user_factory, one_team, name="Alice")
    u2 = add_player(db_session, user_factory, one_team, name="Bob")

    set_identity_raw(db_session, u1, 1)

    report = identity_admin.build_report(one_game)
    players_by_id = {p["user_id"]: p for p in report["players"]}

    assert players_by_id[u1]["slot"] == 1
    assert players_by_id[u1]["canonical_appearance"] is not None
    assert (
        players_by_id[u1]["effective_appearance"]
        == players_by_id[u1]["canonical_appearance"]
    )
    assert players_by_id[u1]["overridden"] is False

    assert players_by_id[u2]["slot"] is None
    assert players_by_id[u2]["canonical_appearance"] is None
    assert players_by_id[u2]["effective_appearance"] is None
    assert players_by_id[u2]["overridden"] is False

    # A slot-less player contributes no effective word, so is excluded from
    # every pairwise computation -- nothing to warn about with only one
    # slot-holder in the game.
    assert report["pairs"] == []
    assert report["effective_min_distance"] is None


def test_report_overrides_reflected_in_effective_appearance(
    db_session, one_game, one_team, user_factory
):
    u1 = add_player(db_session, user_factory, one_team)
    canonical = SCHEME.channels.codeword_to_appearance(SCHEME.codeword_of_slot(1))
    set_identity_raw(db_session, u1, 1, overrides={"tshirt": "yellow", "hat": None})

    report = identity_admin.build_report(one_game)
    player = next(p for p in report["players"] if p["user_id"] == u1)

    assert player["overrides"] == {"tshirt": "yellow", "hat": None}
    assert player["overridden"] is True
    assert player["canonical_appearance"] == canonical
    assert player["effective_appearance"]["tshirt"] == "yellow"
    assert player["effective_appearance"]["hat"] is None
    # Untouched channels keep the canonical colour
    assert player["effective_appearance"]["trousers"] == canonical["trousers"]
    assert player["effective_appearance"]["armbands"] == canonical["armbands"]


def test_report_pairs_and_levels(db_session, one_game, one_team, user_factory):
    # Slots 1 and 2 -> (1,1,1,1) and (2,2,2,2), nominal distance 4 apart.
    # Override player B onto player A's outfit one channel at a time to walk
    # the distance down from 4 to 0.
    a = add_player(db_session, user_factory, one_team, name="Aardvark")
    b = add_player(db_session, user_factory, one_team, name="Badger")
    set_identity_raw(db_session, a, 1)
    set_identity_raw(
        db_session,
        b,
        2,
        overrides={"tshirt": "purple", "hat": "purple", "armbands": "purple"},
    )
    # b's effective word: (1, 2, 1, 1) vs a's (1, 1, 1, 1) -> distance 1

    report = identity_admin.build_report(one_game)
    assert len(report["pairs"]) == 1
    pair = report["pairs"][0]
    assert pair["distance"] == 1
    assert pair["level"] == "danger"
    assert {pair["name_a"], pair["name_b"]} == {"Aardvark", "Badger"}
    assert report["effective_min_distance"] == 1

    # Now make them identical -> distance 0, "critical"
    set_identity_raw(
        db_session,
        b,
        2,
        overrides={
            "tshirt": "purple",
            "trousers": "blue",
            "hat": "purple",
            "armbands": "purple",
        },
    )
    report = identity_admin.build_report(one_game)
    assert len(report["pairs"]) == 1
    pair = report["pairs"][0]
    assert pair["distance"] == 0
    assert pair["level"] == "critical"
    assert report["effective_min_distance"] == 0


def test_report_free_slots_shrinks_as_slots_assigned(
    db_session, one_game, one_team, user_factory
):
    report = identity_admin.build_report(one_game)
    initial_free = set(report["free_slots"])
    assert 1 in initial_free

    u1 = add_player(db_session, user_factory, one_team)
    set_identity_raw(db_session, u1, 1)

    report = identity_admin.build_report(one_game)
    assert 1 not in set(report["free_slots"])
    assert set(report["free_slots"]) == initial_free - {1}


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_set_happy_path_touches_and_updates(
    mocker, db_session, one_game, one_team, user_factory
):
    trigger_mock = mocker.patch("backend.asyncio_triggers.trigger_update_event")
    u1 = add_player(db_session, user_factory, one_team, name="Alice")

    before_tag = db_session.get(User, u1).update_tag
    db_session.expire_all()

    result = identity_admin.set_identity(
        IdentitySetRequest(user_id=u1, slot=1, overrides=None)
    )

    assert result["slot"] == 1
    assert result["user_id"] == u1

    db_session.expire_all()
    after = db_session.get(User, u1)
    assert after.identity_slot == 1
    assert after.update_tag != before_tag

    assert any(
        call.args[0] == "user" and call.args[1] == u1
        for call in trigger_mock.call_args_list
    )


def test_set_slot_taken_400(db_session, one_game, one_team, user_factory):
    u1 = add_player(db_session, user_factory, one_team, name="Alice")
    u2 = add_player(db_session, user_factory, one_team, name="Bob")
    set_identity_raw(db_session, u1, 1)

    with pytest.raises(IdentityAdminError) as exc_info:
        identity_admin.set_identity(IdentitySetRequest(user_id=u2, slot=1))
    assert "Alice" in str(exc_info.value)


def test_set_unusable_slot_400(db_session, one_game, one_team, user_factory):
    u1 = add_player(db_session, user_factory, one_team)
    # slot 0 (all black) is deliberately excluded from usable_slots()
    with pytest.raises(IdentityAdminError):
        identity_admin.set_identity(IdentitySetRequest(user_id=u1, slot=0))


def test_set_overrides_without_slot_400(db_session, one_game, one_team, user_factory):
    u1 = add_player(db_session, user_factory, one_team)
    with pytest.raises(IdentityAdminError, match="assign a slot first"):
        identity_admin.set_identity(
            IdentitySetRequest(user_id=u1, slot=None, overrides={"tshirt": "red"})
        )


def test_set_bad_label_400(db_session, one_game, one_team, user_factory):
    u1 = add_player(db_session, user_factory, one_team)
    with pytest.raises(IdentityAdminError):
        identity_admin.set_identity(
            IdentitySetRequest(
                user_id=u1, slot=1, overrides={"trousers": "yellow"}
            )  # yellow isn't in the restricted trousers palette
        )


def test_set_collision_400_names_player(db_session, one_game, one_team, user_factory):
    a = add_player(db_session, user_factory, one_team, name="Aardvark")
    b = add_player(db_session, user_factory, one_team, name="Badger")
    set_identity_raw(db_session, a, 1)

    with pytest.raises(IdentityAdminError) as exc_info:
        identity_admin.set_identity(
            IdentitySetRequest(
                user_id=b,
                slot=2,
                overrides={
                    "tshirt": "purple",
                    "trousers": "blue",
                    "hat": "purple",
                    "armbands": "purple",
                },
            )
        )
    assert "Aardvark" in str(exc_info.value)


def test_set_force_overrides_collision(db_session, one_game, one_team, user_factory):
    a = add_player(db_session, user_factory, one_team, name="Aardvark")
    b = add_player(db_session, user_factory, one_team, name="Badger")
    set_identity_raw(db_session, a, 1)

    result = identity_admin.set_identity(
        IdentitySetRequest(
            user_id=b,
            slot=2,
            overrides={
                "tshirt": "purple",
                "trousers": "blue",
                "hat": "purple",
                "armbands": "purple",
            },
            force=True,
        )
    )
    assert result["slot"] == 2
    # The write succeeded despite the collision
    db_session.expire_all()
    assert db_session.get(User, b).identity_slot == 2
    assert db_session.get(User, b).identity_overrides is not None


def test_set_slot_null_clears_overrides(db_session, one_game, one_team, user_factory):
    u1 = add_player(db_session, user_factory, one_team)
    set_identity_raw(db_session, u1, 1, overrides={"tshirt": "yellow"})

    result = identity_admin.set_identity(
        IdentitySetRequest(user_id=u1, slot=None, overrides=None)
    )
    assert result["slot"] is None
    assert result["overrides"] is None
    assert result["overridden"] is False

    db_session.expire_all()
    after = db_session.get(User, u1)
    assert after.identity_slot is None
    assert after.identity_overrides is None


def test_set_overrides_full_replacement(db_session, one_game, one_team, user_factory):
    u1 = add_player(db_session, user_factory, one_team)
    set_identity_raw(db_session, u1, 1, overrides={"tshirt": "yellow", "hat": "orange"})

    # Writing a new (different) overrides dict fully replaces the old one --
    # "hat" is not carried forward.
    result = identity_admin.set_identity(
        IdentitySetRequest(user_id=u1, slot=1, overrides={"armbands": "yellow"})
    )
    assert result["overrides"] == {"armbands": "yellow"}
    assert "hat" not in result["overrides"]
    assert "tshirt" not in result["overrides"]


# ---------------------------------------------------------------------------
# suggest
# ---------------------------------------------------------------------------


def test_suggest_returns_ranked_suggestions(
    db_session, one_game, one_team, user_factory
):
    a = add_player(db_session, user_factory, one_team, name="Aardvark")
    set_identity_raw(db_session, a, 1)
    newcomer = add_player(db_session, user_factory, one_team, name="Newcomer")

    result = identity_admin.suggest_identity(
        IdentitySuggestRequest(
            game_id=one_game,
            user_id=newcomer,
            fixed={},
            free=["armbands"],
        )
    )

    assert len(result["suggestions"]) > 0
    first = result["suggestions"][0]
    assert set(first.keys()) == {
        "assignment",
        "min_distance",
        "closest_players",
        "slot",
        "overrides",
        "effective_appearance",
    }
    assert first["slot"] in SCHEME.usable_slots()
    # Suggestions are ranked best (largest min_distance) first
    distances = [s["min_distance"] for s in result["suggestions"]]
    assert distances == sorted(distances, reverse=True)


def test_suggest_apply_reproduces_effective_appearance(
    db_session, one_game, one_team, user_factory
):
    a = add_player(db_session, user_factory, one_team, name="Aardvark")
    set_identity_raw(db_session, a, 1)
    newcomer = add_player(db_session, user_factory, one_team, name="Newcomer")

    result = identity_admin.suggest_identity(
        IdentitySuggestRequest(
            game_id=one_game,
            user_id=newcomer,
            fixed={},
            free=["armbands"],
        )
    )
    suggestion = result["suggestions"][0]

    applied = identity_admin.set_identity(
        IdentitySetRequest(
            user_id=newcomer,
            slot=suggestion["slot"],
            overrides=suggestion["overrides"] or None,
        )
    )

    assert applied["effective_appearance"] == suggestion["effective_appearance"]

    report = identity_admin.build_report(one_game)
    player = next(p for p in report["players"] if p["user_id"] == newcomer)
    assert player["effective_appearance"] == suggestion["effective_appearance"]


def test_suggest_excludes_own_word(db_session, one_game, one_team, user_factory):
    a = add_player(db_session, user_factory, one_team, name="Aardvark")
    set_identity_raw(db_session, a, 1)

    # Asking for suggestions for `a` themselves: their own current word must
    # not appear in `others` (it would trivially make every candidate look
    # maximally bad against itself).
    result = identity_admin.suggest_identity(
        IdentitySuggestRequest(
            game_id=one_game,
            user_id=a,
            fixed={"tshirt": "purple", "hat": "purple", "trousers": "blue"},
            free=["armbands"],
        )
    )
    # With only `a` in the game and `a` excluded from `others`, there is
    # nothing to avoid via criterion 1, so distance is reported as the
    # sentinel channels.n (no real constraint).
    assert result["suggestions"][0]["min_distance"] == len(SCHEME.channels.names)
    assert result["suggestions"][0]["closest_players"] == []


def test_suggest_no_free_slots_returns_empty(
    db_session, one_game, one_team, user_factory
):
    # Fill every usable slot so nothing is left to suggest into.
    users = [
        add_player(db_session, user_factory, one_team, name=f"p{slot}")
        for slot in SCHEME.usable_slots()
    ]
    for user_id, slot in zip(users, SCHEME.usable_slots()):
        set_identity_raw(db_session, user_id, slot)

    newcomer = add_player(db_session, user_factory, one_team, name="Newcomer")
    result = identity_admin.suggest_identity(
        IdentitySuggestRequest(
            game_id=one_game, user_id=newcomer, fixed={}, free=["armbands"]
        )
    )
    assert result["suggestions"] == []


# ---------------------------------------------------------------------------
# endpoint-level (through the FastAPI test client, matching test_admin_mode.py)
# ---------------------------------------------------------------------------


def test_admin_identity_report_endpoint(
    admin_api_client, db_session, one_game, one_team, user_factory
):
    u1 = add_player(db_session, user_factory, one_team, name="Alice")
    set_identity_raw(db_session, u1, 1)

    response = admin_api_client.get(f"/api/admin_identity_report?game_id={one_game}")
    assert response.is_success
    data = response.json()
    assert len(data["players"]) == 1
    assert data["players"][0]["name"] == "Alice"
    assert data["players"][0]["slot"] == 1


def test_admin_identity_set_endpoint(
    admin_api_client, db_session, one_game, one_team, user_factory
):
    u1 = add_player(db_session, user_factory, one_team, name="Alice")

    response = admin_api_client.post(
        "/api/admin_identity_set",
        json={"user_id": str(u1), "slot": 1, "overrides": None, "force": False},
    )
    assert response.is_success
    data = response.json()
    assert data["slot"] == 1

    db_session.expire_all()
    assert db_session.get(User, u1).identity_slot == 1


def test_admin_identity_set_endpoint_400_on_bad_slot(
    admin_api_client, db_session, one_game, one_team, user_factory
):
    u1 = add_player(db_session, user_factory, one_team, name="Alice")

    response = admin_api_client.post(
        "/api/admin_identity_set",
        json={"user_id": str(u1), "slot": 0, "overrides": None, "force": False},
    )
    assert response.status_code == 400


def test_admin_identity_suggest_endpoint(
    admin_api_client, db_session, one_game, one_team, user_factory
):
    u1 = add_player(db_session, user_factory, one_team, name="Alice")

    response = admin_api_client.post(
        "/api/admin_identity_suggest",
        json={
            "game_id": str(one_game),
            "user_id": str(u1),
            "fixed": {},
            "free": ["armbands"],
        },
    )
    assert response.is_success
    data = response.json()
    assert "suggestions" in data


def test_admin_identity_requires_admin_auth(api_client, one_game):
    response = api_client.get(f"/api/admin_identity_report?game_id={one_game}")
    assert response.status_code == 403
