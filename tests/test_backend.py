GAME_ID = "hot-potato"
from uuid import UUID
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
    assert isinstance(response_team.json(), int)
