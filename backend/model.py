import datetime
import enum
import logging
import random
import time
from typing import List
from typing import Optional
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
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy_utils import UUIDType

DEFAULT_SHOT_TIMEOUT = 6

# The values Shot.ai_review_state can take. They live here, next to the column,
# rather than in backend.ai_shot_review so that code which only reads the column
# does not have to import the review worker.
AI_REVIEW_STATE_PENDING = "pending"
AI_REVIEW_STATE_DONE = "done"
AI_REVIEW_STATE_ERROR = "error"

Base = declarative_base()

logger = logging.getLogger(__name__)


def random_counter_value():
    return random.randint(1, 2147483646)


class Game(Base):
    """The current state of a game"""

    __tablename__ = "games"

    id = Column(UUIDType, primary_key=True, default=get_uuid)
    time_created = Column(DateTime, server_default=func.now())
    active = Column(Boolean, nullable=False, default=False)

    # When on, every unchecked shot is sent to a vision model and annotated
    # with what it saw. The admin still makes the call; this only adds tags.
    ai_shot_review_enabled = Column(Boolean, nullable=False, default=False)

    teams = relationship("Team", lazy=True, back_populates="game")
    shots = relationship("Shot", lazy=True, back_populates="game")
    items = relationship("Item", lazy=True, back_populates="game")

    exclusion_circle_lat = Column(Float, nullable=True)
    exclusion_circle_long = Column(Float, nullable=True)
    exclusion_circle_radius = Column(Float, nullable=True)

    next_circle_lat = Column(Float, nullable=True)
    next_circle_long = Column(Float, nullable=True)
    next_circle_radius = Column(Float, nullable=True)

    drop_circle_lat = Column(Float, nullable=True)
    drop_circle_long = Column(Float, nullable=True)
    drop_circle_radius = Column(Float, nullable=True)

    ticker_update_tag = Column(Integer(), default=random_counter_value)

    def touch(self):
        old = self.ticker_update_tag
        new = random_counter_value()
        logger.debug(
            "Changing ticker_update_tag for game %s from %s to %s", self.id, old, new
        )
        self.ticker_update_tag = new


class Shot(Base):
    """
    A shot from a user in a game

    Note that we record what team the user that fired the shot was
    in when the shot was fired, in case the user later switches team
    """

    __tablename__ = "shots"

    id = Column(UUIDType, primary_key=True, nullable=False, default=get_uuid)
    time_created = Column(DateTime, server_default=func.now())

    game_id = Column(UUIDType, ForeignKey("games.id"), nullable=False)
    game = relationship(
        "Game", lazy="joined", foreign_keys=game_id, back_populates="shots"
    )

    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    user = relationship(
        "User", lazy="joined", foreign_keys=user_id, back_populates="shots"
    )

    target_user_id = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    target_user = relationship("User", lazy="joined", foreign_keys=user_id)

    team_id = Column(UUIDType, ForeignKey("teams.id"), nullable=False)
    team = relationship(
        "Team", lazy="joined", foreign_keys=team_id, back_populates="shots"
    )

    # Required since users could pick up upgrades after taking this shot
    shot_damage = Column(Integer, default=1)

    image_base64 = Column(String, nullable=False)
    checked = Column(Boolean, nullable=False, default=False)

    # How the shot was adjudicated: "hit" / "miss" / "refunded", or null while
    # it is still in the queue. Recorded so the shooter's shot history can
    # report what happened - target_user_id alone can't tell a miss from a
    # refund.
    result = Column(String, nullable=True)

    location_context = Column(String, nullable=True)

    # AI review of the photo. Advisory only: the admin still decides every
    # shot, these just become tags under the image in the queue.
    # State is null (never queued) / "pending" / "done" / "error".
    ai_review_state = Column(String, nullable=True)
    # The ShotVisionResult as JSON text, or the error message when the state is
    # "error". Text JSON matches how location_context is already stored.
    ai_review = Column(String, nullable=True)


class Team(Base):
    """
    A team in a game

    Teams contain zero or more players and are associated with exactly one game
    """

    __tablename__ = "teams"

    id = Column(UUIDType, primary_key=True, default=get_uuid)
    time_created = Column(DateTime, server_default=func.now())
    name = Column(String)

    game_id = Column(UUIDType, ForeignKey("games.id"), nullable=False)
    game = relationship("Game", lazy=True, foreign_keys=game_id, back_populates="teams")

    users = relationship("User", lazy=True, back_populates="team")
    shots = relationship("Shot", lazy=True, back_populates="team")


user_item_association_table = Table(
    "association_table",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("item_id", ForeignKey("items.id"), primary_key=True),
)


class UserState(str, enum.Enum):
    WAITING = "waiting"
    ALIVE = "alive"
    DEAD = "dead"
    KNOCKED_OUT = "knocked out"


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
    shot_timeout = Column(Float, nullable=False, default=DEFAULT_SHOT_TIMEOUT)
    shot_damage = Column(Integer, nullable=False, default=1)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_timestamp = Column(Float, nullable=True)

    time_of_death = Column(Float, nullable=True)
    "Timestamp at which this user transitions from dying to dead"

    shots = relationship(
        "Shot", lazy=True, back_populates="user", foreign_keys=[Shot.user_id]
    )

    items = relationship(
        "Item", secondary=user_item_association_table, back_populates="users"
    )

    update_tag = Column(Integer(), default=random_counter_value)

    @property
    def active(self):
        if not self.team:
            return False

        return self.team.game.active

    @property
    def game_id(self) -> Optional[UUID]:
        if not self.team:
            return None

        return self.team.game.id

    @classmethod
    def calculate_state(cls, team, hit_points, time_of_death):
        if not team:
            return UserState.WAITING
        if hit_points > 0:
            return UserState.ALIVE
        if time_of_death < time.time():
            return UserState.DEAD
        else:
            return UserState.KNOCKED_OUT

    @property
    def state(self) -> UserState:
        return self.calculate_state(self.team, self.hit_points, self.time_of_death)

    @property
    def team_name(self):
        if not self.team:
            return None

        return self.team.name

    def touch(self):
        old = self.update_tag
        new = random_counter_value()
        logger.debug("Changing update_tag for user %s from %s to %s", self.id, old, new)
        self.update_tag = new
        self.last_seen = datetime.datetime.now()


class ItemType(str, enum.Enum):
    AMMO = "ammo"
    MEDPACK = "medpack"
    ARMOUR = "armour"
    WEAPON = "weapon"


class TickerEntry(Base):
    __tablename__ = "ticker_entries"

    id = Column(Integer, primary_key=True)
    time_created = Column(DateTime, server_default=func.now())

    game_id = Column(UUIDType, ForeignKey("games.id"), index=True, nullable=False)
    game = relationship("Game", lazy=True, foreign_keys=game_id)

    private_user_id = Column(
        UUIDType, ForeignKey("users.id"), index=True, nullable=True
    )
    private_user = relationship(
        "User",
        lazy=True,
        foreign_keys=private_user_id,
    )

    highlight_user_id = Column(
        UUIDType, ForeignKey("users.id"), index=True, nullable=True
    )
    highlight_user = relationship(
        "User",
        lazy=True,
        foreign_keys=highlight_user_id,
    )

    message = Column(String, nullable=False)


class Item(Base):
    """
    An item that has been collected by a user. Items are stored in the real world (probably as signed QR codes): these can be validated and, if validated, are stored in this table to prevent duplicate pickups.
    """

    __tablename__ = "items"

    id = Column(UUIDType, primary_key=True, nullable=False)
    time_created = Column(DateTime, server_default=func.now())

    item_type = Column(Enum(ItemType))
    data = Column(String)
    "Arbitary data for objects of this type. Might be used for special, per-item code"

    collected_only_once = Column(Boolean, default=True, nullable=False)
    collected_as_team = Column(Boolean, default=False, nullable=False)

    game_id = Column(UUIDType, ForeignKey("games.id"))
    game = relationship(
        "Game", lazy="joined", foreign_keys=game_id, back_populates="items"
    )

    users = relationship(
        "User", secondary=user_item_association_table, back_populates="items"
    )


class GameModel(pydantic.BaseModel):
    id: UUID

    teams: List["TeamModel"]
    ticker_update_tag: int
    active: bool
    ai_shot_review_enabled: bool = False

    exclusion_circle_lat: Optional[float] = None
    exclusion_circle_long: Optional[float] = None
    exclusion_circle_radius: Optional[float] = None

    next_circle_lat: Optional[float] = None
    next_circle_long: Optional[float] = None
    next_circle_radius: Optional[float] = None

    drop_circle_lat: Optional[float] = None
    drop_circle_long: Optional[float] = None
    drop_circle_radius: Optional[float] = None

    model_config = pydantic.ConfigDict(from_attributes=True, extra="forbid")


class UserModel(pydantic.BaseModel):
    id: UUID
    name: Optional[str] = None

    team_id: Optional[UUID] = None

    num_bullets: int
    hit_points: int
    shot_timeout: float
    shot_damage: int
    time_of_death: Optional[float] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_timestamp: Optional[float] = None

    # These are retrieved from the Game associated with the Team this user is in
    game_id: Optional[UUID] = None
    active: bool
    state: UserState

    # This is retrieved from the team too
    team_name: Optional[str] = None

    model_config = pydantic.ConfigDict(from_attributes=True, extra="forbid")


class TeamModel(pydantic.BaseModel):
    id: UUID
    name: str
    game_id: UUID
    users: List[UserModel]

    model_config = pydantic.ConfigDict(from_attributes=True, extra="forbid")


class ShotModel(pydantic.BaseModel):
    id: UUID
    time_created: datetime.datetime
    game_id: UUID
    checked: bool
    result: Optional[str] = None
    image_base64: str

    user: UserModel
    game: GameModel

    user_id: UUID
    target_user_id: Optional[UUID] = None

    shot_damage: int

    location_context: Optional[str] = None

    ai_review_state: Optional[str] = None
    ai_review: Optional[str] = None

    model_config = pydantic.ConfigDict(from_attributes=True, extra="forbid")


class TickerEntryModel(pydantic.BaseModel):
    id: int
    time_created: datetime.datetime
    game_id: UUID
    message: str

    model_config = pydantic.ConfigDict(from_attributes=True, extra="forbid")


GameModel.model_rebuild()
UserModel.model_rebuild()
TeamModel.model_rebuild()
ShotModel.model_rebuild()
