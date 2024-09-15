import asyncio
import json
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import AsyncGenerator
from typing import Dict
from typing import List
from typing import Optional
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse
from uuid import UUID

import pydantic
from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse

from .admin_interface import AdminInterface
from .dotenv import load_env_vars
from .model import GameModel
from .ticker import Ticker
from .user_id import get_user_id
from .user_interface import UserInterface


# How often to send keepalive messages
SSE_KEEPALIVE_TIMEOUT = 15

logger = logging.getLogger(__name__)


def make_sse_update_message(m):
    return f"data: {m}\n\n"


async def updates_generator(user_id):
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
        user_event_generator = ui.generate_updates()

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

        # get_ticker is db_scoped so this will not hold a session open
        ticker: Optional[Ticker] = ui.get_ticker()

        while ticker is None:
            logger.debug("Ticker updates - User %s is not in a game, waiting", user_id)
            # generate_updates does not interact with the database session, so
            # will not block other database requests
            await anext(ui.generate_updates())
            ticker = ui.get_ticker()

            if ticker:
                logger.debug("Ticker updates - User %s now in game", user_id)
            else:
                logger.debug("Ticker updates - User %s still not in game", user_id)

        logger.debug(
            "updates_generator - User is in game, mounting to game ticker for user %s",
            user_id,
        )
        # Yield one update immediately to refresh the ticker
        yield None

        # Then yield from the ticker
        async for x in ticker.generate_updates():
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
    update_admin = make_sse_update_message(
        json.dumps({"handler": "update_prompt", "data": "admin"})
    )
    yield update_admin
    async for _ in AdminInterface().generate_any_ticker_updates():
        logger.debug("(admin_updates_generator) Update received - sending")
        yield update_admin
