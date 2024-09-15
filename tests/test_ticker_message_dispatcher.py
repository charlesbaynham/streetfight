from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from backend.ticker_message_dispatcher import TICKER_MESSAGES
from backend.ticker_message_dispatcher import TickerMessageType
from backend.ticker_message_dispatcher import TickerTarget
from backend.ticker_message_dispatcher import send_ticker_message


@pytest.fixture
def mock_session():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_ticker(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("backend.ticker_message_dispatcher.Ticker", mock)
    return mock


def test_send_public_ticker_message(mock_session, mock_ticker):
    game_id = uuid4()
    supporting_strings = {"user": "Alice", "team": "Red"}

    send_ticker_message(
        message_type=TickerMessageType.USER_JOINED_TEAM,
        supporting_strings=supporting_strings,
        game_id=game_id,
        session=mock_session,
    )

    mock_ticker.assert_called_once_with(game_id, user_id=None, session=mock_session)
    mock_ticker().post_message.assert_called_once_with(
        message="Alice has joined team Red"
    )


def test_send_private_user_ticker_message(mock_session, mock_ticker):
    game_id = uuid4()
    user_id = uuid4()
    supporting_strings = {"user": "Alice", "team": "Red"}

    # Modify TICKER_MESSAGES to test private user message
    TICKER_MESSAGES[TickerMessageType.USER_JOINED_TEAM] = (
        TickerTarget.PRIVATE_USER,
        "{user} has joined team {team}",
    )

    send_ticker_message(
        message_type=TickerMessageType.USER_JOINED_TEAM,
        supporting_strings=supporting_strings,
        user_id=user_id,
        game_id=game_id,
        session=mock_session,
    )

    mock_ticker.assert_called_once_with(game_id, user_id=user_id, session=mock_session)
    mock_ticker().post_message.assert_called_once_with(
        message="Alice has joined team Red", private_for_user_id=user_id
    )


def test_send_ticker_message_missing_game_id(mock_session):
    supporting_strings = {"user": "Alice", "team": "Red"}

    with pytest.raises(ValueError, match="Game ID required for public ticker messages"):
        send_ticker_message(
            message_type=TickerMessageType.USER_JOINED_TEAM,
            supporting_strings=supporting_strings,
            session=mock_session,
        )


def test_send_ticker_message_missing_user_id(mock_session):
    game_id = uuid4()
    supporting_strings = {"user": "Alice", "team": "Red"}

    # Modify TICKER_MESSAGES to test private user message
    TICKER_MESSAGES[TickerMessageType.USER_JOINED_TEAM] = (
        TickerTarget.PRIVATE_USER,
        "{user} has joined team {team}",
    )

    with pytest.raises(
        ValueError, match="User ID required for private user ticker messages"
    ):
        send_ticker_message(
            message_type=TickerMessageType.USER_JOINED_TEAM,
            supporting_strings=supporting_strings,
            game_id=game_id,
            session=mock_session,
        )


def test_send_ticker_message_missing_format_string_value(mock_session):
    game_id = uuid4()
    supporting_strings = {"user": "Alice"}

    with pytest.raises(
        ValueError, match="Missing values in format string for message type"
    ):
        send_ticker_message(
            message_type=TickerMessageType.USER_JOINED_TEAM,
            supporting_strings=supporting_strings,
            game_id=game_id,
            session=mock_session,
        )


def test_send_private_team_ticker_message_not_implemented(mock_session):
    game_id = uuid4()
    team_id = uuid4()
    supporting_strings = {"user": "Alice", "team": "Red"}

    # Modify TICKER_MESSAGES to test private team message
    TICKER_MESSAGES[TickerMessageType.USER_JOINED_TEAM] = (
        TickerTarget.PRIVATE_TEAM,
        "{user} has joined team {team}",
    )

    with pytest.raises(
        NotImplementedError, match="Private team messages not yet implemented"
    ):
        send_ticker_message(
            message_type=TickerMessageType.USER_JOINED_TEAM,
            supporting_strings=supporting_strings,
            team_id=team_id,
            game_id=game_id,
            session=mock_session,
        )
