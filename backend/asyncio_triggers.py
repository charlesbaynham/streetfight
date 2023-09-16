import asyncio
import logging
from threading import RLock
from typing import Dict
from uuid import UUID


logger = logging.getLogger(__name__)


update_events: Dict[int, asyncio.Event] = {}

make_user_lock = RLock()


def trigger_update_event(user_id: UUID):
    global update_events

    logger.info(f"Triggering updates for user {user_id}")
    logger.debug(f"update_events = %s, user_id=%s", update_events, user_id)

    if user_id in update_events:
        logger.debug("Update event found")
        update_events[user_id].set()
        del update_events[user_id]
    else:
        logger.debug("No update event found")


def get_user_trigger_event(user_id: UUID) -> asyncio.Event:
    """Get a trigger event for this user which will fire when this user changes

    Args:
        user_id (UUID): User ID

    Returns:
        asyncio.Event: ASyncio event
    """

    # Otherwise, lookup / make an event and subscribe to it
    if user_id not in update_events:
        update_events[user_id] = asyncio.Event()
        logger.info("Made new event for user %s", user_id)

    return update_events[user_id]
