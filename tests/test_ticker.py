import time

import pytest

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
