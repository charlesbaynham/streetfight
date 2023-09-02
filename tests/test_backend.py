from uuid import UUID

import pytest

from backend.model import UserModel


@pytest.fixture
def user_factory(db_session):
    import random

    from backend.model import User

    def factory():
        name = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))
        user = User(name=name)

        db_session.add(user)
        db_session.commit()

        return user.id

    return factory


@pytest.fixture
def team_factory(db_session):
    import random

    from backend.model import Team

    def factory():
        name = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))
        team = Team(name=name)

        db_session.add(team)
        db_session.commit()

        return team.id

    return factory


@pytest.fixture
def three_users(user_factory):
    return [user_factory() for _ in range(3)]


@pytest.fixture
def one_team(team_factory):
    return team_factory()


def test_three_users(three_users):
    assert [isinstance(u, UUID) for u in three_users]


def test_one_team(one_team):
    return isinstance(one_team, UUID)


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
    assert response.ok
    all_users = response.json()

    retrieved_ids = [UserModel(**user).id for user in all_users]
    for retrieved_id in retrieved_ids:
        assert retrieved_id in three_users
    for id in three_users:
        assert id in retrieved_ids


def test_add_user_to_team(api_client, one_team, three_users):
    the_lucky_user = three_users[0]
    response = api_client.post(
        f"/api/admin_add_user_to_team?user_id={the_lucky_user}&team_id={one_team}"
    )
    assert response.ok
