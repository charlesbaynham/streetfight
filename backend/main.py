import logging
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
def hello():
    return {"msg": "Hello world!"}


@router.get("/my_id")
def get_my_id(
    user_id=Depends(get_user_id),
):
    return user_id


@router.get("/user_info")
def get_user_info(
    user_id=Depends(get_user_id),
):
    return UserInterface(user_id).get_user_model()


class Shot(BaseModel):
    photo: str


@router.post("/submit_shot")
def submit_shot(
    shot: Shot,
    user_id=Depends(get_user_id),
):
    logger.info("Received shot from user %s", user_id)

    UserInterface(user_id).submit_shot(shot.photo)


@router.post("/join_game")
def join_game(
    game_id: str,
    user_id=Depends(get_user_id),
):
    try:
        game_id = UUID(game_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    logger.info("User %s joining game %s", user_id, game_id)

    return UserInterface(user_id).join_game(game_id)


######## ADMIN ###########
@router.post("/admin_create_game")
def admin_create_game():
    game_id = AdminInterface().create_game()
    logger.info("Created new game with id = %s", game_id)
    return game_id


@router.get("/admin_list_games")
def admin_list_games():
    return AdminInterface().get_games()


@router.get("/admin_get_shots")
def admin_get_shots(limit=5):
    num_in_queue, filtered_shots = AdminInterface().get_unchecked_shots(limit=limit)
    return {"numInQueue": num_in_queue, "shots": filtered_shots}


@router.post("/admin_kill_user")
def admin_kill_user(user_id):
    AdminInterface().kill_user(user_id)


@router.post("/admin_mark_shot_checked")
def admin_mark_shot_checked(shot_id):
    AdminInterface().mark_shot_checked(shot_id)


app.include_router(router, prefix="/api")
