import datetime
import enum
import logging
import random
import time
from typing import Dict
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

DEFAULT_SHOT_TIMEOUT = 25

# The weapon a player is handed by the 16:00 reset, and the hit points they
# start it with. A weapon is the pair (shot_damage, shot_timeout), named by
# item_actions.WEAPON_NAME_LOOKUP -- this one is the Pewster. There is no
# armour column: level n armour sets hit_points to n + 1, so "starting armour
# 1" is a starting hit_points of 2.
BASIC_WEAPON = (1, DEFAULT_SHOT_TIMEOUT)
STARTING_HIT_POINTS = 2

# The values Shot.ai_review_state can take. They live here, next to the column,
# rather than in backend.ai_shot_review so that code which only reads the column
# does not have to import the review worker.
AI_REVIEW_STATE_PENDING = "pending"
AI_REVIEW_STATE_DONE = "done"
AI_REVIEW_STATE_ERROR = "error"

# How many appeals a player gets per game (roadmap R8). One constant rather
# than a number scattered about: three is a guess to revisit after a night's
# play. Refunded whenever an appeal is upheld, so the price is on being wrong
# rather than on appealing.
APPEALS_PER_GAME = 3

# What an appellant must say is wrong with the verdict. The first four are the
# target's ("I was not hit at all" through to "I was already out"); the last is
# the shooter's, appealing a miss or a bystander call that should have been a
# hit. Recorded because it labels the error class, which is exactly the data
# the recognition work has to reconstruct by hand today.
APPEAL_REASONS = {
    "missed",
    "wrong_target",
    "not_a_player",
    "already_out",
    "actually_hit",
}

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
    # with what it saw. Annotation only: the admin still resolves every shot
    # unless ai_auto_actions_enabled is also on.
    ai_shot_review_enabled = Column(Boolean, nullable=False, default=False)

    # When on, confident verdicts on the head of the shot queue are acted on
    # automatically (backend/shot_auto_actions.py); ambiguous or unconfident
    # reviews stay in the queue for the admin. Independent of
    # ai_shot_review_enabled -- it acts on whatever reviews exist, however
    # they were produced.
    ai_auto_actions_enabled = Column(Boolean, nullable=False, default=False)

    # When off, the ladder's escalate rungs go straight to the admin instead of
    # to the stronger model (backend/shot_escalation.py) -- exactly what happens
    # with no OPENROUTER_API_KEY configured. OPENROUTER_ESCALATION_MODEL itself
    # defaults to whatever OPENROUTER_MODEL is, so escalation needs no separate
    # opt-in once recognition is set up. Defaults *on*, unlike the two above:
    # those are the opt-in for the AI features, while escalation only ever runs
    # when auto-actions are on and a vision model is configured, so this is a
    # kill switch inside a feature already opted into rather than a third
    # opt-in.
    ai_escalation_enabled = Column(Boolean, nullable=False, default=True)

    # When on, the auto-action drain resolves the head of the queue as best it
    # can rather than handing anything ambiguous to the admin: _decide() stops
    # meaning "stop the drain" and starts meaning "the players will complain if
    # it is wrong". Only safe alongside appeals (roadmap R8), which is what
    # makes an automatic error loud and recoverable rather than silent and
    # final, so it is off by default like its two opt-in siblings.
    ai_resolve_everything_enabled = Column(Boolean, nullable=False, default=False)

    teams = relationship("Team", lazy=True, back_populates="game")
    shots = relationship("Shot", lazy=True, back_populates="game")
    items = relationship("Item", lazy=True, back_populates="game")
    # The crates the courier has put out and nobody has claimed yet (M4.3).
    # Oldest first, which is the order the courier dropped them in and so the
    # order their list on /admin/courier reads in.
    drops = relationship(
        "Drop",
        lazy=True,
        back_populates="game",
        order_by="Drop.time_created",
    )

    exclusion_circle_lat = Column(Float, nullable=True)
    exclusion_circle_long = Column(Float, nullable=True)
    exclusion_circle_radius = Column(Float, nullable=True)

    next_circle_lat = Column(Float, nullable=True)
    next_circle_long = Column(Float, nullable=True)
    next_circle_radius = Column(Float, nullable=True)

    drop_circle_lat = Column(Float, nullable=True)
    drop_circle_long = Column(Float, nullable=True)
    drop_circle_radius = Column(Float, nullable=True)

    # What the players are told is coming next, and when (M3.1). The kind is
    # one of backend.next_event's KIND_CIRCLE / KIND_DROP, next_event_at is
    # the epoch second it lands at, and next_event_note is the free text an
    # admin typed to go with it - the drop's contents, in practice. All three
    # are null together when nothing is cued, and are cleared together when
    # the cue fires or is cancelled, so next_event_at is the one field to test
    # for "is anything cued".
    #
    # They live on the Game rather than in a table of their own because only
    # one thing is ever cued at a time, and because a column can ride out to
    # every phone on UserModel, where the existing "user" SSE refetch delivers
    # it with no new stream.
    next_event_kind = Column(String, nullable=True)
    next_event_at = Column(Float, nullable=True)
    next_event_note = Column(String, nullable=True)

    # Where the courier is right now (M4.1): whoever is walking a crate to a
    # drop, broadcasting from /admin/courier. It hangs off the Game and not
    # off a User because the courier is not playing - there is no player row
    # to put it on, and only one person carries the crate at a time.
    #
    # All null means nobody is broadcasting, which is also the state after the
    # drop is placed: the courier's job ends when the crate is on the ground.
    # courier_timestamp is what the maps fade the dot by, so a stale fix
    # reads as stale rather than as a courier standing still.
    #
    # courier_accuracy is the browser's own radius-in-metres estimate. Like
    # User.location_accuracy and Shot.heading it is captured because it cannot
    # be recovered after the night, and is consumed by nothing yet.
    courier_lat = Column(Float, nullable=True)
    courier_long = Column(Float, nullable=True)
    courier_timestamp = Column(Float, nullable=True)
    courier_accuracy = Column(Float, nullable=True)

    # Has the next circle been announced to the players (M6.2)? Placing NEXT
    # no longer tells anybody: the cue (M3.2) is what makes it public, and
    # until then the only players who see it are the ones holding a live
    # early-warning card. Placing or clearing NEXT puts this back to False, so
    # moving the circle mid-countdown takes it off every phone again. The
    # admin map and the spectator screen read the columns directly and always
    # see it.
    next_circle_public = Column(Boolean, nullable=False, default=False)

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
    # NOT NULL because a shot's own moment is what its telemetry is read
    # against (backend/shot_identification.shot_epoch) and what the queue is
    # ordered by. Nothing writes a null - submit_shot is the only writer, and
    # it leaves the server default alone unless a replay hands it a time.
    time_created = Column(DateTime, server_default=func.now(), nullable=False)

    game_id = Column(UUIDType, ForeignKey("games.id"), nullable=False)
    game = relationship(
        "Game", lazy="joined", foreign_keys=game_id, back_populates="shots"
    )

    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    user = relationship(
        "User", lazy="joined", foreign_keys=user_id, back_populates="shots"
    )

    target_user_id = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    target_user = relationship("User", lazy="joined", foreign_keys=target_user_id)

    team_id = Column(UUIDType, ForeignKey("teams.id"), nullable=False)
    team = relationship(
        "Team", lazy="joined", foreign_keys=team_id, back_populates="shots"
    )

    # Required since users could pick up upgrades after taking this shot
    shot_damage = Column(Integer, default=1)
    # Same reasoning as shot_damage above: recorded at fire time because a
    # player's own shot_timeout can change later. Damage alone cannot name a
    # weapon (react-ui/src/weapons.js's WEAPONS keys on both, since e.g.
    # Pewster and Eat-a-bullet share damage 1) - this is what lets the shot
    # queue and a player's own shot history say which weapon fired a shot.
    shot_timeout = Column(Float, nullable=False, default=DEFAULT_SHOT_TIMEOUT)

    image_base64 = Column(String, nullable=False)
    checked = Column(Boolean, nullable=False, default=False)

    # How the shot was adjudicated: "hit" / "miss" / "bystander" / "refunded" /
    # "invalidated", or null while it is still in the queue. Recorded so the
    # shooter's shot history can report what happened - target_user_id alone
    # can't tell a miss from a refund. "bystander" costs the ammo like a miss,
    # but says the photo caught somebody who isn't playing. "refunded" is an
    # admin's own call (nobody could read the shot); "invalidated" is the same
    # ammo-back outcome reached automatically, because the shooter was already
    # knocked out before this shot of theirs could be checked - see
    # UserInterface.clear_unchecked_shots.
    result = Column(String, nullable=True)

    location_context = Column(String, nullable=True)

    # Which way the shooter's phone was pointing when the photo was taken:
    # degrees clockwise from true north, or null when the device could not say
    # (no compass, permission refused, or an older shot taken before this was
    # recorded). Captured because it cannot be recovered afterwards; nothing
    # reads it yet - it is the input that turns a future engagement envelope
    # from a disc into a cone. See docs/roadmap.md R5b.
    heading = Column(Float, nullable=True)

    # AI review of the photo. Shown as tags under the image in the queue, and
    # -- when the game's toggle is on -- acted on automatically for the queue
    # head when confident enough (backend/shot_auto_actions.py); everything
    # ambiguous is still the admin's call.
    # State is null (never queued) / "pending" / "done" / "error".
    ai_review_state = Column(String, nullable=True)
    # The ShotVisionResult as JSON text, or the error message when the state is
    # "error". Text JSON matches how location_context is already stored.
    ai_review = Column(String, nullable=True)

    # The escalated second opinion (backend/shot_escalation.py): a stronger
    # model, shown the candidate list and their reference photos, asked which
    # player this is. Only reached when the cheap review above read too little
    # of the outfit to act on; an escalation in flight blocks the queue behind
    # it, exactly as an ambiguous head does.
    # State is null (never escalated) / "pending" / "done" / "error".
    ai_escalation_state = Column(String, nullable=True)
    # The verdict, its candidate list and the transcript as JSON text, or the
    # error message when the state is "error" -- same shape of storage as
    # ai_review above.
    ai_escalation = Column(String, nullable=True)

    # Free-text annotation from the admin explaining an adjudication. No game
    # logic reads this: it exists so the reasoning behind each verdict survives
    # for the offline replay harness (scripts/replay_shot_reviews.py).
    admin_notes = Column(String, nullable=True)

    # An appeal against the verdict, by either of the two people who were
    # actually there (roadmap R8). A shot is contested while appeal_state is
    # "open"; it stays checked=True throughout, so it can never re-enter the
    # auto-action drain (backend/shot_auto_actions.py reads only unchecked
    # shots) and jam the live queue behind a twenty-minute-old argument.
    # "upheld" / "rejected" are terminal: the admin's word ends the loop.
    #
    # Deliberately absent from ShotModel below: the frontend caches a shot
    # model permanently by id, and every one of these fields is mutable, so a
    # cached shot would show an appeal state that had since moved on. The admin
    # reads them through their own endpoint instead, as with the AI review.
    appeal_state = Column(String, nullable=True)
    # When the shot was first contested, whichever party got there first --
    # what the contested queue is ordered by.
    appealed_at = Column(Float, nullable=True)
    # One appeal per party per shot, each stating a reason from APPEAL_REASONS.
    shooter_appeal_reason = Column(String, nullable=True)
    target_appeal_reason = Column(String, nullable=True)


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

    # A display colour for the team - the spectator screen's dots and roster
    # (react-ui/src/SpectatorView.js) - drawn from TEAM_CHANNEL's palette and
    # pinned the first time the game's join codes are generated. It used to be
    # the hat colour every member of the team wore; since the sign-up rework
    # (roadmap R15) the hat is chosen per player by the allocator and this
    # constrains nobody's outfit. Stored rather than derived so that adding a
    # team never re-colours the others. None until join codes have been built.
    identity_colour = Column(String, nullable=True)


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

    # A player belongs to a game before they belong to a team (roadmap R15):
    # signing up through the game-wide join link claims an outfit in the game
    # with no team at all, and the team is scanned in at the door on the
    # night. Every writer that sets team_id sets this to the team's game too,
    # so the two never disagree; a player with a game and no team is one who
    # has signed up but not yet arrived.
    game_id = Column(UUIDType, ForeignKey("games.id"), nullable=True, index=True)
    game = relationship("Game", lazy="joined", foreign_keys=game_id)

    team_id = Column(UUIDType, ForeignKey("teams.id"))
    team = relationship(
        "Team", lazy="joined", foreign_keys=team_id, back_populates="users"
    )

    # One player per team is nominated at the door as its leader: the person
    # who is asked to check their team is properly equipped before the game
    # starts. It is a label and a checklist, not a permission - a leader can do
    # nothing in the app another player cannot.
    is_team_leader = Column(Boolean, nullable=False, default=False)

    num_bullets = Column(Integer, nullable=False, default=0)
    # A fresh player gets STARTING_HIT_POINTS, which _make_user passes
    # explicitly - it is the only place a User row is built. This default is
    # what a row written any other way would land with, and is left at one so
    # that a player conjured up outside that path is not silently armoured.
    hit_points = Column(Integer, nullable=False, default=1)
    shot_timeout = Column(Float, nullable=False, default=DEFAULT_SHOT_TIMEOUT)
    shot_damage = Column(Integer, nullable=False, default=1)

    # When this player last fired, in epoch seconds, so the server can refuse
    # a shot inside their own cooldown (M1.1) - a client-side timer is one
    # page reload away from being gone. Deliberately not derived from the
    # player's newest Shot.time_created: that is a DateTime with one-second
    # resolution, and a reset deletes the rows, which would hand everybody a
    # free shot. Null for a player who has not fired since the column arrived.
    last_shot_at = Column(Float, nullable=True)

    # The appeal budget (roadmap R8), mechanically ammo: spent when an appeal
    # is lodged, handed back when it is upheld, reset with the rest of a
    # player's stats in AdminInterface.reset_game.
    appeals_remaining = Column(Integer, nullable=False, default=APPEALS_PER_GAME)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_timestamp = Column(Float, nullable=True)
    # The browser's own estimate of how good that fix is: the radius in metres
    # of the 95% confidence circle (`position.coords.accuracy`). Null when the
    # fix predates this being recorded. Like Shot.heading, captured now and
    # consumed by nothing yet. See docs/roadmap.md R5a.
    location_accuracy = Column(Float, nullable=True)

    time_of_death = Column(Float, nullable=True)
    "Timestamp at which this user transitions from dying to dead"

    # The radar card (M6.1): the epoch second at which the holder stops being
    # able to see where everybody else last was. Null, or a moment in the
    # past, means no radar - so it expires by itself and nothing has to tidy
    # it up, and a reset that clears the items leaves nothing behind either.
    radar_until = Column(Float, nullable=True)

    # The early circle-warning card (M6.2), the same shape: the epoch second
    # at which the holder stops seeing the next circle before it is announced.
    # Null or past means no warning.
    circle_warning_until = Column(Float, nullable=True)

    # The player's identity slot (backend/identity/): a member of
    # default_scheme().usable_slots() that determines the canonical colour
    # code they're assigned to wear. None means this player has no identity
    # assignment yet.
    identity_slot = Column(Integer, nullable=True)
    # A sparse {channel_name: label_or_null} diff against the slot's canonical
    # codeword, recording what the player actually wears when it differs from
    # the assignment. Stored as JSON text, same pattern as Shot.ai_review;
    # null means no overrides. Only meaningful when identity_slot is set.
    identity_overrides = Column(String, nullable=True)
    # The colours the player declared they own, {channel_name: [label, ...]}
    # as JSON text, same pattern as identity_overrides. Null before they pick.
    identity_wardrobe = Column(String, nullable=True)

    # The kit check taken at the door (backend/reference_photos.py): a photo of
    # the player in the outfit they turned up in, run through the same vision
    # pipeline a real shot uses. Same columns as Shot's, for the same reasons -
    # the image is a base64 data URL, the review is JSON text (or the error
    # message when the state is "error"), and the state is null (never queued)
    # / "pending" / "done" / "error". Never exposed on UserModel: the photo is
    # of an identifiable person and travels only through the admin endpoints.
    reference_photo_base64 = Column(String, nullable=True)
    reference_review_state = Column(String, nullable=True)
    reference_review = Column(String, nullable=True)

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


class UserAlias(Base):
    """Redirects a stray session cookie to the surviving ``User`` it was
    merged into (``AdminInterface.merge_user``) - the repair for a player who
    joined on a second phone or cleared their cookies. ``get_user_id``
    resolves every request's cookie UUID through this table, so a merge takes
    effect on the stray's very next request with no cookie of their own to
    change.
    """

    __tablename__ = "user_aliases"

    session_id = Column(UUIDType, primary_key=True)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False, index=True)


class ItemType(str, enum.Enum):
    AMMO = "ammo"
    MEDPACK = "medpack"
    ARMOUR = "armour"
    WEAPON = "weapon"
    # The two experimental items. An Enum column is a VARCHAR with no check
    # constraint, so a new member needs no migration; their handlers are not
    # written yet, and until they are `do_item_actions` raises
    # NotImplementedError - a RuntimeError, so a scan is refused with a 403.
    RADAR = "radar"
    CIRCLE_WARNING = "circle_warning"


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

    # The shot this message is about, when it is about one. The private
    # "you were hit" line carries it so the line itself can be the way in to
    # the shot - and to appealing it - rather than making the player go
    # looking. Null for every message that is not about a shot.
    shot_id = Column(UUIDType, ForeignKey("shots.id"), index=True, nullable=True)

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


class RevokedBatch(Base):
    """A print run that has been withdrawn, and so no longer collectable.

    A code is an HMAC over its payload and nothing else, which is what lets a
    card be printed on Thursday for a server that is deployed on Friday - and
    is equally why a printed code cannot be recalled. Rotating ``SECRET_KEY``
    would withdraw everything at once, the team cards included. So every code
    minted carries a ``batch`` (:class:`backend.items.ItemModel`), and
    withdrawing one is a row here: at 16:00 the sandbox's wall posters stop
    working while the game's own cards, minted as "game", carry on.

    The row's presence is the whole of the state, so un-withdrawing is a
    delete. A code minted before batches existed has no batch at all and can
    never be withdrawn this way - which is the right answer, since there is
    nothing to name it by.
    """

    __tablename__ = "revoked_batches"

    batch = Column(String, primary_key=True, nullable=False)
    revoked_at = Column(DateTime, server_default=func.now())


class Drop(Base):
    """A crate the courier has put on the ground (M4.3).

    One row per crate, so several can be out at once and each is cleared on
    its own when somebody claims it. That is the whole reason this is a table
    rather than three more columns on ``Game``: the single ``drop_circle_*``
    triplet that predates it can only ever hold the newest crate, so putting
    out a second one silently took the first off every map while the crate was
    still sitting under a bench.

    The row *is* the crate. Clearing one deletes it, rather than marking it
    collected: the ticker line announcing the claim is the record of what
    happened, and a table of crates that are no longer there is a thing the
    courier's list would then have to filter.
    """

    __tablename__ = "drops"

    id = Column(UUIDType, primary_key=True, nullable=False, default=get_uuid)

    game_id = Column(UUIDType, ForeignKey("games.id"), nullable=False)
    game = relationship("Game", lazy="joined", back_populates="drops")

    lat = Column(Float, nullable=False)
    long = Column(Float, nullable=False)
    radius = Column(Float, nullable=False)

    # An epoch second, like Game.courier_timestamp and unlike Shot's DateTime:
    # it is shown as a wall-clock time on the courier's own phone, and a number
    # the browser can hand straight to Date() cannot pick up a timezone on the
    # way.
    time_created = Column(Float, nullable=False, default=time.time)


class DropModel(pydantic.BaseModel):
    id: UUID
    lat: float
    long: float
    radius: float
    time_created: float

    model_config = pydantic.ConfigDict(from_attributes=True, extra="forbid")


class GameModel(pydantic.BaseModel):
    id: UUID

    teams: List["TeamModel"]
    ticker_update_tag: int
    active: bool
    ai_shot_review_enabled: bool = False
    ai_auto_actions_enabled: bool = False
    ai_escalation_enabled: bool = True
    ai_resolve_everything_enabled: bool = False

    exclusion_circle_lat: Optional[float] = None
    exclusion_circle_long: Optional[float] = None
    exclusion_circle_radius: Optional[float] = None

    next_circle_lat: Optional[float] = None
    next_circle_long: Optional[float] = None
    next_circle_radius: Optional[float] = None

    drop_circle_lat: Optional[float] = None
    drop_circle_long: Optional[float] = None
    drop_circle_radius: Optional[float] = None

    # Every crate still on the ground (M4.3). The drop_circle_* triplet above
    # is the admin's own map-placed drop and is unrelated; both are drawn the
    # same way.
    drops: List["DropModel"] = []

    next_event_kind: Optional[str] = None
    next_event_at: Optional[float] = None
    next_event_note: Optional[str] = None

    courier_lat: Optional[float] = None
    courier_long: Optional[float] = None
    courier_timestamp: Optional[float] = None
    courier_accuracy: Optional[float] = None

    next_circle_public: bool = False

    model_config = pydantic.ConfigDict(from_attributes=True, extra="forbid")


class UserModel(pydantic.BaseModel):
    id: UUID
    name: Optional[str] = None

    team_id: Optional[UUID] = None
    is_team_leader: bool = False

    num_bullets: int
    hit_points: int
    shot_timeout: float
    shot_damage: int

    # The epoch second at which this player may fire again: last_shot_at plus
    # their own shot_timeout, or None when they are free to fire now. Derived
    # rather than stored, so the phone counts down to the server's answer
    # instead of running its own timer - a reload then comes back still
    # cooling. Not an ORM attribute; get_user_model fills it in.
    next_shot_at: Optional[float] = None

    time_of_death: Optional[float] = None

    # Rides out with the rest so the phone knows its radar is running without
    # asking: scanning the card is a write on this player, so the "user" SSE
    # event they already listen to carries it. RadarLayer.js is what polls,
    # and only while this says it is worth polling.
    radar_until: Optional[float] = None

    # Rides the SSE "user" payload beside num_bullets, so a player weighing up
    # an appeal always has the count in front of them without a poll
    appeals_remaining: int = APPEALS_PER_GAME

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_timestamp: Optional[float] = None
    location_accuracy: Optional[float] = None

    # The game the player signed up to - set before, and independently of,
    # team_id (see User.game_id)
    game_id: Optional[UUID] = None
    active: bool
    state: UserState

    # This is retrieved from the team too
    team_name: Optional[str] = None

    identity_slot: Optional[int] = None
    identity_overrides: Optional[str] = None
    identity_wardrobe: Optional[str] = None

    # {channel_name: {"colour", "hex"}} for the garments the player supplies
    # themselves (t-shirt, trousers), and the same again for the hat and
    # armband handed out at the door, both decoded from identity_slot +
    # identity_overrides. None until an outfit is picked. Neither is an ORM
    # attribute, so get_user_model fills them in by hand after
    # model_validate.
    outfit_wardrobe: Optional[Dict[str, Dict[str, Optional[str]]]] = None
    outfit_provided: Optional[Dict[str, Dict[str, Optional[str]]]] = None

    # What the game says is coming next, copied off the player's Game so that
    # the "user" SSE event every phone already listens to carries it (M3.1).
    # Null when nothing is cued. Not ORM attributes either, so get_user_model
    # fills them in after model_validate, like the two above.
    next_event_kind: Optional[str] = None
    next_event_at: Optional[float] = None
    next_event_note: Optional[str] = None

    model_config = pydantic.ConfigDict(from_attributes=True, extra="forbid")


class TeamModel(pydantic.BaseModel):
    id: UUID
    name: str
    game_id: UUID
    users: List[UserModel]
    identity_colour: Optional[str] = None

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
    shot_timeout: float

    location_context: Optional[str] = None
    heading: Optional[float] = None

    ai_review_state: Optional[str] = None
    ai_review: Optional[str] = None

    ai_escalation_state: Optional[str] = None
    ai_escalation: Optional[str] = None

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
