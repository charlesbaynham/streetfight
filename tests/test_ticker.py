import time

import pytest

from backend.admin_interface import AdminInterface
from backend.model import Shot
from backend.ticker import Ticker
from backend.user_interface import UserInterface


@pytest.fixture
def ticker(game_factory) -> Ticker:
    return Ticker(game_id=game_factory())


def test_ticker_starts_empty(ticker):
    assert ticker.get_messages(3) == []


def test_ticker_can_be_filled(ticker):
    ticker.post_message("hello world")
    assert ticker.get_messages(3) == ["hello world"]


def test_ticker_filters_correctly_len(ticker):
    for _ in range(10):
        ticker.post_message("test")

    assert len(ticker.get_messages(3)) == 3


def test_ticker_filters_correctly_order(ticker):
    for i in range(10):
        ticker.post_message(str(i))
        time.sleep(0.01)

    assert ticker.get_messages(3) == ["9", "8", "7"]


@pytest.mark.asyncio
async def test_ticker_messages_via_user_outside_team(user_factory):
    ticker = UserInterface(user_factory()).get_ticker()
    assert ticker is None


def test_api_query_ticker_outside_team(api_client):
    response = api_client.get("/api/ticker_messages")
    assert response.ok
    messages = response.json()

    assert messages == []


def test_api_query_ticker_inside_team(api_client, api_user_id, team_factory):
    team_id = team_factory()
    AdminInterface().add_user_to_team(api_user_id, team_id)

    response = api_client.get("/api/ticker_messages")
    assert response.ok
    messages = response.json()

    assert len(messages) == 1  # Just the "joined team" message


def test_api_query_ticker_messages(api_client, api_user_id, team_factory):
    team_id = team_factory()
    AdminInterface().add_user_to_team(api_user_id, team_id)

    UserInterface(api_user_id).get_ticker().post_message("hello")

    response = api_client.get("/api/ticker_messages")
    assert response.ok
    messages = response.json()

    assert len(messages) == 2
    assert "hello" in messages


def test_ticker_announces_kill(
    db_session, api_client, api_user_id, team_factory, test_image_string
):
    UserInterface(api_user_id).join_team(team_factory())
    UserInterface(api_user_id).award_ammo(1)
    UserInterface(api_user_id).submit_shot(test_image_string)
    shot_a = db_session.query(Shot.id).order_by(Shot.id.desc()).first()[0]
    # Let's say the user shot themselves:
    response = api_client.post(
        f"/api/admin_shot_hit_user?shot_id={shot_a}&target_user_id={api_user_id}"
    )
    assert response.ok

    response = api_client.get("/api/ticker_messages")
    assert response.ok
    messages = response.json()

    assert "killed" in messages[0]
