import asyncio
import logging
from typing import List
from uuid import UUID

from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event
from .database_scope_provider import DatabaseScopeProvider
from .model import Game
from .model import TickerEntry

logger = logging.getLogger(__name__)


TickerScopeWrapper = DatabaseScopeProvider(
    "ticker",
    precommit_method=lambda ticker: ticker.touch_game_ticker_tag(),
    postcommit_method=lambda ticker: trigger_update_event("ticker", ticker.game_id),
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
        self._session = session

    @db_scoped
    def get_messages(self, num_messages) -> List[str]:
        """
        Gets the latest n messages for this game and user

        Args:
            n_entries (int): Number of messages to get

        Returns:
            List[str]: Messages
        """
        ticker_entries = (
            self._session.query(TickerEntry)
            .filter_by(game_id=self.game_id)
            .order_by(TickerEntry.id.desc())
            .limit(num_messages)
            .all()
        )

        logger.debug(
            "(Game Ticker %s) Looked up %d ticker entries",
            self.game_id,
            len(ticker_entries),
        )

        return [t.message for t in ticker_entries]

    @db_scoped
    def _get_game(self) -> Game:
        return self._session.query(Game).get(self.game_id)

    @db_scoped
    def touch_game_ticker_tag(self):
        logger.debug("(Game Ticker %s) Touching ticker", self.game_id)
        self._get_game().touch()

    @db_scoped
    def post_message(self, message: str, private_for_user_id: UUID = None):
        """Post a message to this game's ticker

        Args:
            message (str):  The ticker message
            private_for_user_id (UUID, optional):
                            If provided, the message will be
                            private for this user id. Defaults to None.
        """
        logger.debug(
            '(Game Ticker %s) Adding ticker entry "%s", user_filter = %s',
            self.game_id,
            message,
            private_for_user_id,
        )
        if private_for_user_id:
            self._session.add(TickerEntry(game_id=self.game_id, message=message))
        else:
            self._session.add(TickerEntry(game_id=self.game_id, message=message))

    async def generate_updates(self, timeout=None):
        """
        A generator that yields None every time an update is available for this
        ticker, or at most after timeout seconds
        """
        while True:
            # Lookup / make an event for this user and subscribe to it
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
