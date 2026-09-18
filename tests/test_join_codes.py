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
from backend.join_codes import make_game_join_url
from backend.join_codes import make_join_url
from backend.join_codes import make_team_join_url
from backend.model import Game
from backend.model import Item
from backend.model import Shot
from backend.model import Team
from backend.model import TickerEntry
from backend.model import User
from backend.qr_signing import sign_payload
from backend.user_interface import UserInterface

from .shared_fixtures import NO_FIRE_DELAY

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


def test_game_join_code_roundtrip_and_tamper():
    game_id = get_uuid()
    url = make_game_join_url(game_id)

    decoded = JoinCodeModel.from_base64(url)
    assert decoded.game_id == game_id
    assert decoded.team_id is None
    assert decoded.slot is None
    assert decoded.validate_signature() is None

    # A game code can't be turned into a team code by naming a team, nor a
    # team code into a game code by dropping its team.
    forged = decoded.model_copy()
    forged.team_id = get_uuid()
    assert forged.validate_signature() == "Signature mismatch"

    team_code = JoinCodeModel(game_id=game_id, team_id=get_uuid(), slot=None).sign()
    assert team_code.sig != decoded.sig
    forged = team_code.model_copy()
    forged.team_id = None
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


def test_join_game_game_code_needs_pick_and_names_no_team(
    api_client, db_session, one_game
):
    user_id = scanner_id(api_client)

    response = api_client.post(
        "/api/join_game", json={"data": make_game_join_url(one_game)}
    )

    assert response.is_success
    data = response.json()
    assert data["needs_pick"] is True
    assert data["team_id"] is None
    assert data["team_name"] is None

    db_session.expire_all()
    assert db_session.get(User, user_id).game_id is None


def test_join_game_unknown_game_code_404(api_client, db_session):
    response = api_client.post(
        "/api/join_game", json={"data": make_game_join_url(get_uuid())}
    )
    assert response.status_code == 404


def signed_up(db_session, user_id, game_id, slot=SLOT):
    """A player who came through the sign-up link: an outfit in the game,
    no team (roadmap R15)."""
    user = db_session.get(User, user_id)
    user.game_id = game_id
    user.identity_slot = slot
    db_session.commit()


def join_messages(db_session, game_id):
    return [
        t.message
        for t in db_session.query(TickerEntry).filter_by(game_id=game_id).all()
        if "joined team" in t.message
    ]


def test_join_game_team_code_puts_a_signed_up_player_in_the_team_keeping_the_outfit(
    api_client, db_session, one_game, one_team
):
    """The door scan."""
    user_id = scanner_id(api_client)
    signed_up(db_session, user_id, one_game)

    response = api_client.post(
        "/api/join_game", json={"data": make_team_join_url(one_game, one_team)}
    )

    assert response.is_success
    data = response.json()
    assert data["joined"] is True
    assert "needs_pick" not in data
    assert data["slot"] == SLOT

    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id == one_team
    assert user.game_id == one_game
    assert user.identity_slot == SLOT
    assert len(join_messages(db_session, one_game)) == 1


def test_join_game_rescanning_the_same_team_is_a_no_op(
    api_client, db_session, one_game, one_team
):
    user_id = scanner_id(api_client)
    signed_up(db_session, user_id, one_game)
    url = make_team_join_url(one_game, one_team)

    assert api_client.post("/api/join_game", json={"data": url}).is_success
    again = api_client.post("/api/join_game", json={"data": url})

    assert again.is_success
    assert again.json()["joined"] is True
    db_session.expire_all()
    assert db_session.get(User, user_id).team_id == one_team
    assert len(join_messages(db_session, one_game)) == 1


def test_join_game_scanning_another_team_moves_the_player(
    api_client, db_session, one_game, team_factory
):
    """The repair for scanning the wrong card at a crowded door."""
    team_a, team_b = team_factory(), team_factory()
    user_id = scanner_id(api_client)
    signed_up(db_session, user_id, one_game)

    api_client.post(
        "/api/join_game", json={"data": make_team_join_url(one_game, team_a)}
    )
    moved = api_client.post(
        "/api/join_game", json={"data": make_team_join_url(one_game, team_b)}
    )

    assert moved.is_success
    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user.team_id == team_b
    assert user.identity_slot == SLOT
    assert len(join_messages(db_session, one_game)) == 2


def test_join_game_team_code_of_another_game_400(
    api_client, db_session, game_factory, one_game, one_team
):
    other_game = game_factory()
    user_id = scanner_id(api_client)
    signed_up(db_session, user_id, one_game)

    response = api_client.post(
        "/api/join_game", json={"data": make_team_join_url(other_game, one_team)}
    )

    assert response.status_code == 400
    db_session.expire_all()
    assert db_session.get(User, user_id).team_id is None


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
    assert user.game_id == one_game
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

    # The sign-up link: one per game, naming no team
    game_code = JoinCodeModel.from_base64(body["game_url"])
    assert game_code.validate_signature() is None
    assert game_code.game_id == one_game
    assert game_code.team_id is None
    assert game_code.slot is None

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
        colours.append(team["team_colour"])

    # No two teams share a display colour
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
    UserInterface(user_a).set_weapon_data(1, NO_FIRE_DELAY)
    UserInterface(user_a).submit_shot(test_image_string)

    # B shoots A, and the admin validates the hit (so B's shot targets A)
    UserInterface(user_b).award_ammo(1)
    UserInterface(user_b).set_weapon_data(1, NO_FIRE_DELAY)
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


# ---------------------------------------------------------------------------
# admin_delete_team
# ---------------------------------------------------------------------------


def test_admin_delete_team(
    admin_api_client, db_session, two_users_in_different_teams, test_image_string
):
    from backend.items import ItemModel

    user_a, user_b = two_users_in_different_teams
    team_a = db_session.get(User, user_a).team_id
    team_b = db_session.get(User, user_b).team_id

    # A collects an item and fires a shot from team A
    item = ItemModel(
        id=get_uuid(),
        itype="ammo",
        data={"num": 3},
        collected_only_once=True,
        collected_as_team=False,
    ).sign()
    UserInterface(user_a).collect_item(item.to_base64())
    UserInterface(user_a).set_weapon_data(1, NO_FIRE_DELAY)
    UserInterface(user_a).submit_shot(test_image_string)

    response = admin_api_client.post(f"/api/admin_delete_team?team_id={team_a}")
    assert response.is_success

    db_session.expire_all()

    # The team and its only player are gone, along with their shots and items
    assert db_session.get(Team, team_a) is None
    assert db_session.get(User, user_a) is None
    assert db_session.query(Shot).filter_by(team_id=team_a).count() == 0
    assert db_session.get(Item, item.id) is None

    # B and their team are untouched
    assert db_session.get(Team, team_b) is not None
    assert db_session.get(User, user_b) is not None


def test_admin_delete_team_removes_shots_from_players_who_switched_out(
    admin_api_client, db_session, user_in_team, team_factory, test_image_string
):
    """A shot's ``team_id`` records the team the shooter was on when they
    fired, not their current one, so it survives a later team switch. It
    should not survive its recorded team being deleted, since ``team_id`` is
    not nullable."""
    old_team_id = db_session.get(User, user_in_team).team_id

    UserInterface(user_in_team).award_ammo(1)
    UserInterface(user_in_team).set_weapon_data(1, NO_FIRE_DELAY)
    shot_id = UserInterface(user_in_team).submit_shot(test_image_string)

    new_team_id = team_factory()
    admin_api_client.post(
        f"/api/admin_add_user_to_team?user_id={user_in_team}&team_id={new_team_id}"
    )

    response = admin_api_client.post(f"/api/admin_delete_team?team_id={old_team_id}")
    assert response.is_success

    db_session.expire_all()

    assert db_session.get(Team, old_team_id) is None
    assert db_session.get(Shot, shot_id) is None

    # The player themselves is untouched - they had already left the team
    assert db_session.get(User, user_in_team) is not None
    assert db_session.get(User, user_in_team).team_id == new_team_id


def test_admin_delete_team_unknown_404(admin_api_client, db_session):
    response = admin_api_client.post(f"/api/admin_delete_team?team_id={get_uuid()}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# admin_delete_game
# ---------------------------------------------------------------------------


def test_admin_delete_game(
    admin_api_client,
    db_session,
    one_game,
    two_users_in_different_teams,
    test_image_string,
):
    from backend.items import ItemModel

    user_a, user_b = two_users_in_different_teams
    team_a = db_session.get(User, user_a).team_id
    team_b = db_session.get(User, user_b).team_id

    # A collects an item and fires a shot; a general ticker line is posted too
    item = ItemModel(
        id=get_uuid(),
        itype="ammo",
        data={"num": 3},
        collected_only_once=True,
        collected_as_team=False,
    ).sign()
    UserInterface(user_a).collect_item(item.to_base64())
    UserInterface(user_a).set_weapon_data(1, NO_FIRE_DELAY)
    UserInterface(user_a).submit_shot(test_image_string)

    admin_api_client.post(
        f"/api/admin_send_custom_ticker_message?game_id={one_game}&message=hello"
    )

    response = admin_api_client.post(f"/api/admin_delete_game?game_id={one_game}")
    assert response.is_success

    db_session.expire_all()

    # The game, both its teams and both players are gone, along with their
    # shots, items and the game's ticker
    assert db_session.get(Game, one_game) is None
    assert db_session.get(Team, team_a) is None
    assert db_session.get(Team, team_b) is None
    assert db_session.get(User, user_a) is None
    assert db_session.get(User, user_b) is None
    assert db_session.query(Shot).filter_by(game_id=one_game).count() == 0
    assert db_session.get(Item, item.id) is None
    assert db_session.query(TickerEntry).filter_by(game_id=one_game).count() == 0


def test_admin_delete_game_removes_players_who_never_joined_a_team(
    admin_api_client, db_session, one_game, user_factory
):
    """A sign-up with no team (roadmap R15) belongs to no team's cascade."""
    user_id = user_factory()
    user = db_session.get(User, user_id)
    user.game_id = one_game
    user.identity_slot = SLOT
    db_session.commit()

    response = admin_api_client.post(f"/api/admin_delete_game?game_id={one_game}")
    assert response.is_success

    db_session.expire_all()
    assert db_session.get(Game, one_game) is None
    assert db_session.get(User, user_id) is None


def test_admin_delete_game_unknown_404(admin_api_client, db_session):
    response = admin_api_client.post(f"/api/admin_delete_game?game_id={get_uuid()}")
    assert response.status_code == 404


def test_admin_delete_game_requires_admin_auth(api_client, one_game):
    response = api_client.post(f"/api/admin_delete_game?game_id={one_game}")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# admin_game_join_url
# ---------------------------------------------------------------------------


def test_admin_game_join_url_works_before_any_team_exists(admin_api_client, one_game):
    """The sign-up link is wanted days before the teams exist (R15), which is
    exactly when admin_join_qr_codes 400s."""
    response = admin_api_client.get(f"/api/admin_game_join_url?game_id={one_game}")

    assert response.is_success
    code = JoinCodeModel.from_base64(response.json()["game_url"])
    assert code.validate_signature() is None
    assert code.game_id == one_game
    assert code.team_id is None
    assert code.slot is None


def test_admin_game_join_url_leaves_team_colours_alone(
    admin_api_client, db_session, one_game, team_factory
):
    team = team_factory()

    admin_api_client.get(f"/api/admin_game_join_url?game_id={one_game}")

    db_session.expire_all()
    assert db_session.get(Team, team).identity_colour is None


def test_admin_game_join_url_unknown_game_404(admin_api_client):
    response = admin_api_client.get(f"/api/admin_game_join_url?game_id={get_uuid()}")
    assert response.status_code == 404


def test_admin_game_join_url_requires_admin_auth(api_client, one_game):
    response = api_client.get(f"/api/admin_game_join_url?game_id={one_game}")
    assert response.status_code in (401, 403)


# Reading a join code without using it (react-ui/src/AdminScanCode.js). An
# admin handed a team card off the floor needs to know which team it is for,
# and the alternative - scanning it with their own phone - moves them into
# that team.


def test_identifying_a_team_card(db_session, one_game, one_team):
    from backend.admin_interface import AdminInterface

    team_name = db_session.get(Team, one_team).name

    identified = AdminInterface().identify_code(make_team_join_url(one_game, one_team))

    assert identified["kind"] == "join"
    assert team_name in identified["headline"]
    assert identified["verdict"]["tone"] == "good"


def test_identifying_the_sign_up_link(db_session, one_game):
    from backend.admin_interface import AdminInterface

    identified = AdminInterface().identify_code(make_game_join_url(one_game))

    assert identified["headline"] == "Sign-up link"
    assert identified["verdict"]["tone"] == "good"


def test_identifying_a_join_code_for_a_game_that_is_gone(db_session):
    """The failure this page is for: a card from last time, which looks
    exactly like one from this time."""
    from backend.admin_interface import AdminInterface

    identified = AdminInterface().identify_code(make_game_join_url(get_uuid()))

    assert identified["kind"] == "join"
    assert identified["verdict"]["tone"] == "bad"
