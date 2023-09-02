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
from uuid import uuid4 as get_uuid

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


def random_counter_value():
    return random.randint(1, 2147483646)


class Game(Base):
    """The current state of a game"""

    __tablename__ = "games"

    id = Column(UUIDType, primary_key=True, default=get_uuid)
    time_created = Column(DateTime, server_default=func.now())

    teams = relationship("Team", lazy=True, back_populates="game")
    shots = relationship("Shot", lazy=True, back_populates="game")

    update_tag = Column(Integer(), default=random_counter_value)

    def touch(self):
        self.update_tag = random_counter_value()


class Shot(Base):
    """
    A shot from a user in a game

    Note that we record what team the user that fired the shot was
    in when the shot was fired, in case the user later switches team
    """

    __tablename__ = "shots"

    id = Column(Integer, primary_key=True, nullable=False)
    time_created = Column(DateTime, server_default=func.now())

    game_id = Column(UUIDType, ForeignKey("games.id"), nullable=False)
    game = relationship(
        "Game", lazy="joined", foreign_keys=game_id, back_populates="shots"
    )

    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    user = relationship(
        "User", lazy="joined", foreign_keys=user_id, back_populates="shots"
    )

    team_id = Column(UUIDType, ForeignKey("teams.id"), nullable=False)
    team = relationship(
        "Team", lazy="joined", foreign_keys=team_id, back_populates="shots"
    )

    image_base64 = Column(String, nullable=False)
    checked = Column(Boolean, nullable=False, default=False)


class Team(Base):
    """
    A team in a game

    Teams contain zero or more players and are associated with exactly one game
    """

    __tablename__ = "teams"

    id = Column(UUIDType, primary_key=True, default=get_uuid)
    time_created = Column(DateTime, server_default=func.now())
    name = Column(String)

    game_id = Column(UUIDType, ForeignKey("games.id"))
    game = relationship(
        "Game", lazy="joined", foreign_keys=game_id, back_populates="teams"
    )

    users = relationship("User", lazy=True, back_populates="team")
    shots = relationship("Shot", lazy=True, back_populates="team")


class User(Base):
    """
    Details of each user, recognised by their session id

    A user is in one or zero games, and one or zero teams
    """

    __tablename__ = "users"

    id = Column(UUIDType, primary_key=True, default=get_uuid)
    time_created = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, default=func.now())
    name = Column(String)

    team_id = Column(UUIDType, ForeignKey("teams.id"))
    team = relationship(
        "Team", lazy="joined", foreign_keys=team_id, back_populates="users"
    )

    num_bullets = Column(Integer, nullable=False, default=0)
    hit_points = Column(Integer, nullable=False, default=1)

    shots = relationship("Shot", lazy=True, back_populates="user")

    def touch(self):
        self.last_seen = datetime.datetime.now()


class GameModel(pydantic.BaseModel):
    id: UUID
    update_tag: int

    teams: List["TeamModel"]

    class Config:
        orm_mode = True
        extra = "forbid"


class UserModel(pydantic.BaseModel):
    id: UUID
    name: Optional[str]

    team_id: Optional[int]

    num_bullets: int
    hit_points: int

    class Config:
        orm_mode = True
        extra = "forbid"


class TeamModel(pydantic.BaseModel):
    id: UUID
    name: str
    game_id: UUID
    users: List[UserModel]

    class Config:
        orm_mode = True
        extra = "forbid"


class ShotModel(pydantic.BaseModel):
    id: int
    time_created: datetime.datetime
    game_id: UUID
    checked: bool
    image_base64: str

    user: UserModel
    game: GameModel

    class Config:
        orm_mode = True
        extra = "forbid"


GameModel.update_forward_refs()
UserModel.update_forward_refs()
TeamModel.update_forward_refs()
ShotModel.update_forward_refs()
