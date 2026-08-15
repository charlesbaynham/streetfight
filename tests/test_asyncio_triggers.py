"""Tests for the asyncio trigger registry.

The interesting one is that a scheduled event survives until it fires: asyncio
only keeps a weak reference to a running task, so the module has to hold its own
strong reference or the update can vanish part way through its sleep.
"""

import asyncio
import gc

import pytest

from backend import asyncio_triggers


@pytest.fixture(autouse=True)
def clean_registry():
    asyncio_triggers._scheduled_tasks.clear()
    asyncio_triggers._update_events.clear()
    yield
    asyncio_triggers._scheduled_tasks.clear()
    asyncio_triggers._update_events.clear()


@pytest.mark.asyncio
async def test_scheduled_task_is_strongly_referenced():
    asyncio_triggers.schedule_update_event("test_type", "test_key", timeout=10)

    assert len(asyncio_triggers._scheduled_tasks) == 1

    # Don't leave a 10 second sleep running for the rest of the session
    for task in list(asyncio_triggers._scheduled_tasks):
        task.cancel()


@pytest.mark.asyncio
async def test_scheduled_event_fires_after_a_collection():
    event = asyncio_triggers.get_trigger_event("test_type", "test_key")

    asyncio_triggers.schedule_update_event("test_type", "test_key", timeout=0.01)

    # Nothing in this test holds the task, so a collection here is exactly the
    # situation the strong reference exists to survive
    gc.collect()

    await asyncio.wait_for(event.wait(), timeout=5)


@pytest.mark.asyncio
async def test_scheduled_task_is_released_once_it_has_fired():
    event = asyncio_triggers.get_trigger_event("test_type", "test_key")
    asyncio_triggers.schedule_update_event("test_type", "test_key", timeout=0.01)

    await asyncio.wait_for(event.wait(), timeout=5)

    # The done callback runs on the next loop iteration
    await asyncio.sleep(0)

    assert not asyncio_triggers._scheduled_tasks
