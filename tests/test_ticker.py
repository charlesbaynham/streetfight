import time

import pytest

from backend.admin_interface import AdminInterface
from backend.model import Shot
from backend.ticker import Ticker
from backend.user_interface import UserInterface


@pytest.fixture
def ticker(user_factory, game_factory) -> Ticker:
    return Ticker(game_id=game_factory(), user_id=user_factory())


@pytest.fixture
def ticker_for_user_in_game(api_user_id, team_factory):
    team_id = team_factory()
    AdminInterface().add_user_to_team(api_user_id, team_id)

    user_model = UserInterface(api_user_id).get_user_model()

    return Ticker(game_id=user_model.game_id, user_id=None)


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


def test_api_query_ticker_outside_team(api_client):
    response = api_client.get("/api/ticker_messages")
    assert response.is_success
    messages = response.json()

    assert messages == []


def test_user_sees_own_private_messages(ticker_for_user_in_game: Ticker):
    msg = "Hello world"
    user_id = ticker_for_user_in_game.user_id

    initial_messages = ticker_for_user_in_game.get_messages(10)

    ticker_for_user_in_game.post_message(message=msg, private_for_user_id=user_id)

    later_messages = ticker_for_user_in_game.get_messages(10)

    assert len(later_messages) == 1 + len(initial_messages)
    assert msg in later_messages
    assert later_messages[0] == msg


def test_user_doesnt_see_others_private_messages(
    user_factory, ticker_for_user_in_game: Ticker
):
    msg = "Hello world"

    user_id_alt = user_factory()

    initial_messages = ticker_for_user_in_game.get_messages(10)

    ticker_for_user_in_game.post_message(message=msg, private_for_user_id=user_id_alt)

    later_messages = ticker_for_user_in_game.get_messages(10)

    assert len(initial_messages) == len(later_messages)


def test_api_query_ticker_inside_team(api_client, ticker_for_user_in_game):
    response = api_client.get("/api/ticker_messages")
    assert response.is_success
    messages = response.json()

    assert len(messages) == 1  # Just the "joined team" message


def test_api_query_ticker_messages(api_client, ticker_for_user_in_game):
    ticker_for_user_in_game.post_message("hello")

    response = api_client.get("/api/ticker_messages")
    assert response.is_success
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
    assert response.is_success

    response = api_client.get("/api/ticker_messages")
    assert response.is_success
    messages = response.json()

    assert "killed" in messages[0]


def test_get_messages_empty(ticker):
    assert ticker.get_messages(3) == []


def test_get_messages_single_message(ticker):
    ticker.post_message("Test message")
    assert ticker.get_messages(1) == ["Test message"]


def test_get_messages_multiple_messages(ticker):
    messages = ["Message 1", "Message 2", "Message 3"]
    for msg in messages:
        ticker.post_message(msg)
    assert ticker.get_messages(3) == messages[::-1]


def test_get_messages_limit(ticker):
    messages = ["Message 1", "Message 2", "Message 3", "Message 4"]
    for msg in messages:
        ticker.post_message(msg)
    assert ticker.get_messages(2) == messages[-1:-3:-1]


def test_get_messages_order_newest_first(ticker):
    messages = ["Message 1", "Message 2", "Message 3"]
    for msg in messages:
        ticker.post_message(msg)
    assert ticker.get_messages(3, newest_first=True) == messages[::-1]


def test_get_messages_order_oldest_first(ticker):
    messages = ["Message 1", "Message 2", "Message 3"]
    for msg in messages:
        ticker.post_message(msg)
    assert ticker.get_messages(3, newest_first=False) == messages


def test_get_messages_private_messages(ticker, user_factory):
    user_id = user_factory()
    ticker.post_message("Public message")
    ticker.post_message("Private message", private_for_user_id=user_id)
    ticker.user_id = user_id
    assert ticker.get_messages(2) == ["Private message", "Public message"]


def test_get_messages_excludes_others_private_messages(ticker, user_factory):
    user_id = user_factory()
    ticker.post_message("Public message")
    ticker.post_message("Private message", private_for_user_id=user_id)
    assert ticker.get_messages(2) == ["Public message"]
