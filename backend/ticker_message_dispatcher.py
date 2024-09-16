from enum import Enum
from enum import auto
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
    USER_COLLECTED_AMMO = auto()
    TEAM_COLLECTED_AMMO = auto()
    USER_COLLECTED_ARMOUR = auto()
    USER_COLLECTED_MEDPACK = auto()
    USER_COLLECTED_WEAPON = auto()
    ADMIN_HIT_USER = auto()
    ADMIN_HIT_AND_KNOCKED_OUT_USER = auto()
    ADMIN_HIT_AND_KILLED_USER = auto()
    HIT_AND_DAMAGE = auto()
    HIT_AND_KNOCKOUT = auto()
    ADMIN_GAVE_ARMOUR = auto()
    ADMIN_REVIVED_USER = auto()
    ADMIN_GAVE_AMMO = auto()


class TickerTarget(Enum):
    PUBLIC = auto()
    PRIVATE_USER = auto()
    PRIVATE_TEAM = auto()


TICKER_MESSAGES = {
    TickerMessageType.USER_JOINED_TEAM: (
        TickerTarget.PUBLIC,
        "{user} has joined team {team}",
    ),
    TickerMessageType.USER_COLLECTED_AMMO: (
        TickerTarget.PUBLIC,
        "{user} collected {num}x ammo",
    ),
    TickerMessageType.TEAM_COLLECTED_AMMO: (
        TickerTarget.PUBLIC,
        "{user} collected {num}x ammo for everyone in their team",
    ),
    TickerMessageType.USER_COLLECTED_ARMOUR: (
        TickerTarget.PUBLIC,
        "{user} collected a level {num} armour",
    ),
    TickerMessageType.USER_COLLECTED_MEDPACK: (
        TickerTarget.PUBLIC,
        "{user} was revived with a medpack!",
    ),
    TickerMessageType.USER_COLLECTED_WEAPON: (
        TickerTarget.PUBLIC,
        "{user} collected a {weapon}",
    ),
    TickerMessageType.ADMIN_HIT_USER: (
        TickerTarget.PUBLIC,
        "Admin hit {user} for {num} damage",
    ),
    TickerMessageType.ADMIN_HIT_AND_KNOCKED_OUT_USER: (
        TickerTarget.PUBLIC,
        "Admin knocked out {user}!",
    ),
    TickerMessageType.ADMIN_HIT_AND_KILLED_USER: (
        TickerTarget.PUBLIC,
        "Admin killed {user}!",
    ),
    TickerMessageType.HIT_AND_DAMAGE: (
        TickerTarget.PUBLIC,
        "{user} hit {target} for {num} damage",
    ),
    TickerMessageType.HIT_AND_KNOCKOUT: (
        TickerTarget.PUBLIC,
        "{user} killed {target}!",
    ),
    TickerMessageType.ADMIN_GAVE_ARMOUR: (
        TickerTarget.PRIVATE_USER,
        "You were given a level {num} armour!",
    ),
    TickerMessageType.ADMIN_REVIVED_USER: (
        TickerTarget.PRIVATE_USER,
        "You were revived by the admin!",
    ),
    TickerMessageType.ADMIN_GAVE_AMMO: (
        TickerTarget.PRIVATE_USER,
        "You were given {num}x ammo!",
    ),
}


assert len(TICKER_MESSAGES) == len(TickerMessageType)
assert all(m in TickerMessageType for m in TICKER_MESSAGES.keys())


def send_ticker_message(
    message_type: TickerMessageType,
    supporting_strings: Dict[str, str],
    user_id: Optional[UUID] = None,
    team_id: Optional[UUID] = None,
    game_id: Optional[UUID] = None,
    session: Optional[Session] = None,
    highlight_user_id: Optional[UUID] = None,
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
            message=formatted_msg, highlight_user_id=highlight_user_id
        )
    elif target == TickerTarget.PRIVATE_USER:
        if not game_id:
            raise ValueError("Game ID required for public ticker messages")
        if not user_id:
            raise ValueError("User ID required for private user ticker messages")

        Ticker(game_id, user_id=user_id, session=session).post_message(
            message=formatted_msg,
            private_for_user_id=user_id,
            highlight_user_id=highlight_user_id,
        )
    elif target == TickerTarget.PRIVATE_TEAM:
        raise NotImplementedError("Private team messages not yet implemented")
    else:
        raise ValueError(f"Unknown ticker target {target}")
