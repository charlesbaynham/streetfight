import datetime
import enum
import json
import logging
import random
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Union
from uuid import UUID

import pydantic
import sqlalchemy.sql.functions as func
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator
from sqlalchemy.types import VARCHAR
from sqlalchemy_utils import UUIDType

from .utils import hash_str_to_int

Base = declarative_base()


class JSONEncodedDict(TypeDecorator):
    """Represents an immutable structure as a json-encoded string.

    See
    https://docs.sqlalchemy.org/en/13/core/custom_types.html#marshal-json-strings

    Usage::
        JSONEncodedDict(255)
    """

    impl = VARCHAR

    class UUIDEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, UUID):
                # if the obj is uuid, we simply return the value of uuid
                return obj.hex
            return json.JSONEncoder.default(self, obj)

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value, cls=self.UUIDEncoder)

        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


def random_counter_value():
    return random.randint(1, 2147483646)


class Game(Base):
    """The current state of a game"""

    __tablename__ = "games"

    id = Column(Integer, primary_key=True, nullable=False)
    time_created = Column(DateTime, server_default=func.now())

    # users = relationship("User", backref="game", lazy=True)
    # teams = relationship("Team", backref="game", lazy=True)

    update_tag = Column(Integer(), default=random_counter_value)

    def touch(self):
        self.update_tag = random_counter_value()


class Team(Base):
    """
    A team in a game

    Teams contain zero or more players and are associated with exactly one game
    """

    __tablename__ = "teams"

    id = Column(UUIDType, primary_key=True, nullable=False)
    time_created = Column(DateTime, server_default=func.now())
    name = Column(String)

    game_id = Column(Integer, ForeignKey("games.id"))
    game = relationship("Game", lazy="joined", foreign_keys=game_id)

    # users = relationship("User", backref="team", lazy=True)


class User(Base):
    """
    Details of each user, recognised by their session id

    A user is in one or zero games, and one or zero teams
    """

    __tablename__ = "users"

    id = Column(UUIDType, primary_key=True, nullable=False)
    time_created = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, default=func.now())
    name = Column(String)

    game_id = Column(Integer, ForeignKey("games.id"), default=0)
    team_id = Column(Integer, ForeignKey("teams.id"), default=0)

    # game = relationship("Game", lazy="joined", foreign_keys=game_id)
    # team = relationship("Team", lazy="joined", foreign_keys=team_id)

    def touch(self):
        self.last_seen = datetime.datetime.now()


class GameModel(pydantic.BaseModel):
    id: int
    update_tag: int

    users: List["UserModel"]
    teams: List["TeamModel"]

    class Config:
        orm_mode = True
        extra = "forbid"


class UserModel(pydantic.BaseModel):
    id: UUID
    name: str
    game: GameModel
    team: "TeamModel"

    class Config:
        orm_mode = True
        extra = "forbid"


class TeamModel(pydantic.BaseModel):
    id: int
    name: str
    game: GameModel
    users: List[UserModel]

    class Config:
        orm_mode = True
        extra = "forbid"


GameModel.update_forward_refs()
UserModel.update_forward_refs()
TeamModel.update_forward_refs()
