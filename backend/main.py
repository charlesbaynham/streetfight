import json
import logging
import os
import random
from typing import Optional


import pydantic
from dotenv import find_dotenv
from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Path
from fastapi import Query
from fastapi import Request
from fastapi import Response
from starlette.middleware.sessions import SessionMiddleware


from .user_id import get_user_id

logger = logging.getLogger("main")

# Set the root logger level to LOG_LEVEL if specified
load_dotenv(find_dotenv())
if "LOG_LEVEL" in os.environ:
    logging.getLogger().setLevel(os.environ.get("LOG_LEVEL"))
    logger.info("Setting log level to %s", os.environ.get("LOG_LEVEL"))
else:
    logging.getLogger().setLevel(logging.INFO)
    logger.info("Setting log level to INFO by default")


app = FastAPI()
router = APIRouter()

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


app.include_router(router, prefix="/api")
