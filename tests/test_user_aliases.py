from uuid import UUID
from uuid import uuid4 as get_uuid

import pytest

from backend.admin_interface import AdminInterface
from backend.items import ItemModel
from backend.model import Item
from backend.model import Shot
from backend.model import TickerEntry
from backend.model import User
from backend.model import UserAlias
from backend.user_interface import UserInterface


# Mock "schedule_update_event" since we don't have an asyncio loop, same as
# tests/test_admin_mode.py
@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def test_admin_merge_user(
    admin_api_client, api_client, db_session, team_factory, test_image_string
):
    # The stray session: a fresh join on a second phone, with no cookie
    # shared with the survivor
    stray_response = api_client.get("/api/my_id")
    assert stray_response.is_success
    stray_id = UUID(stray_response.json())

    # The survivor: the real player, already in a team with an identity slot
    team_id = team_factory()
    stray_team_id = team_factory()
    with UserInterface(stray_id) as ui:
        ui.set_name("Stray")
        ui.join_team(stray_team_id)

    survivor_id = get_uuid()
    with UserInterface(survivor_id) as ui:
        ui.set_name("Survivor")
        ui.join_team(team_id)
    identity_admin_slot = 3
    survivor = db_session.get(User, survivor_id)
    survivor.identity_slot = identity_admin_slot
    db_session.commit()

    # The stray fired a shot, collected an item, and picked up ammo
    item = ItemModel(
        id=get_uuid(),
        itype="ammo",
        data={"num": 3},
        collected_only_once=True,
        collected_as_team=False,
    ).sign()
    UserInterface(stray_id).collect_item(item.to_base64())
    UserInterface(stray_id).award_ammo(2)
    UserInterface(stray_id).set_weapon_data(1, 6)
    stray_shot = UserInterface(stray_id).submit_shot(test_image_string)

    # A shot fired by the survivor targeted the stray (e.g. shot before the
    # merge happened)
    UserInterface(survivor_id).award_ammo(1)
    UserInterface(survivor_id).set_weapon_data(1, 6)
    shot_at_stray = UserInterface(survivor_id).submit_shot(test_image_string)
    AdminInterface().hit_user(shot_at_stray, stray_id)

    survivor_bullets_before = db_session.get(User, survivor_id).num_bullets
    stray_bullets_before = db_session.get(User, stray_id).num_bullets

    response = admin_api_client.post(
        f"/api/admin_merge_user?user_id={stray_id}&into_user_id={survivor_id}"
    )
    assert response.is_success

    db_session.expire_all()

    # The stray session is now served as the survivor
    my_id_response = api_client.get("/api/my_id")
    assert my_id_response.is_success
    assert UUID(my_id_response.json()) == survivor_id

    user_info_response = api_client.get("/api/user_info")
    assert user_info_response.is_success
    assert user_info_response.json()["team_id"] == str(team_id)

    # The stray's own User row is gone, and an alias points at the survivor
    assert db_session.get(User, stray_id) is None
    alias = db_session.get(UserAlias, stray_id)
    assert alias is not None
    assert alias.user_id == survivor_id

    # Events merged onto the survivor
    survivor = db_session.get(User, survivor_id)
    assert survivor.num_bullets == survivor_bullets_before + stray_bullets_before
    assert survivor.identity_slot == identity_admin_slot
    assert survivor.team_id == team_id
    assert [i.id for i in survivor.items] == [item.id]

    assert db_session.get(Shot, stray_shot).user_id == survivor_id
    assert db_session.get(Shot, shot_at_stray).target_user_id == survivor_id

    # Nothing in the database still names the stray
    assert db_session.query(Shot).filter_by(user_id=stray_id).count() == 0
    assert db_session.query(Shot).filter_by(target_user_id=stray_id).count() == 0
    assert (
        db_session.query(TickerEntry).filter_by(private_user_id=stray_id).count() == 0
    )
    assert (
        db_session.query(TickerEntry).filter_by(highlight_user_id=stray_id).count() == 0
    )
    assert db_session.get(Item, item.id) is not None


def test_admin_merge_user_chained_alias(admin_api_client, db_session, user_factory):
    user_a = user_factory()
    user_b = user_factory()
    user_c = user_factory()

    # a -> b
    response = admin_api_client.post(
        f"/api/admin_merge_user?user_id={user_a}&into_user_id={user_b}"
    )
    assert response.is_success

    # merging c into a (now an alias for b) should land on b, the ultimate
    # survivor
    response = admin_api_client.post(
        f"/api/admin_merge_user?user_id={user_c}&into_user_id={user_a}"
    )
    assert response.is_success

    db_session.expire_all()

    assert db_session.get(User, user_c) is None
    alias_c = db_session.get(UserAlias, user_c)
    assert alias_c.user_id == user_b

    alias_a = db_session.get(UserAlias, user_a)
    assert alias_a.user_id == user_b


def test_admin_merge_user_self_400(admin_api_client, user_factory):
    user_id = user_factory()

    response = admin_api_client.post(
        f"/api/admin_merge_user?user_id={user_id}&into_user_id={user_id}"
    )
    assert response.status_code == 400


def test_admin_merge_user_unknown_404(admin_api_client, user_factory):
    user_id = user_factory()

    response = admin_api_client.post(
        f"/api/admin_merge_user?user_id={get_uuid()}&into_user_id={user_id}"
    )
    assert response.status_code == 404

    response = admin_api_client.post(
        f"/api/admin_merge_user?user_id={user_id}&into_user_id={get_uuid()}"
    )
    assert response.status_code == 404


def test_admin_merge_user_fills_in_what_the_survivor_lacks(
    admin_api_client, db_session, team_factory, user_factory
):
    """The other direction: the player was minted afresh on the phone they are
    now holding, so the *survivor* is the empty one and everything - team,
    slot, name - has to come across from the stray.
    """
    team_id = team_factory()

    stray_id = user_factory()
    with UserInterface(stray_id) as ui:
        ui.set_name("Stray")
        ui.join_team(team_id)
    stray = db_session.get(User, stray_id)
    stray.identity_slot = 5
    db_session.commit()

    survivor_id = user_factory()
    db_session.get(User, survivor_id).name = None
    db_session.commit()

    response = admin_api_client.post(
        f"/api/admin_merge_user?user_id={stray_id}&into_user_id={survivor_id}"
    )
    assert response.is_success

    db_session.expire_all()

    survivor = db_session.get(User, survivor_id)
    assert survivor.name == "Stray"
    assert survivor.team_id == team_id
    assert survivor.identity_slot == 5
    assert db_session.get(User, stray_id) is None
