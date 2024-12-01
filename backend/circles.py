import asyncio
import logging

from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event

logger = logging.getLogger(__name__)


def trigger_circle_update(game_id):
    """
    Trigger an update event for the circles in this game
    """
    trigger_update_event("circle", game_id)


async def generate_circle_updates(game_id, timeout=None):
    """
    A generator that yields None every time an update is available for the
    circles in this game, or at most after timeout seconds

    Does not block the database session.
    """
    while True:
        # Lookup / make an event for this game and subscribe to it
        event = get_trigger_event("circle", game_id)

        try:
            logger.info(
                "(Circle %s) Subscribing to event %s",
                game_id,
                event,
            )
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.info("(Circle %s) Event received", game_id)
            yield
        except asyncio.TimeoutError:
            logger.info("(Circle %s) Event timeout", game_id)
            yield
