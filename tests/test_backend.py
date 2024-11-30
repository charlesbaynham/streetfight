import os
from uuid import UUID

import pytest
from fastapi.exceptions import HTTPException

from backend.model import UserModel
from backend.user_interface import UserInterface


def test_read_main(api_client):
    response = api_client.get("/api/hello")
    assert response.status_code == 200
    assert response.json() == {"msg": "Hello world!"}


def test_auth_default_to_false(api_client):
    response = api_client.get("/api/admin_is_authed")
    assert response.status_code == 200
    assert response.json() == False


def test_auth_denies_admin(api_client):
    response = api_client.get("/api/admin_list_games")
    assert response.status_code == 403


def test_auth_can_login(api_client):
    password = os.getenv("ADMIN_PASSWORD", "password")
    response = api_client.post(f"/api/admin_authenticate?password={password}")
    assert response.status_code == 200
    response = api_client.get("/api/admin_list_games")
    assert response.status_code == 200


def test_user_info(api_client):
    response = api_client.get("/api/user_info")

    print(response)
    print(response.json())

    assert response.status_code == 200
    assert UserModel(**response.json())


def test_make_game(api_client):
    response = api_client.post("/api/admin_create_game")

    print(response)
    print(response.json())

    assert response.status_code == 200
    assert UUID(response.json())


def test_make_team(api_client):
    response_game = api_client.post("/api/admin_create_game")

    game_id = response_game.json()
    team_name = "A new team"

    response_team = api_client.post(
        f"/api/admin_create_team?game_id={game_id}&team_name={team_name}"
    )

    print(response_team)
    print(response_team.json())

    assert response_team.status_code == 200
    return UUID(response_team.json())


def test_username_starts_empty(api_client):
    user_info = UserModel(**api_client.get("/api/user_info").json())
    assert user_info.name is None


def test_can_set_username(api_client):
    this_user_name = "Stinky Smelly"
    api_client.post(f"/api/set_name?name={this_user_name}")

    user_info = UserModel(**api_client.get("/api/user_info").json())
    assert user_info.name == this_user_name


def test_get_users(api_client, three_users):
    response = api_client.get(f"/api/get_users")
    assert response.is_success
    all_users = response.json()

    retrieved_ids = [UserModel(**user).id for user in all_users]
    for retrieved_id in retrieved_ids:
        assert retrieved_id in three_users
    for id in three_users:
        assert id in retrieved_ids


def test_get_user_id(api_client):
    response = api_client.get("/api/my_id")
    assert response.is_success
    UUID(response.json())


def test_add_user_to_team(api_client, one_team, three_users):
    the_lucky_user = three_users[0]
    response = api_client.post(
        f"/api/admin_add_user_to_team?user_id={the_lucky_user}&team_id={one_team}"
    )
    assert response.is_success


@pytest.mark.parametrize("num", range(0, 3))
def test_admin_set_hp(api_client, user_in_team, num):
    api_client.post(f"/api/admin_set_hp?user_id={user_in_team}&num={num}")
    assert UserInterface(user_in_team).get_user_model().hit_points == num


@pytest.mark.parametrize("num", range(-3, 3))
def test_admin_give_ammo(api_client, user_in_team, num):
    api_client.post(f"/api/admin_give_ammo?user_id={user_in_team}&num={num}")
    assert UserInterface(user_in_team).get_user_model().num_bullets == num


def test_admin_make_item(api_client, user_in_team):
    r = api_client.post(
        "/api/admin_make_new_item?item_type=ammo",
        json={"num": 123},
    )

    encoded_item_data = r.json()

    assert encoded_item_data["itype"] == "ammo"
    assert encoded_item_data["item_data"]["num"] == 123

    encoded_item = encoded_item_data["encoded_item"]

    UserInterface(user_in_team).collect_item(encoded_item)

    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(encoded_item)
