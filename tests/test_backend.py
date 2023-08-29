from uuid import UUID
import pytest
from backend.model import UserModel


def test_client(api_client):
    pass


def test_read_main(api_client):
    response = api_client.get("/api/hello")
    assert response.status_code == 200
    assert response.json() == {"msg": "Hello world!"}


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
    game_name = "A new game"

    response_team = api_client.post(
        f"/api/admin_create_team?game_id={game_id}&team_name={game_name}"
    )

    print(response_team)
    print(response_team.json())

    assert response_team.status_code == 200
    assert UUID(response_team.json())


def test_username_starts_empty(api_client):
    user_info = UserModel(**api_client.get("/api/user_info").json())
    assert user_info.name is None


def test_can_set_username(api_client):
    this_user_name = "Stinky Smelly"
    api_client.post(f"/api/set_name?name={this_user_name}")

    user_info = UserModel(**api_client.get("/api/user_info").json())
    assert user_info.name == this_user_name


@pytest.fixture
def three_users(api_client):
    import random

    names = [
        "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10)) for _ in range(3)
    ]
    ids = []
    for name in names:
        ids.append(api_client.get(f"/api/my_id").json())
        api_client.post(f"/api/set_name?name={name}")

    return ids


def test_get_users(api_client, three_users):
    response = api_client.get(f"/api/get_users")
    assert response.ok
    all_users = response.json()

    retrieved_ids = [str(UserModel(**user).id) for user in all_users]
    for retrieved_id in retrieved_ids:
        assert retrieved_id in three_users
    for id in three_users:
        assert id in retrieved_ids
