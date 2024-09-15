from enum import auto
from enum import Enum
from typing import Dict
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from .ticker import Ticker

"""
A centralized location to coordinate messages sent to tickers. This module is
the only place where ticker messages are sent, and so decides who gets them and
what they say.
"""


class TickerMessageType(Enum):
    USER_JOINED_TEAM = auto()


class TickerTarget(Enum):
    PUBLIC = auto()
    PRIVATE_USER = auto()
    PRIVATE_TEAM = auto()


TICKER_MESSAGES = {
    TickerMessageType.USER_JOINED_TEAM: (
        TickerTarget.PUBLIC,
        "{user} has joined team {team}",
    )
}


def send_ticker_message(
    message_type: TickerMessageType,
    supporting_strings: Dict[str],
    user_id: Optional[UUID] = None,
    team_id: Optional[UUID] = None,
    game_id: Optional[UUID] = None,
    session: Optional[Session] = None,
):
    """
    Sends a message to the appropriate ticker(s).

    Look up the message type in `TICKER_MESSAGES`, use the supporting strings to
    construct its message and then send it to the appropriate ticker according to
    the `TickerTarget` defined in `TICKER_MESSAGES`.

    Args:
        message_type (TickerMessageType): The type of message to send.
        supporting_strings (Dict[str, str]): A dictionary of strings to use in the message.
        user_id (Optional[UUID]): The ID of the user to send the message to.
        team_id (Optional[UUID]): The ID of the team to send the message to.
        game_id (Optional[UUID]): The ID of the game to send the message to.
        session (Optional[Session]): The database session to use.
    """

    # Get the target and message format string for the message type
    target, message_format_str = TICKER_MESSAGES[message_type]

    try:
        formatted_msg = message_format_str.format(**supporting_strings)
    except KeyError:
        raise ValueError(
            f"Missing values in format string for message type {message_type}"
        )

    if target == TickerTarget.PUBLIC:
        if not game_id:
            raise ValueError("Game ID required for public ticker messages")

        Ticker(game_id, user_id=None, session=session).post_message(
            message=formatted_msg
        )
    elif target == TickerTarget.PRIVATE_USER:
        if not game_id:
            raise ValueError("Game ID required for public ticker messages")
        if not user_id:
            raise ValueError("User ID required for private user ticker messages")

        Ticker(game_id, user_id=user_id, session=session).post_message(
            message=formatted_msg, private_for_user_id=user_id
        )
    elif target == TickerTarget.PRIVATE_TEAM:
        raise NotImplementedError("Private team messages not yet implemented")
    else:
        raise ValueError(f"Unknown ticker target {target}")
