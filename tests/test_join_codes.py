import json
import os
from uuid import UUID
from uuid import uuid4 as get_uuid

import pytest

from backend.identity.allocation import colour_capacity
from backend.identity.config import TEAM_CHANNEL
from backend.identity.config import default_scheme
from backend.identity.config import hex_for
from backend.join_codes import JoinCodeModel
from backend.join_codes import make_join_url
from backend.join_codes import make_team_join_url
from backend.model import Item
from backend.model import Shot
from backend.model import Team
from backend.model import TickerEntry
from backend.model import User
from backend.qr_signing import sign_payload
from backend.user_interface import UserInterface

# Mocking the environment variables for testing
os.environ["SECRET_KEY"] = "test_secret_key"
os.environ.setdefault("WEBSITE_URL", "https://streetfight.example.com")

SCHEME = default_scheme()
SLOT = SCHEME.usable_slots()[0]


# Mock "schedule_update_event" since we don't have an asyncio loop
@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def set_identity_raw(db_session, user_id, slot, overrides=None):
    """Write identity columns directly, bypassing validation - used to build
    scenarios (e.g. a deliberate collision) the API itself would reject.
    """
    user = db_session.get(User, user_id)
    user.identity_slot = slot
    user.identity_overrides = json.dumps(overrides) if overrides is not None else None
    db_session.commit()


def scanner_id(api_client) -> UUID:
    user_id = UUID(api_client.get("/api/my_id").json())
    # Materialise the User row (it is created lazily), so tests can assert on
    # its state after a rejected join
    assert api_client.get("/api/user_info").is_success
    return user_id


def join_via_api(api_client, game_id, team_id, slot):
    return api_client.post(
        "/api/join_game", json={"data": make_join_url(game_id, team_id, slot)}
    )


# ---------------------------------------------------------------------------
# JoinCodeModel unit tests
# ---------------------------------------------------------------------------


def test_join_code_sign_and_roundtrip():
    code = JoinCodeModel(game_id=get_uuid(), team_id=get_uuid(), slot=SLOT).sign()

    decoded = JoinCodeModel.from_base64(code.to_base64())

    assert decoded == code
    assert decoded.validate_signature() is None


def test_join_code_roundtrip_via_url():
    game_id, team_id = get_uuid(), get_uuid()
    url = make_join_url(game_id, team_id, SLOT)

    decoded = JoinCodeModel.from_base64(url)

    assert decoded.game_id == game_id
    assert decoded.team_id == team_id
    assert decoded.slot == SLOT
    assert decoded.validate_signature() is None


def test_join_code_tamper_detected():
    code = JoinCodeModel(game_id=get_uuid(), team_id=get_uuid(), slot=SLOT).sign()

    tampered = code.model_copy()
    tampered.slot = SLOT + 1
    assert tampered.validate_signature() == "Signature mismatch"

    tampered = code.model_copy()
    tampered.team_id = get_uuid()
    assert tampered.validate_signature() == "Signature mismatch"

    unsigned = code.model_copy()
    unsigned.sig = None
    assert unsigned.validate_signature() == "Join code not signed"


def test_join_and_item_signatures_are_domain_separated():
    assert sign_payload("join", "x") != sign_payload("item", "x")


def test_team_join_code_roundtrip_and_tamper():
    game_id, team_id = get_uuid(), get_uuid()
    url = make_team_join_url(game_id, team_id)

    decoded = JoinCodeModel.from_base64(url)
    assert decoded.game_id == game_id
    assert decoded.team_id == team_id
    assert decoded.slot is None
    assert decoded.validate_signature() is None

    tampered = decoded.model_copy()
    tampered.team_id = get_uuid()
    assert tampered.validate_signature() == "Signature mismatch"


def test_team_and_slot_codes_sign_differently():
    game_id, team_id = get_uuid(), get_uuid()

    team_code = JoinCodeModel(game_id=game_id, team_id=team_id, slot=None).sign()
    slot_code = JoinCodeModel(game_id=game_id, team_id=team_id, slot=SLOT).sign()

    assert team_code.sig != slot_code.sig
    # And a slot code can't be re-signed as a team code by nulling its slot -
    # the signature is bound to which kind it is, not just the ids.
    forged = slot_code.model_copy()
    forged.slot = None
    assert forged.validate_signature() == "Signature mismatch"


# ---------------------------------------------------------------------------
# POST /api/join_game
# ---------------------------------------------------------------------------


def test_join_game_happy_path(api_client, db_session, one_game, one_team):
    user_id = scanner_id(api_client)

    response = join_via_api(api_client, one_game, one_team, SLOT)

    assert response.is_success
    data = response.json()
    assert data["slot"] == SLOT

    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id == one_team
    assert user.identity_slot == SLOT
    assert user.identity_overrides is None

    # The join was announced on the game ticker
    team_name = db_session.get(Team, one_team).name
    messages = [
        t.message
        for t in db_session.query(TickerEntry).filter_by(game_id=one_game).all()
    ]
    assert any(f"joined team {team_name}" in m for m in messages)


def test_join_game_rescan_is_idempotent(api_client, db_session, one_game, one_team):
    user_id = scanner_id(api_client)

    assert join_via_api(api_client, one_game, one_team, SLOT).is_success
    response = join_via_api(api_client, one_game, one_team, SLOT)

    assert response.is_success
    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id == one_team
    assert user.identity_slot == SLOT

    # The re-scan did not announce a second join
    join_messages = [
        t.message
        for t in db_session.query(TickerEntry).filter_by(game_id=one_game).all()
        if "joined team" in t.message
    ]
    assert len(join_messages) == 1


def test_join_game_rescan_of_different_code_moves(
    api_client, db_session, one_game, team_factory
):
    user_id = scanner_id(api_client)
    team_a = team_factory()
    team_b = team_factory()
    other_slot = SCHEME.usable_slots()[1]

    assert join_via_api(api_client, one_game, team_a, SLOT).is_success
    assert join_via_api(api_client, one_game, team_b, other_slot).is_success

    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id == team_b
    assert user.identity_slot == other_slot


def test_join_game_occupied_slot_400_and_joins_nothing(
    api_client, db_session, one_game, one_team, user_factory
):
    holder = user_factory()
    UserInterface(holder).join_team(one_team)
    set_identity_raw(db_session, holder, SLOT)

    user_id = scanner_id(api_client)
    response = join_via_api(api_client, one_game, one_team, SLOT)

    assert response.status_code == 400
    assert "already used" in response.json()["detail"]

    # Atomicity: the loser is left exactly as they were - no team, no slot
    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id is None
    assert user.identity_slot is None


def test_join_game_override_collision_400_and_joins_nothing(
    api_client, db_session, one_game, one_team, user_factory
):
    # Player B holds slot 2 but is overridden onto slot 1's exact canonical
    # outfit (see test_admin_identity.test_report_pairs_and_levels), so slot 1
    # is rendered unusable even though nobody holds it.
    holder = user_factory()
    UserInterface(holder).join_team(one_team)
    set_identity_raw(
        db_session,
        holder,
        2,
        overrides=dict(SCHEME.appearance_of_slot(1)),
    )

    user_id = scanner_id(api_client)
    response = join_via_api(api_client, one_game, one_team, 1)

    assert response.status_code == 400
    assert "identical outfit" in response.json()["detail"]

    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id is None
    assert user.identity_slot is None


def test_join_game_bad_signature_403(api_client, one_game, one_team):
    code = JoinCodeModel(game_id=one_game, team_id=one_team, slot=SLOT).sign()
    code.slot = SCHEME.usable_slots()[1]  # tamper after signing

    response = api_client.post("/api/join_game", json={"data": code.to_base64()})

    assert response.status_code == 403


def test_join_game_malformed_400(api_client, db_session):
    assert (
        api_client.post("/api/join_game", json={"data": "not-valid-b64!!"}).status_code
        == 400
    )
    # A URL with no join code in it
    assert (
        api_client.post(
            "/api/join_game", json={"data": "https://example.com/?d=whatever"}
        ).status_code
        == 400
    )


def test_join_game_unknown_game_404(api_client, db_session, one_team):
    response = join_via_api(api_client, get_uuid(), one_team, SLOT)
    assert response.status_code == 404


def test_join_game_unknown_team_404(api_client, db_session, one_game):
    response = join_via_api(api_client, one_game, get_uuid(), SLOT)
    assert response.status_code == 404


def test_join_game_cross_game_team_400(api_client, db_session, one_game, game_factory):
    other_game = game_factory()
    other_team = Team(name="interlopers", game_id=other_game)
    db_session.add(other_team)
    db_session.commit()

    # A validly-signed code whose team belongs to a different game
    response = join_via_api(api_client, one_game, other_team.id, SLOT)

    assert response.status_code == 400


def test_join_game_slot_zero_400(api_client, db_session, one_game, one_team):
    user_id = scanner_id(api_client)

    response = join_via_api(api_client, one_game, one_team, 0)

    assert response.status_code == 400
    db_session.expire_all()
    assert db_session.get(User, user_id).team_id is None


def test_join_game_team_code_needs_pick_and_writes_nothing(
    api_client, db_session, one_game, one_team
):
    user_id = scanner_id(api_client)

    response = api_client.post(
        "/api/join_game",
        json={"data": make_team_join_url(one_game, one_team)},
    )

    assert response.is_success
    data = response.json()
    assert data["needs_pick"] is True
    assert UUID(data["team_id"]) == one_team

    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id is None
    assert user.identity_slot is None


# ---------------------------------------------------------------------------
# admin_add_user_to_team slot picker
# ---------------------------------------------------------------------------


def test_admin_add_user_to_team_with_slot(
    admin_api_client, db_session, one_game, one_team, user_factory
):
    user_id = user_factory()

    response = admin_api_client.post(
        f"/api/admin_add_user_to_team?user_id={user_id}&team_id={one_team}&slot={SLOT}"
    )

    assert response.is_success
    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id == one_team
    assert user.identity_slot == SLOT


def test_admin_add_user_to_team_without_slot(
    admin_api_client, db_session, one_game, one_team, user_factory
):
    user_id = user_factory()

    response = admin_api_client.post(
        f"/api/admin_add_user_to_team?user_id={user_id}&team_id={one_team}"
    )

    assert response.is_success
    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id == one_team
    assert user.identity_slot is None


def test_admin_add_user_to_team_occupied_slot_400_but_user_in_team(
    admin_api_client, db_session, one_game, one_team, user_factory
):
    holder = user_factory()
    UserInterface(holder).join_team(one_team)
    set_identity_raw(db_session, holder, SLOT)

    user_id = user_factory()
    response = admin_api_client.post(
        f"/api/admin_add_user_to_team?user_id={user_id}&team_id={one_team}&slot={SLOT}"
    )

    # Not atomic by design: the join committed before the slot was rejected
    assert response.status_code == 400
    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id == one_team
    assert user.identity_slot is None


# ---------------------------------------------------------------------------
# admin_join_qr_codes
# ---------------------------------------------------------------------------


def test_admin_join_qr_codes_one_code_per_team_distinct_colours(
    admin_api_client, db_session, one_game, team_factory
):
    team_a = team_factory()
    team_b = team_factory()

    response = admin_api_client.get(f"/api/admin_join_qr_codes?game_id={one_game}")

    assert response.is_success
    body = response.json()
    assert body["team_channel"] == TEAM_CHANNEL

    teams = body["teams"]
    assert {UUID(t["team_id"]) for t in teams} == {team_a, team_b}

    colours = []
    for team in teams:
        # Exactly one code per team, decoding to a signed team code (no slot)
        code = JoinCodeModel.from_base64(team["encoded_url"])
        assert code.validate_signature() is None
        assert code.game_id == one_game
        assert code.team_id == UUID(team["team_id"])
        assert code.slot is None

        assert team["team_colour_hex"] == hex_for(TEAM_CHANNEL, team["team_colour"])
        assert team["capacity"] > 0
        colours.append(team["team_colour"])

    # No two teams share a hat colour
    assert len(set(colours)) == 2

    # And the colours were actually pinned to the teams in the database
    db_session.expire_all()
    stored = {db_session.get(Team, t).identity_colour for t in (team_a, team_b)}
    assert stored == set(colours)


def test_admin_join_qr_codes_regenerating_after_new_team_keeps_existing_colours(
    admin_api_client, db_session, one_game, team_factory
):
    team_a = team_factory()
    team_b = team_factory()

    first = admin_api_client.get(f"/api/admin_join_qr_codes?game_id={one_game}").json()
    colour_by_team = {UUID(t["team_id"]): t["team_colour"] for t in first["teams"]}

    team_c = team_factory()

    second = admin_api_client.get(f"/api/admin_join_qr_codes?game_id={one_game}").json()
    second_by_team = {UUID(t["team_id"]): t["team_colour"] for t in second["teams"]}

    # The original two teams' colours - and therefore their printed codes -
    # are byte-identical after adding a third team and regenerating.
    assert second_by_team[team_a] == colour_by_team[team_a]
    assert second_by_team[team_b] == colour_by_team[team_b]
    assert second_by_team[team_c] not in {
        colour_by_team[team_a],
        colour_by_team[team_b],
    }


def test_admin_join_qr_codes_more_teams_than_colours_400(
    admin_api_client, db_session, one_game, team_factory
):
    num_colours = len(colour_capacity(default_scheme(), TEAM_CHANNEL))
    for _ in range(num_colours + 1):
        team_factory()

    response = admin_api_client.get(f"/api/admin_join_qr_codes?game_id={one_game}")

    assert response.status_code == 400


def test_admin_join_qr_codes_no_teams_400(admin_api_client, db_session, one_game):
    response = admin_api_client.get(f"/api/admin_join_qr_codes?game_id={one_game}")
    assert response.status_code == 400


def test_admin_join_qr_codes_requires_admin_auth(api_client, one_game):
    response = api_client.get(f"/api/admin_join_qr_codes?game_id={one_game}")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# admin_delete_user
# ---------------------------------------------------------------------------


def test_admin_delete_user(
    admin_api_client, db_session, two_users_in_different_teams, test_image_string
):
    from backend.admin_interface import AdminInterface
    from backend.items import ItemModel

    user_a, user_b = two_users_in_different_teams

    # A collects an item and fires a shot
    item = ItemModel(
        id=get_uuid(),
        itype="ammo",
        data={"num": 3},
        collected_only_once=True,
        collected_as_team=False,
    ).sign()
    UserInterface(user_a).collect_item(item.to_base64())
    UserInterface(user_a).set_weapon_data(1, 6)
    UserInterface(user_a).submit_shot(test_image_string)

    # B shoots A, and the admin validates the hit (so B's shot targets A)
    UserInterface(user_b).award_ammo(1)
    UserInterface(user_b).set_weapon_data(1, 6)
    shot_b = UserInterface(user_b).submit_shot(test_image_string)
    AdminInterface().hit_user(shot_b, user_a)

    response = admin_api_client.post(f"/api/admin_delete_user?user_id={user_a}")
    assert response.is_success

    db_session.expire_all()

    # The user, their shots and their items are all gone
    assert db_session.get(User, user_a) is None
    assert db_session.query(Shot).filter_by(user_id=user_a).count() == 0
    assert db_session.get(Item, item.id) is None

    # The shot that hit them survives as anonymous history
    remaining = db_session.get(Shot, shot_b)
    assert remaining is not None
    assert remaining.target_user_id is None
    assert remaining.checked
    assert remaining.result == "hit"

    # B is untouched
    assert db_session.get(User, user_b) is not None


def test_admin_delete_user_unknown_404(admin_api_client, db_session):
    response = admin_api_client.post(f"/api/admin_delete_user?user_id={get_uuid()}")
    assert response.status_code == 404
