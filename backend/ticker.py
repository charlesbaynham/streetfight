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

GET_HASH_TIMEOUT = 20

TickerScopeWrapper = DatabaseScopeProvider(
    "ticker",
    precommit_method=lambda ticker: ticker.touch_game_ticker_tag(),
    postcommit_method=lambda ticker: trigger_update_event("ticker", ticker.game_id),
)


db_scoped = TickerScopeWrapper.db_scoped


class Ticker:
    def __init__(self, game_id: UUID, session=None) -> None:
        self.game_id = game_id
        self._session = session

    @db_scoped
    def get_messages(self, num_messages) -> List[str]:
        """Gets the latest n messages for this game

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
            "Looked up %d ticker entries for game %s", len(ticker_entries), self.game_id
        )

        return [t.message for t in ticker_entries]

    @db_scoped
    def _get_game(self) -> Game:
        return self._session.query(Game).get(self.game_id)

    @db_scoped
    def touch_game_ticker_tag(self):
        self._get_game().touch()

    @db_scoped
    def post_message(self, message: str):
        logger.info('Adding ticker entry "%s" to game %s', message, self.game_id)
        self._session.add(TickerEntry(game_id=self.game_id, message=message))

    @db_scoped
    def _get_hash_now(self) -> int:
        ret = self._get_game().ticker_update_tag
        logger.debug(
            f"Ticker _get_hash_now - Current hash {ret}, game_id {self.game_id}"
        )
        return ret

    async def get_hash(self, known_hash=None, timeout=GET_HASH_TIMEOUT) -> int:
        """
        Gets the latest hash of this game

        If known_hash is provided and is the same as the current hash,
        do not return immediately: wait for up to timeout seconds.

        Note that this function is not @db_scoped, but it calls one that is:
        this is to prevent the database being locked while it waits
        """
        current_hash = self._get_hash_now()

        # Return immediately if the hash has changed or if there's no known hash
        if known_hash is None or known_hash != current_hash:
            logger.debug(
                "Out of date hash (%s instead of %s) - returning immediately",
                known_hash,
                current_hash,
            )
            return current_hash

        # Otherwise, lookup / make an event and subscribe to it
        event = get_trigger_event("ticker", self.game_id)

        try:
            logger.info("Subscribing to event %s for game %s", event, self.game_id)
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.info(f"Event received for game {self.game_id}")
            return self._get_hash_now()
        except asyncio.TimeoutError:
            logger.info(f"Event timeout for game ticker {self.game_id}")
            return current_hash

    async def generate_updates(self, timeout=GET_HASH_TIMEOUT):
        """
        A generator that yields None every time an update is available for this
        ticker, or at most after timeout seconds
        """
        while True:
            # Lookup / make an event for this user and subscribe to it
            event = get_trigger_event("ticker", self.game_id)

            try:
                logger.info(
                    "Subscribing to event %s for game ticker %s", event, self.game_id
                )
                await asyncio.wait_for(event.wait(), timeout=timeout)
                logger.info(f"Event received for game ticker {self.game_id}")
                yield
            except asyncio.TimeoutError:
                logger.info(f"Event timeout for game ticker {self.game_id}")
                yield
