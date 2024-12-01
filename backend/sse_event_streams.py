"""
sse_event_streams.py

This module provides functionality for generating Server-Sent Events (SSE) updates for users and administrators.
It includes functions to create SSE update messages, generate updates for users, and generate updates for administrators.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from .admin_interface import AdminInterface
from .user_interface import UserInterface

# How often to send keepalive messages
SSE_KEEPALIVE_TIMEOUT = 15

logger = logging.getLogger(__name__)


def make_sse_update_message(m):
    out = f"data: {m}\n\n"
    logger.debug('make_sse_update_message - "%s"', out)
    return out


async def updates_generator(user_id):
    """
    Yields SSE update prompts that should be received by a given user

    This generator just sends out bumps to prompt clients to refresh themselves.

    This is an async generator - it will collect messages from all relevant
    source for this user (including global announcements) and include keepalive
    events.
    """

    update_user = make_sse_update_message(
        json.dumps({"handler": "update_prompt", "data": "user"})
    )
    update_ticker = make_sse_update_message(
        json.dumps({"handler": "update_prompt", "data": "ticker"})
    )
    update_circles = make_sse_update_message(
        json.dumps({"handler": "update_prompt", "data": "circle"})
    )

    yield update_user
    yield update_ticker
    yield update_circles

    # An asyncio queue to pass to the generators
    queue = asyncio.Queue()

    # A function that logs a message every time an async generator yields
    async def feed_generator_to_queue(generator: AsyncGenerator, message: str) -> None:
        async for data in generator:
            logger.debug(
                'feed_generator_to_queue (UID %s) - Received message "%s" from %s',
                user_id,
                data,
                message,
            )
            await queue.put((message, data))

    # A function that yields from the queue as soon as items arrive
    async def yield_from_queue() -> AsyncGenerator:
        while True:
            msg = await asyncio.wait_for(queue.get(), timeout=None)
            logger.debug(
                "yield_from_queue (UID %s) - Yielding message %s", user_id, msg
            )
            yield msg

    # Keep track of the asyncio tasks we start for producers
    producers = []

    logger.debug("updates_generator - User updates for user %s starting", user_id)

    # Start a producer for user events:
    with UserInterface(user_id) as ui:
        user_event_generator = ui.generate_user_updates()

    producers.append(
        asyncio.create_task(feed_generator_to_queue(user_event_generator, "user")),
    )

    # Start a producer which will watch for the user changing team / game. If
    # this happens, it'll close this connection, prompting a reload
    async def changed_team_generator():
        logger.debug(
            "change_team_generator - Watching for change of team for user %s", user_id
        )

        ui = UserInterface(user_id)

        initial_team_id = ui.get_team_id()  # Might be "none"

        logger.debug(
            "User %s is in team %s. Waiting for update", user_id, initial_team_id
        )

        # Check if the user is in a team
        while ui.get_team_id() == initial_team_id:
            # generate_updates does not interact with the database session, so
            # will not block other database requests
            await anext(ui.generate_user_updates())

        logger.debug("User %s has changed team. Closing connection", user_id)

        yield None
        await asyncio.sleep(1e10)

    # Queue the changed_team_generator
    producers.append(
        asyncio.create_task(
            feed_generator_to_queue(changed_team_generator(), "changed_team")
        )
    )

    # Watch the user ticker if they're in a team
    if UserInterface(user_id).get_team_id() is not None:

        async def ticker_generator():
            logger.debug(
                "updates_generator - User is in game, mounting to game ticker for user %s",
                user_id,
            )
            # Yield one update immediately to refresh the ticker
            yield None

            # Then yield from the ticker
            async for x in UserInterface(user_id).generate_ticker_updates():
                logger.debug(
                    "updates_generator - Forwarding ticker event for user %s", user_id
                )
                yield x

        # Queue the ticker generator
        producers.append(
            asyncio.create_task(feed_generator_to_queue(ticker_generator(), "ticker"))
        )

    # Add a keepalive producer
    async def keepalive_timer(timeout=SSE_KEEPALIVE_TIMEOUT):
        logger.debug("Starting keepalive timer")

        i = 0

        while True:
            await asyncio.sleep(timeout)
            logger.debug("Sending keepalive message %s", i)
            yield i
            i += 1

    producers.append(
        asyncio.create_task(feed_generator_to_queue(keepalive_timer(), "keepalive"))
    )

    # FIXME Stop sending circles automatically
    producers.append(
        asyncio.create_task(
            feed_generator_to_queue(keepalive_timer(timeout=10), "circle")
        )
    )

    # Iterate through the consumer:
    try:
        async for target, data in yield_from_queue():
            logger.debug(
                'updates_generator (UID%s) - Received message from queue: target "%s", data "%s"',
                user_id,
                target,
                data,
            )
            if target == "user":
                yield update_user
            elif target == "ticker":
                yield update_ticker
            elif target == "circle":
                yield update_circles
            elif target == "changed_team":
                # Close the connection to force a reload
                return
            elif target == "keepalive":
                yield make_sse_update_message(
                    json.dumps({"handler": "keepalive", "data": data})
                )
            else:
                logger.error('Unknown update target "%s"', target)
    finally:
        for task in producers:
            task.cancel()


async def admin_updates_generator():
    """
    Asynchronous generator that yields Server-Sent Events (SSE) updates for the
    admin interface.

    This just prompts an update any time anything happens in any game. Very
    inefficient, but who cares, there's only one admin and it's me.
    """

    update_admin = make_sse_update_message(
        json.dumps({"handler": "update_prompt", "data": "admin"})
    )
    yield update_admin
    async for _ in AdminInterface().generate_any_ticker_updates():
        logger.debug("(admin_updates_generator) Update received - sending")
        yield update_admin
