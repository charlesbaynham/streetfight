import asyncio
import logging
from typing import Dict
from typing import Hashable


logger = logging.getLogger(__name__)


_update_events: Dict[str, Dict[Hashable, asyncio.Event]] = {}


def trigger_update_event(event_type: str, key: Hashable):
    global _update_events

    logger.info(f"Triggering updates for type %s, key %s", event_type, key)

    if event_type not in _update_events:
        _update_events[event_type] = dict()

    these_events = _update_events[event_type]

    if key in these_events:
        logger.debug("Update event found")
        these_events[key].set()
        del these_events[key]
    else:
        logger.debug("No update event found")


def get_trigger_event(event_type: str, key: Hashable) -> asyncio.Event:
    """
    Get a trigger event for this type/key which will can be fired by
    :meth:`~.trigger_update_event`

    Args:
        event_type (str): A name to identify these events
        key (Hashable): A hashable key to look up the event

    Returns:
        asyncio.Event: ASyncio event
    """

    if event_type not in _update_events:
        _update_events[event_type] = dict()

    these_events = _update_events[event_type]

    if key not in these_events:
        these_events[key] = asyncio.Event()
        logger.info("Made new event for type %s, key %s", event_type, key)

    return these_events[key]
