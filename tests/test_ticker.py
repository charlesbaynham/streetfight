import time

import pytest

from backend.admin_interface import AdminInterface
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
async def test_ticker_game_hash(ticker):
    await ticker.get_hash()


@pytest.mark.asyncio
async def test_ticker_game_hash_changes(ticker):
    starting_hash = await ticker.get_hash()
    ticker.post_message("Hello")
    assert starting_hash != await ticker.get_hash()


@pytest.mark.asyncio
async def test_ticker_messages_via_user(user_in_team):
    ticker = UserInterface(user_in_team).get_ticker()

    starting_hash = await ticker.get_hash()
    ticker.post_message("Hello")
    assert starting_hash != await ticker.get_hash()


@pytest.mark.asyncio
async def test_ticker_messages_via_user_outside_team(user_factory):
    ticker = UserInterface(user_factory()).get_ticker()
    assert ticker is None


def test_api_query_ticker_outside_team(api_client):
    response = api_client.get("/api/ticker_messages")
    assert response.ok
    messages = response.json()

    response = api_client.get("/api/ticker_hash")
    assert response.ok
    new_hash = response.json()

    assert new_hash == 0
    assert messages == []


def test_api_query_ticker_inside_team(api_client, api_user_id, team_factory):
    team_id = team_factory()
    AdminInterface().add_user_to_team(api_user_id, team_id)

    response = api_client.get("/api/ticker_messages")
    assert response.ok
    messages = response.json()

    response = api_client.get("/api/ticker_hash")
    assert response.ok
    new_hash = response.json()

    assert new_hash != 0
    assert messages == []


def test_api_query_ticker_messages(api_client, api_user_id, team_factory):
    team_id = team_factory()
    AdminInterface().add_user_to_team(api_user_id, team_id)

    response = api_client.get("/api/ticker_hash")
    assert response.ok
    old_hash = response.json()

    UserInterface(api_user_id).get_ticker().post_message("hello")

    response = api_client.get("/api/ticker_messages")
    assert response.ok
    messages = response.json()

    response = api_client.get(f"/api/ticker_hash?known_ticker_hash={old_hash}")
    assert response.ok
    new_hash = response.json()

    assert new_hash != old_hash
    assert messages == ["hello"]