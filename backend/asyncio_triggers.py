import asyncio
import logging
from typing import Dict
from typing import Hashable

logger = logging.getLogger(__name__)


_update_events: Dict[str, Dict[Hashable, asyncio.Event]] = {}
_scheduled_tasks = set()


def trigger_update_event(event_type: str, key: Hashable):
    global _update_events

    logger.info(
        "(asyncio_triggers) Triggering updates for type %s, key %s", event_type, key
    )

    if event_type not in _update_events:
        _update_events[event_type] = dict()

    these_events = _update_events[event_type]

    if key in these_events:
        logger.debug("Update event found - triggering")
        these_events[key].set()
        del these_events[key]
    else:
        logger.debug("No update event found - not triggering")


def schedule_update_event(event_type: str, key: Hashable, timeout: float):
    """Schedule an update event to happen after a timeout

    Currently there is no way to cancel these. That's fine - it just means an
    extra update of user state.
    """
    global _scheduled_tasks

    logger.info(
        "(asyncio_triggers) Scheduling an update for type %s, key %s in %s seconds",
        event_type,
        key,
        timeout,
    )

    async def wait_then_trigger():
        await asyncio.sleep(timeout)
        logger.debug(
            "Triggering scheduled update event (type %s, key %s, %s seconds)",
            event_type,
            key,
            timeout,
        )
        trigger_update_event(event_type=event_type, key=key)

    task = asyncio.create_task(wait_then_trigger())
    task.add_done_callback(_scheduled_tasks.discard)


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

    logger.debug("(asyncio_triggers) Get event for type %s, key %s", event_type, key)

    if event_type not in _update_events:
        _update_events[event_type] = dict()

    these_events = _update_events[event_type]

    if key not in these_events:
        these_events[key] = asyncio.Event()
        logger.info("Made new event for type %s, key %s", event_type, key)

    return these_events[key]
