import asyncio
import json
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import AsyncGenerator
from typing import Dict
from typing import Optional
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse
from uuid import UUID

import pydantic
from dotenv import find_dotenv
from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse

from .admin_interface import AdminInterface
from .ticker import Ticker
from .user_id import get_user_id
from .user_interface import UserInterface

SSE_KEEPALIVE_TIMEOUT = 5

load_dotenv(find_dotenv())


def setup_logging():
    # Redirect the uvicorn logger to root
    root_logger = logging.getLogger()
    uvicorn_logger = logging.getLogger("uvicorn")

    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)

    for handler in uvicorn_logger.handlers:
        root_logger.addHandler(handler)
        uvicorn_logger.removeHandler(handler)

    uvicorn_logger.propagate = True

    # Add a file handler
    rotating_handler = RotatingFileHandler(
        Path(__file__) / "../../logs/backend.log", backupCount=10
    )

    # Configure the format for log messages
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    rotating_handler.setFormatter(formatter)

    root_logger.addHandler(rotating_handler)
    rotating_handler.doRollover()

    # Set the root logger level to LOG_LEVEL if specified
    if "LOG_LEVEL" in os.environ:
        logging.getLogger().setLevel(os.environ.get("LOG_LEVEL"))
        root_logger.warning(
            "Setting log level to %s from env var config", os.environ.get("LOG_LEVEL")
        )
    else:
        logging.getLogger().setLevel(logging.INFO)
        root_logger.warning("Setting log level to INFO by default")


setup_logging()
app = FastAPI()
router = APIRouter()
logger = logging.getLogger("main")

app.add_middleware(
    SessionMiddleware,
    secret_key="james will never understand the prostitute",
    max_age=60 * 60 * 24 * 365 * 10,
)


@router.get("/hello")
async def hello():
    return {"msg": "Hello world!"}


@router.get("/my_id")
async def get_my_id(
    user_id=Depends(get_user_id),
):
    return user_id


@router.get("/user_info")
async def get_user_info(
    user_id=Depends(get_user_id),
):
    return UserInterface(user_id).get_user_model()


class _Shot(BaseModel):
    photo: str


@router.post("/submit_shot")
async def submit_shot(
    shot: _Shot,
    user_id=Depends(get_user_id),
):
    logger.info("Received shot from user %s", user_id)

    UserInterface(user_id).submit_shot(shot.photo)


@router.post("/set_name")
async def set_name(
    name: str,
    user_id=Depends(get_user_id),
):
    logger.info("Changing user %s name to %s", user_id, name)
    UserInterface(user_id).set_name(name)


@router.post("/join_game")
async def join_game(
    game_id: str,
    user_id=Depends(get_user_id),
):
    try:
        game_id = UUID(game_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    logger.info("User %s joining game %s", user_id, game_id)

    return UserInterface(user_id).join_game(game_id)


class _EncodedItem(BaseModel):
    data: str


@router.post("/collect_item")
async def collect_item(
    encoded_item: _EncodedItem,
    user_id=Depends(get_user_id),
):
    # Clean off URL prefix if present
    if re.match(r"http", encoded_item.data):
        parsed_url = urlparse(encoded_item.data)
        query_params = parse_qs(parsed_url.query)
        data = query_params["d"][0]
    else:
        data = encoded_item.data

    try:
        return UserInterface(user_id).collect_item(data)
    except ValueError:
        raise HTTPException(400, "Malformed data")


@router.get("/ticker_messages")
async def get_ticker_messages(
    num_messages=3,
    user_id=Depends(get_user_id),
):
    ticker = UserInterface(user_id).get_ticker()
    if ticker is None:
        return []

    return ticker.get_messages(num_messages)


@router.get("/ticker_hash")
async def get_ticker_hash(
    known_hash: int = 0,
    user_id=Depends(get_user_id),
):
    logger.info(
        "User %s called get_ticker_hash with known_ticker_hash=%s",
        user_id,
        known_hash,
    )
    ticker: Ticker = UserInterface(user_id).get_ticker()
    if ticker is None:
        return 0

    return await ticker.get_hash(known_hash=known_hash)


@router.get("/get_hash")
async def get_hash(
    known_hash: int = 0,
    timeout: int = 30,
    user_id=Depends(get_user_id),
) -> int:
    """
    Get a hash that will change if this user's state changes

    This method may take up to `timeout` seconds to return
    if the state is currently the same as `known_state`.

    Args:
        known_hash (int, optional): _description_. Defaults to 0.
        timeout (int, optional): _description_. Defaults to 30.

    Returns:
        int: Hash of the user's current state
    """
    return await UserInterface(user_id).get_hash(known_hash=known_hash, timeout=timeout)


@router.get("/get_users")
async def get_users(game_id: str = None, team_id: str = None):
    if game_id is not None:
        try:
            game_id = UUID(game_id)
        except ValueError as e:
            raise HTTPException(400, str(e))
    if team_id is not None:
        try:
            team_id = UUID(team_id)
        except ValueError as e:
            raise HTTPException(400, str(e))

    return AdminInterface().get_users(game_id=game_id, team_id=team_id)


######## ADMIN ###########
@router.post("/admin_create_game")
async def admin_create_game():
    game_id = AdminInterface().create_game()
    logger.info("Created new game with id = %s", game_id)
    return game_id


@router.post("/admin_create_team")
async def admin_list_games(game_id: UUID, team_name: str) -> int:
    logger.info("Creating new team '%s' for game %s", team_name, game_id)
    return AdminInterface().create_team(game_id, team_name)


@router.post("/admin_add_user_to_team")
async def admin_list_games(user_id: UUID, team_id: UUID) -> int:
    logger.info("Adding user %s to team %s", user_id, team_id)
    return AdminInterface().add_user_to_team(user_id, team_id)


@router.get("/admin_list_games")
async def admin_list_games():
    logger.info("admin_list_games")
    return AdminInterface().get_games()


@router.get("/admin_get_shots")
async def admin_get_shots(limit=5):
    num_in_queue, filtered_shots = AdminInterface().get_unchecked_shots(limit=limit)
    return {"numInQueue": num_in_queue, "shots": filtered_shots}


@router.post("/admin_kill_user")
async def admin_kill_user(user_id):
    AdminInterface().kill_user(user_id)


@router.post("/admin_give_hp")
async def admin_give_hp(user_id, num: int = 1):
    AdminInterface().award_user_HP(user_id, num=num)


@router.post("/admin_give_ammo")
async def admin_give_ammo(user_id, num: int = 1):
    AdminInterface().award_user_ammo(user_id, num=num)


@router.post("/admin_mark_shot_checked")
async def admin_mark_shot_checked(shot_id):
    AdminInterface().mark_shot_checked(shot_id)


def _add_params_to_url(url: str, params: Dict):
    """
    A chatGPT special to add parameters to a URL
    """

    parsed_url = urlparse(url)

    # Extract the query parameters as a dictionary
    query_params = parse_qs(parsed_url.query)

    # Add or update query parameters
    query_params = params

    # Encode the modified query parameters
    encoded_query = urlencode(query_params, doseq=True)

    # Reconstruct the URL with the modified query parameters
    return urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            encoded_query,
            parsed_url.fragment,
        )
    )


@router.post("/admin_make_new_item")
async def admin_make_new_item(item_type: str, item_data: Dict):
    logger.info("admin_make_new_item")
    try:
        encoded_item = AdminInterface().make_new_item(item_type, item_data)
    except pydantic.ValidationError as e:
        raise HTTPException(400, f"Invalid submission - {e}")

    return {
        "itype": item_type,
        "item_data": item_data,
        "encoded_item": encoded_item,
        "encoded_url": _add_params_to_url(
            os.environ["WEBSITE_URL"], {"d": encoded_item}
        ),
    }


async def updates_generator(user_id):
    def make_sse_update_message(m):
        return f"data: {m}\n\n"

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
        async for _ in generator:
            await queue.put(message)

    # A function that yields from the queue as soon as items arrive
    async def yield_from_queue() -> AsyncGenerator:
        while True:
            yield await asyncio.wait_for(queue.get(), timeout=None)

    # Keep track of the asyncio tasks we start for producers
    producers = []

    logger.debug("Updates - Updates for user %s starting", user_id)

    # Start a producer for user events:
    user_event_generator = UserInterface(user_id).generate_updates()
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
        logger.debug("Ticker updates - User %s starting", user_id)
        ui = UserInterface(user_id)

        ticker: Optional[Ticker] = None
        while ticker is None:
            logger.debug("Ticker updates - User %s is not in a game, waiting", user_id)
            await anext(ui.generate_updates())
            ticker = ui.get_ticker()
            if ticker:
                logger.debug("Ticker updates - User %s now in game", user_id)
            else:
                logger.debug("Ticker updates - User %s still not in game", user_id)

        logger.debug("Ticker updates - Mounting to game ticker for user %s", user_id)
        async for x in ticker.generate_updates():
            yield x

    # Queue the ticker generator
    producers.append(
        asyncio.create_task(
            feed_generator_to_queue(ticker_generator_with_check_user_logic(), "ticker")
        )
    )

    # Also add a keepalive producer
    async def keepalive_timer():
        while True:
            await asyncio.sleep(SSE_KEEPALIVE_TIMEOUT)
            logger.debug("Sending SSE keepalive")
            yield

    producers.append(
        asyncio.create_task(feed_generator_to_queue(keepalive_timer(), "keepalive"))
    )

    # Iterate through the consumer:
    try:
        async for target in yield_from_queue():
            logger.debug("Update queue received message '%s'", target)
            if target == "user":
                yield update_user
            elif target == "ticker":
                yield update_ticker
            elif target == "keepalive":
                yield ":keepalive\n\n"
            else:
                logger.error('Unknown update targer "%s"', target)
    finally:
        for task in producers:
            task.cancel()


@router.get("/sse_updates")
async def sse_endpoint(
    user_id=Depends(get_user_id),
):
    return StreamingResponse(
        updates_generator(user_id),
        headers={
            "Content-type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


app.include_router(router, prefix="/api")
