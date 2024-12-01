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
    return f"data: {m}\n\n"


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

    yield update_user
    yield update_ticker

    # An asyncio queue to pass to the generators
    queue = asyncio.Queue()

    # A function that logs a message every time an async generator yields
    async def feed_generator_to_queue(generator: AsyncGenerator, message: str) -> None:
        async for data in generator:
            await queue.put((message, data))

    # A function that yields from the queue as soon as items arrive
    async def yield_from_queue() -> AsyncGenerator:
        while True:
            yield await asyncio.wait_for(queue.get(), timeout=None)

    # Keep track of the asyncio tasks we start for producers
    producers = []

    logger.debug("updates_generator - User updates for user %s starting", user_id)

    # Start a producer for user events:
    with UserInterface(user_id) as ui:
        user_event_generator = ui.generate_user_updates()

    producers.append(
        asyncio.create_task(feed_generator_to_queue(user_event_generator, "user")),
    )

    # Start a more complicated producer for the ticker. This:
    #
    # a) If the user is in a team, attaches to the ticker updates
    #
    # b) If the user is not in a team, attaches to the user_updates until the
    # user is in a team, then attaches to the ticker updates
    #
    # TODO: Handle the user changing team while this connection is running
    async def ticker_generator_with_check_user_logic():
        logger.debug("updates_generator - Ticker updates for user %s starting", user_id)

        ui = UserInterface(user_id)

        # Check if the user is in a team
        while ui.get_team_id() is None:
            logger.debug("User %s is not in a game, waiting", user_id)

            # generate_updates does not interact with the database session, so
            # will not block other database requests
            await anext(ui.generate_user_updates())

        logger.debug(
            "updates_generator - User is in game, mounting to game ticker for user %s",
            user_id,
        )
        # Yield one update immediately to refresh the ticker
        yield None

        # Then yield from the ticker
        async for x in ui.generate_ticker_updates():
            logger.debug(
                "updates_generator - Forwarding ticker event for user %s", user_id
            )
            yield x

    # Queue the ticker generator
    producers.append(
        asyncio.create_task(
            feed_generator_to_queue(ticker_generator_with_check_user_logic(), "ticker")
        )
    )

    # Also add a keepalive producer
    async def keepalive_timer():
        i = 0

        while True:
            await asyncio.sleep(SSE_KEEPALIVE_TIMEOUT)
            yield i
            i += 1

    producers.append(
        asyncio.create_task(feed_generator_to_queue(keepalive_timer(), "keepalive"))
    )

    # Iterate through the consumer:
    try:
        async for target, data in yield_from_queue():
            if target == "user":
                yield update_user
            elif target == "ticker":
                yield update_ticker
            elif target == "keepalive":
                yield make_sse_update_message(
                    json.dumps({"handler": "keepalive", "data": data})
                )
            else:
                logger.error('Unknown update targer "%s"', target)
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
