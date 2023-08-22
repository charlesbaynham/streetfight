GAME_ID = "hot-potato"
from uuid import UUID


def test_client(api_client):
    pass


def test_read_main(api_client):
    response = api_client.get("/api/hello")
    assert response.status_code == 200
    assert response.json() == {"msg": "Hello world!"}


def test_user_info(api_client):
    response = api_client.get("/api/user_info")
    assert response.status_code == 200
    # assert response.json() == {"msg": "Hello world!"}


def test_make_game(api_client):
    response = api_client.post("/api/admin_create_game")
    print(response)
    assert response.status_code == 200
    UUID(response)
