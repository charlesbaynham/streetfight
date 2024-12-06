import logging
import os
from enum import Enum
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict
from typing import List
from uuid import UUID

import pydantic
from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse

from .admin_interface import CircleTypes
from .dotenv import load_env_vars
from .item_actions import WEAPON_NAME_LOOKUP
from .locations import LANDMARK_LOCATIONS
from .ticker_message_dispatcher import send_generic_message


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
    Path("./logs/").mkdir(exist_ok=True)
    rotating_handler = RotatingFileHandler("./logs/backend.log", backupCount=10)

    # Configure the format for log messages
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    rotating_handler.setFormatter(formatter)

    root_logger.addHandler(rotating_handler)
    rotating_handler.doRollover()

    # Set the uvicorn logger to inherit from the root logger
    uvicorn_logger.setLevel("NOTSET")

    # Set the root logger level to LOG_LEVEL if specified
    if "LOG_LEVEL" in os.environ:
        root_logger.setLevel(os.environ.get("LOG_LEVEL"))
        root_logger.warning(
            "Setting log level to %s from env var config", os.environ.get("LOG_LEVEL")
        )
    else:
        root_logger.setLevel(logging.INFO)
        root_logger.warning("Setting log level to INFO by default")

    if "LOG_OVERRIDES" in os.environ:
        overrides = os.environ["LOG_OVERRIDES"]

        for override in overrides.split(","):
            target_logger, level = override.split(":")

            target_logger = target_logger.strip()
            level = level.strip()

            logging.warning('Setting logger "%s" to level "%s"[]', target_logger, level)
            logging.getLogger(target_logger).setLevel(level)


load_env_vars()
setup_logging()

from . import sse_event_streams
from .admin_auth import is_admin_authed
from .admin_auth import mark_admin_authed
from .admin_auth import require_admin_auth

# Import these after logging is setup since they might have side effects (e.g. database setup)
from .admin_interface import AdminInterface
from .model import GameModel
from .model import ShotModel
from .user_id import get_user_id
from .user_interface import UserInterface

app = FastAPI()
router = APIRouter()
logger = logging.getLogger(__name__)

if "SECRET_KEY" not in os.environ:
    logger.warning("No SECRET_KEY found in environment, using default value")
    os.environ["SECRET_KEY"] = "none"

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"],
    max_age=60 * 60 * 24 * 365 * 10,
)


@router.get("/hello")
async def hello():
    return {"msg": "Hello world!"}


@router.get("/my_id")
async def get_my_id(
    user_id=Depends(get_user_id),
) -> UUID:
    return user_id


@router.get("/user_info")
async def get_user_info(
    user_id=Depends(get_user_id),
):
    with UserInterface(user_id) as ui:
        return ui.get_user_model()


@router.get("/get_circles")
async def get_circles(
    user_id=Depends(get_user_id),
):
    with UserInterface(user_id) as ui:
        return ui.get_circles()


class _Shot(BaseModel):
    photo: str


@router.post("/submit_shot")
async def submit_shot(
    shot: _Shot,
    user_id=Depends(get_user_id),
):
    logger.info("Received shot from user %s", user_id)

    with UserInterface(user_id) as ui:
        return ui.submit_shot(shot.photo)


@router.post("/set_name")
async def set_name(
    name: str,
    user_id=Depends(get_user_id),
):
    logger.info("Changing user %s name to %s", user_id, name)
    with UserInterface(user_id) as ui:
        ui.set_name(name)


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

    with UserInterface(user_id) as ui:
        return ui.join_game(game_id)


class _EncodedItem(BaseModel):
    data: str


@router.post("/collect_item")
async def collect_item(
    encoded_item: _EncodedItem,
    user_id=Depends(get_user_id),
):
    try:
        with UserInterface(user_id) as ui:
            return ui.collect_item(encoded_item.data)
    except ValueError:
        raise HTTPException(400, "Malformed data")


@router.get("/ticker_messages")
async def get_ticker_messages(
    num_messages=3,
    user_id=Depends(get_user_id),
):
    return UserInterface(user_id).get_messages(num_messages, private=True)


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


@router.get("/get_scoreboard")
async def get_scoreboard(user_id=Depends(get_user_id)):
    with UserInterface(user_id) as ui:
        game_id = ui.get_user_model().game_id

    if game_id is None:
        raise HTTPException(404, "User is not in a game")

    return AdminInterface().get_scoreboard(game_id)


@router.post("/set_location")
async def set_location(
    latitude: float,
    longitude: float,
    user_id=Depends(get_user_id),
):
    logger.info("Setting location for user %s to %f, %f", user_id, latitude, longitude)
    with UserInterface(user_id) as ui:
        ui.set_location(latitude, longitude)


######## ADMIN ###########


def admin_method(path: str, method: str = "POST"):
    def decorator(func):
        target = router.get if method == "GET" else router.post

        @target(path, dependencies=[Depends(require_admin_auth)])
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


@router.get("/admin_is_authed")
async def admin_is_authed(
    is_admin_authed=Depends(is_admin_authed),
) -> bool:
    return is_admin_authed


@router.post("/admin_authenticate")
async def admin_authenticate(request: Request, password: str) -> bool:
    return mark_admin_authed(request, password)


@admin_method(path="/admin_create_game", method="POST")
async def admin_create_game() -> UUID:
    game_id = AdminInterface().create_game()
    logger.info("Created new game with id = %s", game_id)
    return game_id


@admin_method(path="/admin_create_team", method="POST")
async def admin_create_team(game_id: UUID, team_name: str) -> UUID:
    logger.info("Creating new team '%s' for game %s", team_name, game_id)
    return AdminInterface().create_team(game_id, team_name)


@admin_method(path="/admin_add_user_to_team", method="POST")
async def admin_add_user_to_team(user_id: UUID, team_id: UUID) -> None:
    logger.info("Adding user %s to team %s", user_id, team_id)
    return AdminInterface().add_user_to_team(user_id, team_id)


@admin_method("/admin_list_games", method="GET")
async def admin_list_games() -> List[GameModel]:
    logger.info("admin_list_games")
    return AdminInterface().get_games()


@admin_method("/admin_get_shots", method="GET")
async def admin_get_shots(limit=5):
    num_in_queue, filtered_shots = AdminInterface().get_unchecked_shots(limit=limit)
    return {"numInQueue": num_in_queue, "shots": filtered_shots}


@admin_method("/admin_get_shots_info", method="GET")
async def admin_get_shots_info() -> list[UUID]:
    return AdminInterface().get_unchecked_shots_ids()


@admin_method("/admin_get_shot", method="GET")
async def admin_get_shot(shot_id: UUID) -> ShotModel:
    shot_model = AdminInterface().get_shot_model(shot_id=shot_id)
    return AdminInterface.markup_shot_model(shot_model)


@admin_method(path="/admin_shot_hit_user", method="POST")
async def admin_shot_hit_user(shot_id: UUID, target_user_id: UUID):
    AdminInterface().hit_user(shot_id, target_user_id)


@admin_method(path="/admin_set_hp", method="POST")
async def admin_set_hp(user_id, num: int = 1):
    AdminInterface().set_user_HP(user_id, num=num)


Weapon = Enum("Weapon", {v: v for k, v in WEAPON_NAME_LOOKUP.items()})
WEAPON_DATA_LOOKUP = {Weapon(v): k for k, v in WEAPON_NAME_LOOKUP.items()}


@admin_method(path="/admin_set_weapon", method="POST")
async def admin_set_weapon(user_id, weapon: Weapon):  # type: ignore
    shot_damage, shot_timeout = WEAPON_DATA_LOOKUP[weapon]
    UserInterface(user_id=user_id).set_weapon_data(
        damage=shot_damage, fire_delay=shot_timeout
    )


@admin_method(path="/admin_hit_user", method="POST")
async def admin_hit_user(user_id, num: int = 1):
    AdminInterface().hit_user_by_admin(user_id, num=num)


@admin_method(path="/admin_give_ammo", method="POST")
async def admin_give_ammo(user_id, num: int = 1):
    AdminInterface().award_user_ammo(user_id, num=num)


@admin_method(path="/admin_refund_shot", method="POST")
async def admin_refund_shot(shot_id):
    AdminInterface().refund_shot(shot_id)


@admin_method(path="/admin_mark_shot_missed", method="POST")
async def admin_mark_shot_missed(shot_id):
    AdminInterface().mark_shot_missed(shot_id)


@admin_method("/admin_get_locations", method="GET")
async def admin_get_locations(game_id=None):
    """
    Get the locations of all users in a game

    :param game_id: The game to get locations for. If None, use the first game.
    """
    return AdminInterface().get_locations(game_id=game_id)


@admin_method(path="/admin_make_new_item", method="POST")
async def admin_make_new_item(
    item_type: str,
    item_data: Dict,
    collected_only_once=True,
    collected_as_team=False,
):
    logger.info("admin_make_new_item")
    try:
        encoded_url = AdminInterface().make_new_item(
            item_type,
            item_data,
            collected_only_once=collected_only_once,
            collected_as_team=collected_as_team,
        )
    except pydantic.ValidationError as e:
        raise HTTPException(400, f"Invalid submission - {e}")

    return {
        "itype": item_type,
        "item_data": item_data,
        "encoded_item": encoded_url,
        "encoded_url": encoded_url,
    }


@admin_method(path="/admin_set_game_active", method="POST")
async def admin_set_game_active(game_id: UUID, active: bool):
    logger.info("admin_set_game_active")
    AdminInterface().set_game_active(game_id, active)


@admin_method(path="/admin_set_user_name", method="POST")
async def admin_set_user_name(user_id: UUID, name: str):
    logger.info("admin_set_user_name")
    AdminInterface().set_user_name(user_id=user_id, name=name)


@admin_method(path="/admin_set_circle", method="POST")
async def admin_set_circle(
    game_id: UUID, name: CircleTypes, lat: float, long: float, radius_km: float
):
    logger.info("admin_set_circle - %s", locals())
    AdminInterface().set_circles(
        game_id=game_id, name=name, lat=lat, long=long, radius=radius_km
    )


Landmark = Enum("Landmark", {k: k for k in LANDMARK_LOCATIONS.keys()})


@admin_method(path="/admin_set_circle_by_location", method="POST")
async def admin_set_circle(
    game_id: UUID,
    name: CircleTypes,
    location: Landmark,  # type: ignore
    radius_km: float,
):
    logger.info("admin_set_circle_by_location - %s", locals())

    location = str(location.value).upper().replace(" ", "_")
    try:
        lat, long = LANDMARK_LOCATIONS[location]
    except KeyError:
        raise HTTPException(404, f"Unknown location {location}")

    AdminInterface().set_circles(
        game_id=game_id, name=name, lat=lat, long=long, radius=radius_km
    )


@admin_method(path="/admin_clear_circle", method="POST")
async def admin_set_circle(
    game_id: UUID,
    name: CircleTypes,
):
    logger.info("admin_clear_circle - %s", locals())

    AdminInterface().set_circles(
        game_id=game_id, name=name, lat=None, long=None, radius=None
    )


@admin_method(path="/admin_reset_game", method="POST")
async def admin_reset_game(game_id: UUID, keep_weapons: bool = True):
    logger.info("admin_reset_game - %s", locals())

    AdminInterface().reset_game(game_id=game_id, keep_weapons=keep_weapons)


@admin_method(path="/admin_send_custom_ticker_message", method="POST")
async def admin_send_custom_ticker_message(
    game_id: UUID,
    message: str,
):
    logger.info("admin_send_custom_ticker_message - %s", locals())

    send_generic_message(game_id, message)


@router.get("/sse_updates")
async def sse_updates(
    user_id=Depends(get_user_id),
):
    return StreamingResponse(
        sse_event_streams.updates_generator(user_id),
        headers={
            "Content-type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@admin_method("/sse_admin_updates", method="GET")
async def sse_admin_updates():
    return StreamingResponse(
        sse_event_streams.admin_updates_generator(),
        headers={
            "Content-type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


app.include_router(router, prefix="/api")
