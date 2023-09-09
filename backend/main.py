import pydantic
import logging
from typing import Dict
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import UUID

from dotenv import find_dotenv
from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from .admin_interface import AdminInterface
from .user_id import get_user_id
from .user_interface import UserInterface


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
    root_logger.addHandler(rotating_handler)
    rotating_handler.doRollover()

    # Set the root logger level to LOG_LEVEL if specified
    load_dotenv(find_dotenv())
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

    return UserInterface(user_id).collect_item(encoded_item.data)


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


@router.post("/admin_make_new_item")
async def admin_make_new_item(item_type: str, item_data: Dict):
    try:
        encoded_item = AdminInterface().make_new_item(item_type, item_data)
    except pydantic.ValidationError as e:
        raise HTTPException(400, f"Invalid submission - {e}")

    return {
        "item_type": item_type,
        "item_data": item_data,
        "encoded_item": encoded_item,
    }


app.include_router(router, prefix="/api")
