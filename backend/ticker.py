import asyncio
import logging
from typing import List
from typing import Tuple
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event
from .database_scope_provider import DatabaseScopeProvider
from .model import Game
from .model import TickerEntry

logger = logging.getLogger(__name__)


def trigger_ticker_update_event(ticker: "Ticker"):
    logger.debug("Triggering update for game ticker %s", ticker.game_id)
    trigger_update_event("ticker", ticker.game_id)


TickerScopeWrapper = DatabaseScopeProvider(
    "ticker",
    precommit_method=lambda ticker: ticker.touch_game_ticker_tag(),
    postcommit_method=trigger_ticker_update_event,
)


db_scoped = TickerScopeWrapper.db_scoped


class Ticker:
    def __init__(self, game_id: UUID, user_id: UUID, session=None) -> None:
        """
        Make a new ticker for a game / user

        If user_id is set, access all public messages + private ones for this user
        If user_id = None, access only the public messages
        """
        self.game_id = game_id
        self.user_id = user_id
        self._session: Session = session

    @db_scoped
    def get_messages(self, num_messages, newest_first=True) -> List[Tuple[str, str]]:
        """
        Retrieve a list of messages from the ticker entries for the current game.
        Args:
            num_messages (int): The number of messages to retrieve.
            newest_first (bool): If True, retrieve the newest messages first. Defaults to True.
        Returns:
            List[Tuple[str,str]]: A list of messages, each as a tuple of (type, message)
        """
        if newest_first:
            order = TickerEntry.id.desc()
        else:
            order = TickerEntry.id.asc()

        ticker_entries = (
            self._session.query(
                TickerEntry.private_user_id,
                TickerEntry.highlight_user_id,
                TickerEntry.message,
            )
            .filter_by(game_id=self.game_id)
            .filter(
                or_(
                    TickerEntry.private_user_id == self.user_id,
                    TickerEntry.private_user_id == None,
                )
            )
            .order_by(order)
            .limit(num_messages)
            .all()
        )

        logger.debug(
            "(Game Ticker %s) Looked up %d ticker entries",
            self.game_id,
            len(ticker_entries),
        )

        out = []
        for private_user_id, highlight_user_id, message in ticker_entries:
            message_class = "public"

            if private_user_id:
                message_class = "user"

            if highlight_user_id == self.user_id:
                message_class = "highlight"

            out.append((message_class, message))

        return out

    @db_scoped
    def _get_game(self) -> Game:
        return self._session.query(Game).get(self.game_id)

    @db_scoped
    def touch_game_ticker_tag(self):
        logger.info("(Game Ticker %s) Touching ticker", self.game_id)
        self._get_game().touch()

    @db_scoped
    def post_message(
        self,
        message: str,
        private_for_user_id: UUID = None,
        highlight_user_id: UUID = None,
    ):
        """Post a message to this game's ticker

        Args:
            message (str):  The ticker message
            private_for_user_id (UUID, optional):
                            If provided, the message will be
                            private for this user id. Defaults to None.
            highlight_user_id (UUID, optional):
                            If provided, the message will be
                            highlighted for this user id. Defaults to None.
        """
        logger.debug(
            '(Game Ticker %s) Adding ticker entry "%s", user_filter = %s',
            self.game_id,
            message,
            private_for_user_id,
        )

        self._session.add(
            TickerEntry(
                game_id=self.game_id,
                message=message,
                private_user_id=private_for_user_id,
                highlight_user_id=highlight_user_id,
            )
        )

    async def generate_updates(self, timeout=None):
        """
        A generator that yields None every time an update is available for this
        ticker, or at most after timeout seconds

        Does not block the database session.
        """
        while True:
            # Lookup / make an event for this game and subscribe to it
            event = get_trigger_event("ticker", self.game_id)

            try:
                logger.info(
                    "(Game Ticker %s) Subscribing to event %s",
                    self.game_id,
                    event,
                )
                await asyncio.wait_for(event.wait(), timeout=timeout)
                logger.info("(Game Ticker %s) Event received", self.game_id)
                yield
            except asyncio.TimeoutError:
                logger.info("(Game Ticker %s) Event timeout", self.game_id)
                yield
