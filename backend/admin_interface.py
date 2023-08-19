import asyncio
import logging
from functools import wraps
from typing import Callable
from typing import Dict
from typing import List
from uuid import UUID
from uuid import uuid4 as get_uuid

from fastapi import HTTPException
from sqlalchemy.ext import baked

from . import database
from .model import Game
from .model import GameModel
from .model import Shot
from .model import User
from .model import UserModel

logger = logging.getLogger(__name__)


class AdminInterface:
    def get_games(self) -> List[GameModel]:
        session = database.Session()
        return [GameModel.from_orm(g) for g in session.query(Game).all()]
