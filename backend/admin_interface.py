import asyncio
import json
import logging
import os
import time
from collections import namedtuple
from enum import Enum
from typing import List
from typing import Optional
from typing import Tuple
from uuid import UUID
from uuid import uuid4 as get_uuid

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import next_event
from . import ticker_message_dispatcher as tk
from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event
from .circles import PlannedCircle
from .circles import circle_plan
from .circles import planned_circle
from .circles import trigger_circle_update
from .database_scope_provider import DatabaseScopeProvider
from .image_processing import annotate_image_with_stats
from .image_processing import downscale_jpeg
from .image_processing import draw_cross_on_image
from .item_actions import describe_item
from .items import ItemModel
from .join_codes import JoinCodeModel
from .model import AI_REVIEW_STATE_DONE
from .model import AI_REVIEW_STATE_ERROR
from .model import AI_REVIEW_STATE_PENDING
from .model import APPEALS_PER_GAME
from .model import BASIC_WEAPON
from .model import DEFAULT_SHOT_TIMEOUT
from .model import STARTING_HIT_POINTS
from .model import Drop
from .model import DropModel
from .model import Game
from .model import GameModel
from .model import Item
from .model import ItemType
from .model import KnownCode
from .model import RevokedBatch
from .model import Shot
from .model import ShotModel
from .model import Team
from .model import TeamModel
from .model import TickerEntry
from .model import User
from .model import UserAlias
from .model import UserModel
from .shot_identification import identification_payload
from .ticker import Ticker
from .user_interface import APPEAL_OPEN
from .user_interface import APPEAL_REJECTED
from .user_interface import APPEAL_UPHELD
from .user_interface import UserInterface
from .utils import add_params_to_url

logger = logging.getLogger(__name__)


# One size, used by all three faces of the spectator screen. The takeover
# frame is 600x900, so anything smaller upscales and goes soft on a
# television; the sidebar's small thumbnails just downsample in the browser.
# At quality 70 this is ~100KB, fetched once per shot and then held.
THUMBNAIL_MAX_DIMENSION = 900

AdminScopeWrapper = DatabaseScopeProvider("admin")
db_scoped = AdminScopeWrapper.db_scoped


# What the auto-action drain needs to know about the head of a game's shot
# queue -- deliberately not a ShotModel, so image_base64 is never loaded.
# ``time_created`` is here because identification scores a shot as of the
# moment it was taken (backend.shot_identification.shot_epoch): leaving it out
# of the projection is how a perfectly good row arrives here with no time on
# it, and the drain re-runs on shots that have sat in the queue for hours.
QueueHead = namedtuple(
    "QueueHead",
    [
        "id",
        "time_created",
        "user_id",
        "ai_review_state",
        "ai_review",
        "ai_escalation_state",
        "ai_escalation",
        "location_context",
    ],
)


# One row of the spectator feed. Superset of QueueHead: it carries what the
# screen shows (when, who, the verdict so far) as well as what
# _ai_review_payload needs, and like QueueHead it never loads image_base64.
RecentShotRow = namedtuple(
    "RecentShotRow",
    [
        "id",
        "time_created",
        "user_id",
        "target_user_id",
        "checked",
        "result",
        "ai_review_state",
        "ai_review",
        "ai_escalation_state",
        "ai_escalation",
        "location_context",
    ],
)


def _ai_review_payload(shot, users: List[UserModel]) -> dict:
    """One shot's stored review, its escalation, and who the reading looks like.

    ``shot`` needs only the review/escalation columns plus ``user_id`` and
    ``location_context`` -- a ``QueueHead`` satisfies it as well as an ORM
    ``Shot`` does, which is what lets the spectator feed build many of these
    from one columns-only query.

    ``users`` is passed in rather than looked up so a caller doing a whole
    game's worth resolves the roster once instead of per shot.
    """
    review = _stored_json(shot.ai_review)

    # Scored here rather than stored with the review: an outfit correction
    # made after the review must change who this reading looks like,
    # without rewriting the reading itself.
    identification = None
    if shot.ai_review_state == AI_REVIEW_STATE_DONE and isinstance(review, dict):
        identification = identification_payload(shot, users, review)

    return {
        "state": shot.ai_review_state,
        "review": review,
        "identification": identification,
        "escalation_state": shot.ai_escalation_state,
        "escalation": _stored_json(shot.ai_escalation),
    }


def _stored_json(raw: Optional[str]) -> Optional[dict]:
    """One of the review columns, decoded for the admin API.

    ``None`` stays None; an "error" state stores a plain message rather than
    JSON, which comes back wrapped as ``{"error": ...}`` so the frontend has
    one shape to render.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return {"error": raw}


def _reference_verdict(state: Optional[str], review: Optional[str]) -> dict:
    """The kit check's headline, pulled out of a stored reference review.

    Null throughout unless the review completed and carried an identification
    section: a pending, errored or pre-identification review has no verdict.

    ``confident`` and ``readable_channels`` ride along with the name because a
    roster row that says "recognised" without them says it just as loudly for a
    coin toss between two players, or for a photograph nothing was readable in
    (see :func:`backend.reference_photos._identification`).
    """
    blank = {
        "matches_expected": None,
        "top_name": None,
        "top_probability": None,
        "confident": None,
        "readable_channels": None,
    }
    if state != AI_REVIEW_STATE_DONE or not review:
        return blank
    try:
        identification = (json.loads(review) or {}).get("identification")
    except ValueError:
        return blank
    if not isinstance(identification, dict):
        return blank

    ranked = identification.get("ranked") or [{}]
    return {
        "matches_expected": identification.get("matches_expected"),
        "top_name": ranked[0].get("name"),
        "top_probability": ranked[0].get("probability"),
        "confident": identification.get("confident"),
        "readable_channels": identification.get("readable_channels"),
    }


# Verdicts that come to the same thing for an appellant: the shot hit no player
# either way, so re-ruling one as the other overturns nothing.
_NO_HIT_VERDICTS = frozenset({"miss", "bystander"})


def _same_appeal_outcome(old_result, new_result) -> bool:
    return old_result == new_result or (
        old_result in _NO_HIT_VERDICTS and new_result in _NO_HIT_VERDICTS
    )


# How each verdict reads in the public line announcing an overturned one.
_APPEAL_RESULT_WORDS = {
    "hit": "a hit",
    "miss": "a miss",
    "bystander": "a bystander",
    "refunded": "unreadable",
}


# A broadcasting courier posts a fix about once a second (M4.1), and every
# announcement wakes the circle stream of every phone in the game. The
# position is written on every post, but the fan-out is throttled to this, so
# a player's map is at most this stale while the courier is walking - about
# seven metres at walking pace, which is inside the accuracy of the fix
# itself. A courier fix is not a shot.
COURIER_ANNOUNCE_INTERVAL_S = 5.0

# game id -> when its courier position was last announced. In-process and
# deliberately not durable: losing it costs one extra announcement.
_courier_announced_at: dict = {}


def _parse_or_none(parser, data: str):
    """Try one of the two code readers, or return None if this is not one.

    Identifying a code means offering the string to each reader in turn, so
    every way a reader can say "not mine" -- bad base64, JSON that is not a
    code, a URL carrying the other kind's query parameter -- has to come back
    as a miss rather than an exception.
    """
    try:
        return parser(data)
    except (ValueError, KeyError, TypeError):
        return None


def _scan_rule(item: ItemModel) -> str:
    """How many times a card can be scanned, in the words on the poster."""
    if item.unlimited:
        return "Unlimited - the same player can scan it over and over (a poster)"
    if item.collected_only_once:
        return "Once ever, by the first player to scan it"
    if item.collected_as_team:
        return "Once per team"
    return "Once per player"


class CircleTypes(str, Enum):
    EXCLUSION = "EXCLUSION"
    NEXT = "NEXT"
    BOTH = "BOTH"
    DROP = "DROP"


# What the ticker says for each circle type, keyed by whether the circle was
# cleared (True) or placed (False). None says nothing at all: only a claimed
# supply drop is worth announcing when a circle goes away
CIRCLE_TICKER_MESSAGES = {
    CircleTypes.EXCLUSION: {
        False: tk.TickerMessageType.ADMIN_SET_CIRCLE_EXCLUSION,
        True: None,
    },
    # NEXT says nothing either way since M6.2: the circle it places is not
    # public until it is cued, so announcing it would be announcing something
    # nobody but an early-warning holder can see.
    CircleTypes.NEXT: {
        False: None,
        True: None,
    },
    CircleTypes.BOTH: {
        False: tk.TickerMessageType.ADMIN_SET_CIRCLE_BOTH,
        True: None,
    },
    CircleTypes.DROP: {
        False: tk.TickerMessageType.ADMIN_SET_CIRCLE_DROP,
        True: tk.TickerMessageType.ADMIN_CLEARED_CIRCLE_DROP,
    },
}

# What the ticker says when a countdown starts, by the kind being counted down
# to (backend/next_event.py). Same shape as CIRCLE_TICKER_MESSAGES above.
CUE_TICKER_MESSAGES = {
    next_event.KIND_CIRCLE: tk.TickerMessageType.CUE_CIRCLE,
    next_event.KIND_DROP: tk.TickerMessageType.CUE_DROP,
}

# What a drop's announcement says instead when the admin typed what is in it.
# Worth saying twice - it is the whole reason anybody runs for a drop, and the
# ticker is read by people who are not looking at the strip at the top of
# their screen.
CUE_TICKER_MESSAGES_WITH_NOTE = {
    next_event.KIND_DROP: tk.TickerMessageType.CUE_DROP_WITH_CONTENTS,
}


def _countdown_words(seconds: float) -> str:
    """How long is left, said the way somebody would say it out loud.

    The ticker line is read once, in passing, by somebody walking: "10
    minutes" is what that wants, not "600s" and not "09:58".
    """
    if seconds < 90:
        return f"{round(seconds)} seconds"
    minutes = round(seconds / 60)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


class AdminInterface:
    def __init__(self, session=None) -> None:
        self._session: Session = session

    @db_scoped
    def _get_user_orm(self, user_id) -> User:
        g = self._session.query(User).filter_by(id=user_id).first()
        if not g:
            raise HTTPException(404, f"User {user_id} not found")
        return g

    @db_scoped
    def _get_game_orm(self, game_id) -> Game:
        g = self._session.query(Game).filter_by(id=game_id).first()
        if not g:
            raise HTTPException(404, f"Game {game_id} not found")
        return g

    @db_scoped
    def _get_team_orm(self, team_id) -> Team:
        t = self._session.query(Team).filter_by(id=team_id).first()
        if not t:
            raise HTTPException(404, f"Team {team_id} not found")
        return t

    @db_scoped
    def _get_shot_orm(self, shot_id) -> Shot:
        s = self._session.get(Shot, shot_id)
        if not s:
            raise HTTPException(404, f"Shot {shot_id} not found")
        return s

    @db_scoped
    def get_shot_model(self, shot_id) -> ShotModel:
        s = self._get_shot_orm(shot_id)
        return ShotModel.model_validate(s)

    @db_scoped
    def get_shot_game_id(self, shot_id) -> UUID:
        """Just the game a shot belongs to, without loading the image.
        404s if the shot is unknown."""
        row = self._session.query(Shot.game_id).filter_by(id=shot_id).first()
        if not row:
            raise HTTPException(404, f"Shot {shot_id} not found")
        return row[0]

    @db_scoped
    def get_shot_image_base64(self, shot_id) -> str:
        """Just the image for a shot, without loading the whole model.

        The vision-images endpoint only needs the base64 data; loading a
        ShotModel would also instantiate the GameModel via ShotModel.game
        and its teams/users.
        404s if the shot is unknown.
        """
        row = self._session.query(Shot.image_base64).filter_by(id=shot_id).first()
        if not row:
            raise HTTPException(404, f"Shot {shot_id} not found")
        return row[0]

    def _queue_query(self):
        """The unchecked-shot column projection shared by get_queue_head/
        get_queue_entry/get_queue -- never image_base64. Callers add their own
        filter (game_id, or shot id). Ordered by (time_created, id): timestamps
        have 1s resolution, so the id breaks ties deterministically.
        """
        return (
            self._session.query(
                Shot.id,
                Shot.time_created,
                Shot.user_id,
                Shot.ai_review_state,
                Shot.ai_review,
                Shot.ai_escalation_state,
                Shot.ai_escalation,
                Shot.location_context,
            )
            .filter_by(checked=False)
            .order_by(Shot.time_created, Shot.id)
        )

    @db_scoped
    def get_queue_head(self, game_id: UUID) -> Optional[QueueHead]:
        """The oldest unchecked shot in a game, or None if the queue is empty."""
        row = self._queue_query().filter(Shot.game_id == game_id).first()
        return QueueHead(*row) if row else None

    @db_scoped
    def get_queue_entry(self, shot_id: UUID) -> Optional[QueueHead]:
        """One shot's queue row, or None if it does not exist or is checked.
        Used by backend.shot_auto_actions.escalate_early to act on a shot
        before it reaches the head.
        """
        row = self._queue_query().filter(Shot.id == shot_id).first()
        return QueueHead(*row) if row else None

    @db_scoped
    def get_queue(self, game_id: UUID) -> List[QueueHead]:
        """Every unchecked shot of a game, oldest first -- for the backlog
        sweep (backend.shot_auto_actions.escalate_backlog).
        """
        return [
            QueueHead(*row)
            for row in self._queue_query().filter(Shot.game_id == game_id).all()
        ]

    @db_scoped
    def get_games(self) -> List[GameModel]:
        logger.info("AdminInterface - get_games")
        return [GameModel.model_validate(g) for g in self._session.query(Game).all()]

    @db_scoped
    def get_user_model(self, user_id: UUID) -> UserModel:
        return UserModel.model_validate(self._get_user_orm(user_id))

    @db_scoped
    def get_team_model(self, team_id: UUID) -> TeamModel:
        return TeamModel.model_validate(self._get_team_orm(team_id))

    @db_scoped
    def get_game_model(self, game_id: UUID) -> GameModel:
        return GameModel.model_validate(self._get_game_orm(game_id))

    @db_scoped
    def get_teams_for_game(self, game_id: UUID) -> List[TeamModel]:
        """Teams of a game, oldest first (with id as a same-second tiebreak) -
        a stable order for the join-code partition. 404s if the game doesn't
        exist.
        """
        self._get_game_orm(game_id)  # 404 if the game doesn't exist

        teams = (
            self._session.query(Team)
            .filter_by(game_id=game_id)
            .order_by(Team.time_created, Team.id)
            .all()
        )
        return [TeamModel.model_validate(t) for t in teams]

    @db_scoped
    def get_users_for_game(self, game_id: UUID) -> List[UserModel]:
        """Every user in ``game_id`` - in a team or not: a player who signed
        up through the game link and has not scanned a team in yet is still
        on the roster, and still holds an outfit. 404s if the game doesn't
        exist. Used by the identity admin report/suggest logic
        (backend/identity_admin.py), which needs the whole game's roster to
        compute pairwise distances and slot uniqueness, and by shot
        identification, which filters the team-less out itself
        (``shot_identification.rank_candidates``).
        """
        self._get_game_orm(game_id)  # 404 if the game doesn't exist

        users = self._session.query(User).filter(User.game_id == game_id).all()
        return [UserModel.model_validate(u) for u in users]

    @db_scoped
    def get_users(self, team_id: UUID = None, game_id: UUID = None) -> List[UserModel]:
        logger.info("AdminInterface - get_users")

        q = self._session.query(User)

        if team_id:
            q.filter_by(team_id=team_id)
        if game_id:
            q.filter_by(game_id=game_id)

        return [UserModel.model_validate(g) for g in q.all()]

    @db_scoped
    def create_game(self, game_id: Optional[UUID] = None) -> UUID:
        """Make a game, optionally at a caller-chosen id.

        ``game_id`` exists for fixtures. A generated sample game whose id is
        minted afresh on every reset cannot have its join QR codes printed in
        advance, because the codes encode the ids -- so the fixture derives
        stable ids from its seed and passes them in here. A real game never
        supplies one and gets the usual random id.
        """
        logger.info("AdminInterface - create_game")
        g = Game(id=game_id) if game_id is not None else Game()
        self._session.add(g)
        self._session.commit()

        return g.id

    @db_scoped
    def set_courier_location(
        self,
        game_id: UUID,
        lat: float,
        long: float,
        accuracy: Optional[float] = None,
    ):
        """Record where the courier is now (M4.1).

        Called about once a second by /admin/courier while somebody is walking
        a crate to a drop. The write happens every time; the announcement is
        throttled to COURIER_ANNOUNCE_INTERVAL_S, because the alternative is
        waking every player's circle stream once a second for a dot that moves
        a metre and a half.
        """
        game: Game = self._get_game_orm(game_id)

        game.courier_lat = lat
        game.courier_long = long
        game.courier_timestamp = time.time()
        game.courier_accuracy = accuracy

        self._session.commit()

        now = time.time()
        last = _courier_announced_at.get(game_id)
        if last is None or now - last >= COURIER_ANNOUNCE_INTERVAL_S:
            _courier_announced_at[game_id] = now
            trigger_circle_update(game_id)

    @db_scoped
    def clear_courier(self, game_id: UUID):
        """The courier has stopped broadcasting: put the dot away.

        Always announces, throttle or no throttle - this one is the difference
        between a courier who is somewhere and a courier who is nowhere, and a
        dot left on a map for five seconds after the crate is down is the one
        staleness that actually misleads.
        """
        game: Game = self._get_game_orm(game_id)

        game.courier_lat = None
        game.courier_long = None
        game.courier_timestamp = None
        game.courier_accuracy = None

        self._session.commit()

        _courier_announced_at.pop(game_id, None)
        trigger_circle_update(game_id)

    @db_scoped
    def place_drop(self, game_id: UUID, lat: float, long: float, radius: float) -> UUID:
        """Put a crate on the ground where the courier is standing (M4.3).

        A row rather than the ``drop_circle_*`` triplet, so that a second crate
        does not take the first off the map: see :class:`backend.model.Drop`.
        The announcement is the same line placing a DROP circle has always
        fired, because to a player it is the same event.
        """
        logger.info("AdminInterface - place_drop %s", game_id)

        # Checked rather than assumed: the drop hangs off a game, and a 404
        # here is better than a foreign key error on commit
        self._get_game_orm(game_id)

        drop = Drop(game_id=game_id, lat=lat, long=long, radius=radius)
        self._session.add(drop)
        self._session.commit()

        drop_id = drop.id

        tk.send_ticker_message(
            tk.TickerMessageType.ADMIN_SET_CIRCLE_DROP,
            {},
            game_id=game_id,
            session=self._session,
        )
        trigger_circle_update(game_id)

        return drop_id

    @db_scoped
    def clear_drop(self, drop_id: UUID):
        """Somebody has claimed a crate: take it off every map (M4.3).

        Deleting the row is the whole of it - the ticker line is what records
        that the drop was claimed, and a collected crate has nothing left to
        say to the courier's list.
        """
        logger.info("AdminInterface - clear_drop %s", drop_id)

        drop: Drop = self._session.query(Drop).filter_by(id=drop_id).first()
        if drop is None:
            raise HTTPException(404, f"Drop {drop_id} not found")

        game_id = drop.game_id
        self._session.delete(drop)
        self._session.commit()

        tk.send_ticker_message(
            tk.TickerMessageType.ADMIN_CLEARED_CIRCLE_DROP,
            {},
            game_id=game_id,
            session=self._session,
        )
        trigger_circle_update(game_id)

    @db_scoped
    def get_drops(self, game_id: UUID) -> List[DropModel]:
        """Every crate still on the ground in this game, oldest first."""
        return [
            DropModel.model_validate(drop)
            for drop in self._session.query(Drop)
            .filter_by(game_id=game_id)
            .order_by(Drop.time_created)
        ]

    @db_scoped
    def set_circles(
        self, game_id: UUID, name: CircleTypes, lat: float, long: float, radius: float
    ):
        logger.info("AdminInterface - set_circles")
        game: Game = self._get_game_orm(game_id)

        # Clearing a circle passes no coordinates, so it gets a different
        # announcement to placing one - or none at all
        cleared = lat is None or long is None or radius is None

        if name == CircleTypes.EXCLUSION:
            game.exclusion_circle_lat = lat
            game.exclusion_circle_long = long
            game.exclusion_circle_radius = radius
        elif name == CircleTypes.NEXT:
            game.next_circle_lat = lat
            game.next_circle_long = long
            game.next_circle_radius = radius
            # Private again (M6.2), placed or cleared: an admin who moves the
            # circle mid-countdown must take the old one off every phone
            # rather than leave a public circle sitting somewhere it is not.
            game.next_circle_public = False
        elif name == CircleTypes.BOTH:
            game.exclusion_circle_lat = lat
            game.exclusion_circle_long = long
            game.exclusion_circle_radius = radius
            game.next_circle_lat = lat
            game.next_circle_long = long
            game.next_circle_radius = radius
            # BOTH puts the next circle exactly where the exclusion circle
            # everybody can already see is, so there is nothing left to hide.
            game.next_circle_public = True
        elif name == CircleTypes.DROP:
            game.drop_circle_lat = lat
            game.drop_circle_long = long
            game.drop_circle_radius = radius
        else:
            raise HTTPException(400, f"Invalid circle name {name}")

        message_type = CIRCLE_TICKER_MESSAGES[CircleTypes(name)][cleared]

        self._session.commit()

        # Announce the circle change, if this one is worth announcing
        if message_type is not None:
            tk.send_ticker_message(
                message_type,
                {},
                game_id=game_id,
                session=self._session,
            )

        # Trigger a circle update
        trigger_circle_update(game_id)

    def _game_user_ids(self, game_id: UUID) -> List[UUID]:
        """Everybody in a game, whether or not they are in a team yet.

        On ``User.game_id`` rather than by walking the teams the way
        :meth:`set_game_active` does: a player who has signed up through the
        game-wide link and has not been handed a team is exactly who the
        waiting page - and so the countdown strip - is for.
        """
        return [
            row[0]
            for row in self._session.query(User.id).filter(User.game_id == game_id)
        ]

    @staticmethod
    def _clear_cue(game: Game) -> None:
        """Wipe a game's cue. All three columns together, always: null
        ``next_event_at`` is what "nothing is cued" means everywhere else."""
        game.next_event_kind = None
        game.next_event_at = None
        game.next_event_note = None

    @staticmethod
    def _arm_planned_circle(game: Game) -> Optional[PlannedCircle]:
        """Place the circle the plan says is next, privately.

        The whole point of the plan (`backend/circles.py`): NEXT is placed
        long before anybody presses a countdown, so the early-warning card
        always has something to reveal and the admin cannot neuter it by
        forgetting a step. Silent by design - placing NEXT announces nothing,
        which is what makes it worth knowing.

        Returns the entry it armed, or None when the plan has run out or the
        environment has not supplied that circle (`LANDMARK_<name>` or
        `CIRCLE_RADIUS_<name>` unset): both leave the circles exactly as they
        are, for the admin to place by hand.
        """
        planned = planned_circle(game.circle_plan_index)

        if planned is None:
            logger.info("Game %s has reached the end of the circle plan", game.id)
            return None
        if not planned.known:
            logger.warning(
                "Planned circle %s is not fully configured - place it by hand",
                planned.name,
            )
            return None

        game.next_circle_lat = planned.lat
        game.next_circle_long = planned.long
        game.next_circle_radius = planned.radius_km
        game.next_circle_public = False

        logger.info(
            "Armed planned circle %s (%s km) for game %s",
            planned.name,
            planned.radius_km,
            game.id,
        )
        return planned

    @db_scoped
    def arm_planned_circle(
        self, game_id: UUID, index: Optional[int] = None
    ) -> Optional[PlannedCircle]:
        """Place a plan circle on the admin's say-so: re-arming the one the
        game is on, or skipping to another one. The pointer follows, so the
        plan carries on from wherever it is put."""
        logger.info("AdminInterface - arm_planned_circle %s/%s", game_id, index)

        game: Game = self._get_game_orm(game_id)

        if index is not None:
            if planned_circle(index) is None:
                raise HTTPException(404, f"No circle {index} in the plan")
            game.circle_plan_index = index

        armed = self._arm_planned_circle(game)

        self._session.commit()
        trigger_circle_update(game_id)

        return armed

    @db_scoped
    def step_back_circle_plan(self, game_id: UUID) -> Optional[PlannedCircle]:
        """Undo a circle that closed by mistake: the play area goes back to
        how it looked a minute ago.

        A countdown that fires early, or a **Close the circle now** pressed by
        a thumb, cannot be taken back by moving the pointer alone - that
        re-places NEXT correctly but leaves the exclusion circle where the
        promotion put it, so the players are still held inside a circle that
        was never meant to close and nobody has told them otherwise. So this
        steps both back together: the pointer to the entry before it, NEXT
        re-placed privately from that entry, and the exclusion circle restored
        from the entry *before that* - cleared outright when there isn't one,
        which is the first circle of the night not yet having closed.

        It overwrites an exclusion circle placed by hand, because the plan is
        what it is stepping back to, and it announces itself: somebody is
        running for a boundary that has just moved away from them.
        """
        logger.info("AdminInterface - step_back_circle_plan %s", game_id)

        game: Game = self._get_game_orm(game_id)

        if game.circle_plan_index <= 0:
            raise HTTPException(400, "The circle plan is already at its first circle")

        game.circle_plan_index -= 1
        self._arm_planned_circle(game)

        previous = planned_circle(game.circle_plan_index - 1)
        restored = previous if previous is not None and previous.known else None

        game.exclusion_circle_lat = restored.lat if restored else None
        game.exclusion_circle_long = restored.long if restored else None
        game.exclusion_circle_radius = restored.radius_km if restored else None

        self._session.commit()

        tk.send_ticker_message(
            tk.TickerMessageType.CIRCLE_REOPENED,
            {},
            game_id=game_id,
            session=self._session,
        )
        trigger_circle_update(game_id)

        return restored

    @staticmethod
    def circle_plan() -> List[PlannedCircle]:
        """The whole plan, so the admin page can say what is coming."""
        return circle_plan()

    @db_scoped
    def cue_next_event(
        self,
        game_id: UUID,
        kind: str,
        seconds: float,
        note: Optional[str] = None,
    ) -> float:
        """Start the countdown to the next circle or the next drop.

        Returns the deadline it set, in epoch seconds. Replaces whatever was
        cued before, cue and timer together - there is only ever one thing
        coming next.

        Zero is allowed, and means now: the timer clamps its delay at zero
        (`next_event.arm`), so a circle cued at zero is announced and closed
        in the same breath. That is the admin's "do it now", and it goes
        through the cue rather than round it so that the announcement, the
        spent early-warning cards and the plan stepping on all still happen.

        The timer is armed here rather than in the route for the usual reason
        (``CLAUDE.md``: announce beside the state change): the route is not the
        only caller, and a cue written with no clock behind it is a countdown
        that reaches zero and does nothing.
        """
        logger.info("AdminInterface - cue_next_event %s/%s/%ss", game_id, kind, seconds)

        try:
            kind = next_event.NextEventKind(kind).value
        except ValueError:
            raise HTTPException(400, f"Unknown event kind {kind}")
        if seconds < 0:
            raise HTTPException(400, "A countdown cannot run backwards")

        game: Game = self._get_game_orm(game_id)
        deadline = time.time() + seconds

        game.next_event_kind = kind
        game.next_event_at = deadline
        game.next_event_note = note.strip() if note and note.strip() else None

        # Cueing the circle is what makes it public (M6.2) - "the circle
        # closes in ten minutes" is not an announcement anybody can act on
        # without being shown which circle.
        if kind == next_event.KIND_CIRCLE:
            game.next_circle_public = True
            # And every early-warning card in the game is spent with it: what
            # it bought was a head start on this announcement, and the
            # announcement has just happened (M6.2).
            self._session.query(User).filter_by(game_id=game_id).update(
                {"circle_warning_until": None}
            )

        user_ids = self._game_user_ids(game_id)

        self._session.commit()

        note = game.next_event_note
        message_type = CUE_TICKER_MESSAGES[kind]
        if note:
            message_type = CUE_TICKER_MESSAGES_WITH_NOTE.get(kind, message_type)

        tk.send_ticker_message(
            message_type,
            {"num": _countdown_words(seconds), "note": note},
            game_id=game_id,
            session=self._session,
        )

        for user_id in user_ids:
            trigger_update_event("user", user_id)

        # The circle the countdown is about has just become visible to
        # everybody (M6.2), so every open map has to refetch it
        if kind == next_event.KIND_CIRCLE:
            trigger_circle_update(game_id)

        next_event.arm(game_id, deadline)

        return deadline

    @db_scoped
    def cancel_cue(self, game_id: UUID) -> None:
        """Call the countdown off. The circle or drop it was counting down to
        is left exactly as it is - only the clock goes."""
        logger.info("AdminInterface - cancel_cue %s", game_id)

        game: Game = self._get_game_orm(game_id)
        if game.next_event_at is None:
            return

        self._clear_cue(game)
        user_ids = self._game_user_ids(game_id)

        self._session.commit()

        tk.send_ticker_message(
            tk.TickerMessageType.CUE_CANCELLED,
            {},
            game_id=game_id,
            session=self._session,
        )

        for user_id in user_ids:
            trigger_update_event("user", user_id)

        next_event.disarm(game_id)

    @db_scoped
    def fire_next_event(
        self, game_id: UUID, expected_at: Optional[float] = None
    ) -> bool:
        """Act on a game's cue because its moment has come. Returns whether
        anything happened.

        ``expected_at`` is the deadline the caller thinks it is firing.
        Checking it here is the double-firing guard: a timer that slept
        through a re-cue, or through an admin cancelling and starting again,
        finds a different deadline in the database and does nothing. The
        timers themselves are cancelled on a re-cue too
        (:func:`next_event.arm`), so this is the second line rather than the
        first - but it is the one that holds when the process restarted in
        between.
        """
        game: Game = self._get_game_orm(game_id)

        if game.next_event_at is None:
            logger.info("Game %s has no cue to fire", game_id)
            return False

        if (
            expected_at is not None
            and abs(game.next_event_at - expected_at) > next_event.DEADLINE_EPSILON_S
        ):
            logger.info(
                "Not firing game %s's cue: it was re-cued while the clock ran",
                game_id,
            )
            return False

        kind = game.next_event_kind
        logger.info("AdminInterface - fire_next_event %s (%s)", game_id, kind)

        if kind == next_event.KIND_CIRCLE:
            self.promote_next_circle(game_id)
            return True

        # A drop's zero is an announcement and nothing else (M3.3): the crate
        # is not on the map until the courier starts broadcasting from
        # /admin/courier (M4), so there is no circle to place here. Clearing
        # the cue is what stops thirty phones sitting at 00:00.
        self._clear_cue(game)
        user_ids = self._game_user_ids(game_id)

        self._session.commit()

        tk.send_ticker_message(
            tk.TickerMessageType.COURIER_SET_OFF,
            {},
            game_id=game_id,
            session=self._session,
        )

        for user_id in user_ids:
            trigger_update_event("user", user_id)
        return True

    @db_scoped
    def promote_next_circle(self, game_id: UUID) -> bool:
        """Make the announced next circle the one people have to be inside.

        Copies the next circle over the exclusion circle, clears the next
        circle and the cue, says so in the ticker and fires the circle event
        so every open map redraws.

        Returns False, having changed nothing but the cue, when there is no
        next circle to promote: an admin who cleared it while the clock ran
        must not have the play area silently blanked instead.
        """
        logger.info("AdminInterface - promote_next_circle %s", game_id)

        game: Game = self._get_game_orm(game_id)
        promoted = (
            game.next_circle_lat is not None
            and game.next_circle_long is not None
            and game.next_circle_radius is not None
        )

        if promoted:
            game.exclusion_circle_lat = game.next_circle_lat
            game.exclusion_circle_long = game.next_circle_long
            game.exclusion_circle_radius = game.next_circle_radius
            game.next_circle_lat = None
            game.next_circle_long = None
            game.next_circle_radius = None
            game.next_circle_public = False

            # On to the next one in the plan, placed straight away and
            # privately: a card scanned a minute from now has something to
            # show, and the admin's next act is a countdown rather than a
            # dropdown.
            game.circle_plan_index += 1
            self._arm_planned_circle(game)
        else:
            logger.warning(
                "Game %s has no next circle to promote - clearing the cue only",
                game_id,
            )

        self._clear_cue(game)
        user_ids = self._game_user_ids(game_id)

        self._session.commit()

        if promoted:
            tk.send_ticker_message(
                tk.TickerMessageType.CIRCLE_CLOSED,
                {},
                game_id=game_id,
                session=self._session,
            )
            trigger_circle_update(game_id)

        for user_id in user_ids:
            trigger_update_event("user", user_id)

        next_event.disarm(game_id)

        return promoted

    @db_scoped
    def get_cued_games(self) -> List[Tuple[UUID, float]]:
        """``(game_id, deadline)`` for every game with a live cue.

        The startup sweep's input (:func:`next_event.sweep`): the timers are
        in-process and die with it, but the deadlines are columns and do not.
        """
        rows = (
            self._session.query(Game.id, Game.next_event_at)
            .filter(Game.next_event_at.isnot(None))
            .all()
        )
        return [(row[0], row[1]) for row in rows]

    @db_scoped
    def create_team(
        self, game_id: UUID, name: str, team_id: Optional[UUID] = None
    ) -> UUID:
        """Add a team to a game, optionally at a caller-chosen id.

        See :meth:`create_game` for why ``team_id`` exists: a printed team
        join code encodes the team id, so a fixture that wants its codes to
        survive a database reset has to choose the id rather than discover it.
        """
        logger.info("AdminInterface - create_team")
        game = self._get_game_orm(game_id)
        team = Team(name=name, id=team_id) if team_id is not None else Team(name=name)
        game.teams.append(team)
        self._session.commit()

        self._get_game_ticker(game_id=game_id).touch_game_ticker_tag()

        return team.id

    @db_scoped
    def set_team_name(self, team_id: UUID, name: str) -> None:
        logger.info("AdminInterface - set_team_name %s %s", team_id, name)
        team = self._get_team_orm(team_id)
        user_ids = [user.id for user in team.users]
        game_id = team.game_id
        team.name = name

        self._get_game_ticker(game_id=game_id).touch_game_ticker_tag()
        for user_id in user_ids:
            trigger_update_event("user", user_id)

    @db_scoped
    def set_team_identity_colour(self, team_id: UUID, colour: str) -> None:
        """Pin a team's TEAM_CHANNEL colour. Once set, join code generation
        for this team must reuse it rather than re-deriving from
        allocate_team_slots, so adding a new team doesn't re-colour teams
        that have already picked."""
        logger.info("AdminInterface - set_team_identity_colour %s %s", team_id, colour)
        team = self._get_team_orm(team_id)
        team.identity_colour = colour

    @db_scoped
    def delete_team(self, team_id: UUID) -> None:
        """Remove a team entirely - the repair for one created by mistake or
        no longer wanted.

        Its current players go with it, each removed the same way
        ``delete_user`` removes a lone player. A team's ``id`` also lives on
        ``Shot.team_id`` (not nullable, recorded at the moment a shot was
        fired so it survives a later team switch) - any shots still pointing
        at this team once its current players are gone are historical only
        and are deleted the same way a departing player's shots are.

        Raises:
            HTTPException: 404 if the team is not found
        """
        logger.info("AdminInterface - delete_team %s", team_id)

        team = self._get_team_orm(team_id)
        game_id = team.game_id
        team_name = team.name

        for user in list(team.users):
            self.delete_user(user.id)

        stray_shots = self._session.query(Shot).filter_by(team_id=team_id).all()
        if stray_shots:
            shot_ids = [shot.id for shot in stray_shots]
            self._session.query(TickerEntry).filter(
                TickerEntry.shot_id.in_(shot_ids)
            ).update({"shot_id": None}, synchronize_session=False)
            for shot in stray_shots:
                self._session.delete(shot)

        self._session.delete(team)

        # Posting the message also touches the game's ticker tag and commits
        # the session, mirroring delete_user's announcement
        tk.send_generic_message(
            game_id, f"Team {team_name} has been deleted", session=self._session
        )

        trigger_update_event("shots", game_id)
        trigger_update_event("ticker", game_id)

    @db_scoped
    def delete_game(self, game_id: UUID) -> None:
        """Remove a game entirely: every team, every player, every shot and
        item, the ticker, the lot. The last resort for a game created by
        mistake or definitively finished with.

        Cascades the same way ``delete_team`` does, one level up - each team
        goes via ``delete_team`` (which removes its players via
        ``delete_user``), leaving only what the game owns directly: items
        never picked up, and whatever ticker lines survived the players who
        would have owned them.

        Raises:
            HTTPException: 404 if the game is not found
        """
        logger.info("AdminInterface - delete_game %s", game_id)

        game = self._get_game_orm(game_id)

        for team in list(game.teams):
            self.delete_team(team.id)

        # Signed up but never scanned a team in (roadmap R15): no team owns
        # them, so the cascade above never reaches them.
        for user in self._session.query(User).filter_by(game_id=game_id).all():
            self.delete_user(user.id)

        for item in self._session.query(Item).filter_by(game_id=game_id).all():
            self._session.delete(item)

        for drop in self._session.query(Drop).filter_by(game_id=game_id).all():
            self._session.delete(drop)

        for ticker_entry in (
            self._session.query(TickerEntry).filter_by(game_id=game_id).all()
        ):
            self._session.delete(ticker_entry)

        self._session.delete(game)

    @db_scoped
    def _get_game_ticker(self, game_id: UUID) -> Ticker:
        return Ticker(game_id, user_id=None, session=self._session)

    @db_scoped
    def set_game_active(self, game_id: UUID, active: bool) -> int:
        logger.info("AdminInterface - set_game_active %s/%s", game_id, active)

        game = self._get_game_orm(game_id)
        game.active = active

        # Starting a game with no next circle placed arms the first one of the
        # plan (backend/circles.py). Only when there is none: an admin who
        # placed one by hand, or paused and restarted mid-evening, keeps what
        # is on their map.
        armed = None
        if active and game.next_circle_lat is None:
            armed = self._arm_planned_circle(game)

        # Collect the user IDs for manual bumping after the session is committed
        user_ids = []
        for team in game.teams:
            for user in team.users:
                user_ids.append(user.id)

        ticker = self._get_game_ticker(game_id=game_id)
        if active:
            ticker.post_message(f"Game started")
        else:
            ticker.post_message(f"Game paused")

        self._session.commit()

        # Manually bump all the users
        for user_id in user_ids:
            trigger_update_event("user", user_id)

        if armed is not None:
            trigger_circle_update(game_id)

    @db_scoped
    def set_ai_shot_review_enabled(self, game_id: UUID, enabled: bool) -> List[UUID]:
        """Turn AI shot review on or off for a game.

        Returns the ids of the shots waiting in the queue when it is switched
        on, so the caller can put the existing backlog through as well as
        everything that arrives afterwards. Returns an empty list when
        switching off.

        Shots that already carry a review are left alone: the toggle gets
        flipped on and off during a game, and re-reviewing a shot that has
        already been read costs another API call to arrive at the same tags.
        A shot whose review errored has no verdict to keep, so it is retried -
        that is the point of switching the toggle back on after fixing the key
        or the model. One mid-review shot ("pending") is left to the review
        already in flight; the admin's "Re-run AI review" button covers a
        review that died before it could store anything.
        """
        logger.info(
            "AdminInterface - set_ai_shot_review_enabled %s/%s", game_id, enabled
        )

        game = self._get_game_orm(game_id)
        game.ai_shot_review_enabled = enabled

        backlog = []
        if enabled:
            backlog = [
                shot_id[0]
                for shot_id in self._session.query(Shot.id)
                .filter_by(game_id=game_id, checked=False)
                .filter(
                    or_(
                        Shot.ai_review_state.is_(None),
                        Shot.ai_review_state == AI_REVIEW_STATE_ERROR,
                    )
                )
                .order_by(Shot.time_created)
                .all()
            ]

        self._session.commit()
        # Wake the admin SSE stream so every open dashboard sees the new
        # checkbox state, not just the one that clicked it.
        trigger_update_event("shots", game_id)
        return backlog

    @db_scoped
    def is_ai_shot_review_enabled(self, game_id: UUID) -> bool:
        return bool(self._get_game_orm(game_id).ai_shot_review_enabled)

    @db_scoped
    def set_ai_auto_actions_enabled(self, game_id: UUID, enabled: bool) -> None:
        """Turn acting on confident AI verdicts on or off for a game.

        Independent of the review toggle: reviews only annotate, and this flag
        alone decides whether backend.shot_auto_actions may resolve the head of
        the queue.
        """
        logger.info(
            "AdminInterface - set_ai_auto_actions_enabled %s/%s", game_id, enabled
        )

        game = self._get_game_orm(game_id)
        game.ai_auto_actions_enabled = enabled

        self._session.commit()
        trigger_update_event("shots", game_id)

    @db_scoped
    def is_ai_auto_actions_enabled(self, game_id: UUID) -> bool:
        return bool(self._get_game_orm(game_id).ai_auto_actions_enabled)

    @db_scoped
    def set_ai_escalation_enabled(self, game_id: UUID, enabled: bool) -> None:
        """Turn escalation of hard shots to the stronger model on or off.

        A kill switch inside the auto-actions feature rather than an opt-in of
        its own, which is why it defaults on: with it off, a shot the ladder
        wants escalated (backend.shot_escalation) simply waits for the admin,
        exactly as it does when no escalation model is configured.
        """
        logger.info(
            "AdminInterface - set_ai_escalation_enabled %s/%s", game_id, enabled
        )

        game = self._get_game_orm(game_id)
        game.ai_escalation_enabled = enabled

        self._session.commit()
        trigger_update_event("shots", game_id)

    @db_scoped
    def is_ai_escalation_enabled(self, game_id: UUID) -> bool:
        return bool(self._get_game_orm(game_id).ai_escalation_enabled)

    @db_scoped
    def set_ai_resolve_everything_enabled(self, game_id: UUID, enabled: bool) -> None:
        """Turn "resolve everything" on or off for a game.

        With it on, an unconfident or unidentifiable head is resolved as best
        the reading allows instead of going to the admin: _decide() stops
        meaning "stop the drain" and starts meaning "the players will complain
        if it is wrong". Only sound alongside appeals (roadmap R8), which is
        what makes an automatic error loud and recoverable.
        """
        logger.info(
            "AdminInterface - set_ai_resolve_everything_enabled %s/%s", game_id, enabled
        )

        game = self._get_game_orm(game_id)
        game.ai_resolve_everything_enabled = enabled

        self._session.commit()
        trigger_update_event("shots", game_id)

    @db_scoped
    def is_ai_resolve_everything_enabled(self, game_id: UUID) -> bool:
        return bool(self._get_game_orm(game_id).ai_resolve_everything_enabled)

    @db_scoped
    def get_contested_shot_ids(self) -> list[UUID]:
        """The contested queue (roadmap R8): every shot with an open appeal,
        oldest complaint first.

        A list of its own rather than a re-entry into the live queue: an
        appealed shot rejoining that with its original timestamp would become
        the head and jam the drain behind a twenty-minute-old argument.
        """
        return [
            shot_id[0]
            for shot_id in self._session.query(Shot.id)
            .filter_by(appeal_state=APPEAL_OPEN)
            .order_by(Shot.appealed_at, Shot.id)
            .all()
        ]

    @db_scoped
    def get_shot_appeal(self, shot_id: UUID) -> dict:
        """What is being argued about on one shot.

        Its own endpoint for the reason the AI review has one: the frontend
        caches shot models permanently by id, and every field here is mutable.
        """
        shot = self._get_shot_orm(shot_id)
        target = (
            self._session.get(User, shot.target_user_id)
            if shot.target_user_id
            else None
        )
        return {
            "appeal_state": shot.appeal_state,
            "shooter_appeal_reason": shot.shooter_appeal_reason,
            "target_appeal_reason": shot.target_appeal_reason,
            "appealed_at": shot.appealed_at,
            "result": shot.result,
            "shooter_name": shot.user.name if shot.user else None,
            "target_name": target.name if target else None,
        }

    @db_scoped
    def get_shot_ai_review(self, shot_id: UUID) -> dict:
        """The stored AI review for one shot, and any escalation of it.

        Deliberately its own endpoint rather than a field on the shot: the
        frontend caches shot responses permanently by id, so a review that
        lands after the image was cached would never be seen. Keeping the big
        image cached and this small payload live avoids that.
        """
        shot = self._get_shot_orm(shot_id)
        return _ai_review_payload(shot, self.get_users_for_game(shot.game_id))

    @db_scoped
    def store_shot_ai_review(
        self, shot_id: UUID, state: str, payload=None
    ) -> Tuple[UUID, UUID]:
        """Record the outcome of a review. The single writer of these columns.

        Starting a fresh review (state "pending") also clears any escalation:
        the escalated verdict was drawn from the old reading, and a re-run
        replaces that reading. It is also how an admin unsticks an errored
        escalation -- "Re-run AI review" puts the shot back on the ladder from
        the bottom.

        Returns the shot's game id and shooter id so the caller can fire
        update events without needing a second session.
        """
        shot = self._get_shot_orm(shot_id)
        shot.ai_review_state = state
        if payload is None:
            shot.ai_review = None
        elif isinstance(payload, str):
            shot.ai_review = payload
        else:
            shot.ai_review = json.dumps(payload, default=str)
        if state == AI_REVIEW_STATE_PENDING:
            shot.ai_escalation_state = None
            shot.ai_escalation = None
        self._session.commit()
        return shot.game_id, shot.user_id

    @db_scoped
    def store_shot_escalation(
        self, shot_id: UUID, state: str, payload=None
    ) -> Tuple[UUID, UUID]:
        """Record the outcome of an escalation (backend/shot_escalation.py).
        The single writer of these columns, and the counterpart of
        :meth:`store_shot_ai_review`, down to what it returns.
        """
        shot = self._get_shot_orm(shot_id)
        shot.ai_escalation_state = state
        if payload is None:
            shot.ai_escalation = None
        elif isinstance(payload, str):
            shot.ai_escalation = payload
        else:
            shot.ai_escalation = json.dumps(payload, default=str)
        self._session.commit()
        return shot.game_id, shot.user_id

    @db_scoped
    def set_reference_photo(self, user_id: UUID, image_base64: str) -> Optional[UUID]:
        """Store the kit-check photo taken at the door for one player.

        Any previous review goes with it: the old reading describes the old
        photo, and leaving it behind would show a verdict for a picture that is
        no longer there. Returns the player's game id (None if they are in no
        team) so the caller can fire update events.
        """
        user = self._get_user_orm(user_id)
        user.reference_photo_base64 = image_base64
        user.reference_review_state = None
        user.reference_review = None
        user.touch()
        self._session.commit()

        game_id = user.game_id
        trigger_update_event("user", user_id)
        if game_id is not None:
            trigger_update_event("shots", game_id)
        return game_id

    @db_scoped
    def clear_reference_photo(self, user_id: UUID) -> Optional[UUID]:
        """Delete a player's reference photo and its review."""
        user = self._get_user_orm(user_id)
        user.reference_photo_base64 = None
        user.reference_review_state = None
        user.reference_review = None
        user.touch()
        self._session.commit()

        game_id = user.game_id
        trigger_update_event("user", user_id)
        if game_id is not None:
            trigger_update_event("shots", game_id)
        return game_id

    @db_scoped
    def get_reference_photo(self, user_id: UUID) -> Optional[str]:
        """Just the reference photo, without loading the whole user."""
        row = (
            self._session.query(User.reference_photo_base64)
            .filter_by(id=user_id)
            .first()
        )
        if not row:
            raise HTTPException(404, f"User {user_id} not found")
        return row[0]

    @db_scoped
    def get_reference_review(self, user_id: UUID) -> dict:
        """The stored kit-check review for one player, shaped like
        :meth:`get_shot_ai_review`."""
        user = self._get_user_orm(user_id)
        return {
            "state": user.reference_review_state,
            "review": _stored_json(user.reference_review),
        }

    @db_scoped
    def store_reference_review(
        self, user_id: UUID, state: str, payload=None
    ) -> Optional[UUID]:
        """Record the outcome of a kit-check review. The single writer of these
        columns.

        Returns the player's game id so the caller can fire update events
        without needing a second session.
        """
        user = self._get_user_orm(user_id)
        user.reference_review_state = state
        if payload is None:
            user.reference_review = None
        elif isinstance(payload, str):
            user.reference_review = payload
        else:
            user.reference_review = json.dumps(payload, default=str)
        self._session.commit()
        return user.game_id

    @db_scoped
    def get_reference_photo_status(self, game_id: UUID) -> List[dict]:
        """One row per player in a game: have they been photographed, and did
        the photo resolve to them?

        Each row also carries what the player is *supposed* to be wearing
        (:func:`backend.identity_admin.expected_outfit`), because the kit check
        is where the hat and the armband are handed over: the admin needs the
        colours to fetch out of the box before there is any photo to compare
        them with, not only afterwards.

        Selects columns only -- never reference_photo_base64, which the roster
        has no use for and which would make this response enormous.
        """
        from .identity.config import default_scheme
        from .identity_admin import expected_outfit

        self._get_game_orm(game_id)  # 404 if the game doesn't exist

        rows = (
            self._session.query(
                User.id,
                User.name,
                Team.name,
                User.reference_photo_base64.isnot(None),
                User.reference_review_state,
                User.reference_review,
                User.identity_slot,
                User.identity_overrides,
            )
            .outerjoin(Team, User.team_id == Team.id)
            .filter(User.game_id == game_id)
            .order_by(Team.name, User.name)
            .all()
        )

        scheme = default_scheme()
        return [
            {
                "user_id": user_id,
                "name": name,
                "team_name": team_name,
                "has_photo": bool(has_photo),
                "review_state": state,
                "expected_appearance": expected_outfit(slot, overrides, scheme),
                **_reference_verdict(state, review),
            }
            for (
                user_id,
                name,
                team_name,
                has_photo,
                state,
                review,
                slot,
                overrides,
            ) in rows
        ]

    def add_user_to_team(self, user_id: UUID, team_id: UUID):
        logger.info("AdminInterface - add_user_to_team")
        with UserInterface(user_id) as ui:
            ui.join_team(team_id)

            u = ui.get_user()

            user_name = u.name
            team_name = u.team.name
            game_id = u.team.game_id

            tk.send_ticker_message(
                tk.TickerMessageType.USER_JOINED_TEAM,
                {"user": user_name, "team": team_name},
                game_id=game_id,
                session=ui.get_session(),
            )

    @db_scoped
    def delete_user(self, user_id: UUID):
        """Remove a player entirely - the repair for the duplicate ``User`` a
        wrong-phone / wrong-browser join creates.

        Their collected items and fired shots (images included) go with them;
        shots *targeting* them survive as anonymous history with
        ``target_user_id`` nulled. Announces the removal on the game ticker
        and bumps the same update events joining a team does, so open
        dashboards and clients refresh. The deleted browser session simply
        gets a fresh auto-created user on its next touch.

        Raises:
            HTTPException: 404 if the user is not found
        """
        logger.info("AdminInterface - delete_user %s", user_id)

        user = self._get_user_orm(user_id)

        user_name = user.name
        game_id = user.team.game_id if user.team else None

        for item in list(user.items):
            self._session.delete(item)

        # Ticker lines pointing at a shot that is about to vanish just lose the
        # pointer - they have to go before the shots do, or the foreign key
        # breaks
        shot_ids = [shot.id for shot in user.shots]
        if shot_ids:
            self._session.query(TickerEntry).filter(
                TickerEntry.shot_id.in_(shot_ids)
            ).update({"shot_id": None}, synchronize_session=False)

        for shot in list(user.shots):
            self._session.delete(shot)

        self._session.query(Shot).filter_by(target_user_id=user_id).update(
            {"target_user_id": None}
        )

        # Ticker rows referencing the user would break their foreign keys on
        # delete: private messages go with the user, highlights just lose the
        # highlight.
        self._session.query(TickerEntry).filter_by(private_user_id=user_id).delete()
        self._session.query(TickerEntry).filter_by(highlight_user_id=user_id).update(
            {"highlight_user_id": None}
        )

        user.team = None
        self._session.delete(user)

        self._announce_user_removed(f"{user_name} has left the game", game_id, user_id)

    def _announce_user_removed(
        self, message: str, game_id: Optional[UUID], user_id: UUID
    ):
        """Shared tail of ``delete_user`` and ``merge_user``: post ``message``
        to the game ticker (if there is a game to post it to) and bump the
        same update events joining a team does, so open dashboards and the
        removed session's own client refresh.
        """
        if game_id:
            # Posting the message also touches the game's ticker tag and
            # commits the session, mirroring add_user_to_team's announcement
            tk.send_generic_message(game_id, message, session=self._session)
        else:
            self._session.commit()

        # Any client session still holding this user id needs to find out it
        # is gone (or, for a merge, that it should re-fetch as the survivor)
        if game_id:
            trigger_update_event("shots", game_id)
            trigger_update_event("ticker", game_id)
        trigger_update_event("user", user_id)

    @db_scoped
    def merge_user(self, user_id: UUID, into_user_id: UUID):
        """Fold a stray session into the player it actually belongs to - the
        repair for someone who joined on a second phone or cleared their
        cookies and so was minted a second, empty ``User``.

        Every row naming ``user_id`` is rewritten to name the survivor:
        countable state (bullets, appeals) is summed, single-valued state
        (name, identity, location, reference photo, weapon, team/slot) takes
        the survivor's value and falls back to the stray's only where the
        survivor has none, and hit points take the higher of the two. A
        ``UserAlias`` row is left behind mapping the stray's session id to the
        survivor, so ``get_user_id`` sends every future request bearing that
        cookie straight to the survivor - existing aliases pointing at the
        stray are re-pointed too, so merging into an id that is itself an
        alias still lands on the ultimate survivor. Reuses ``delete_user``'s
        announcement tail once the stray's row is gone.

        Raises:
            HTTPException: 400 if the two ids resolve to the same user,
                404 if either user does not exist.
        """
        logger.info("AdminInterface - merge_user %s into %s", user_id, into_user_id)

        alias = self._session.get(UserAlias, into_user_id)
        if alias is not None:
            into_user_id = alias.user_id

        if into_user_id == user_id:
            raise HTTPException(400, "Cannot merge a user into themselves")

        stray = self._get_user_orm(user_id)
        survivor = self._get_user_orm(into_user_id)

        stray_id = stray.id
        survivor_id = survivor.id
        stray_name = stray.name or "A player"

        # Items: the survivor keeps what they already hold, since the
        # user<->item association table's composite primary key would
        # collide if both rows named the survivor.
        survivor_item_ids = {item.id for item in survivor.items}
        for item in list(stray.items):
            stray.items.remove(item)
            if item.id not in survivor_item_ids:
                survivor.items.append(item)

        self._session.query(Shot).filter_by(user_id=stray_id).update(
            {"user_id": survivor_id}
        )
        self._session.query(Shot).filter_by(target_user_id=stray_id).update(
            {"target_user_id": survivor_id}
        )
        self._session.query(TickerEntry).filter_by(private_user_id=stray_id).update(
            {"private_user_id": survivor_id}
        )
        self._session.query(TickerEntry).filter_by(highlight_user_id=stray_id).update(
            {"highlight_user_id": survivor_id}
        )

        survivor.num_bullets += stray.num_bullets
        survivor.appeals_remaining += stray.appeals_remaining
        survivor.hit_points = max(survivor.hit_points, stray.hit_points)

        if stray.shot_damage > survivor.shot_damage or (
            stray.shot_damage == survivor.shot_damage
            and stray.shot_timeout < survivor.shot_timeout
        ):
            survivor.shot_damage = stray.shot_damage
            survivor.shot_timeout = stray.shot_timeout

        if survivor.name is None and stray.name is not None:
            survivor.name = stray.name
        if survivor.game_id is None and stray.game_id is not None:
            survivor.game_id = stray.game_id
        if survivor.identity_slot is None and stray.identity_slot is not None:
            survivor.identity_slot = stray.identity_slot
        if survivor.identity_overrides is None and stray.identity_overrides is not None:
            survivor.identity_overrides = stray.identity_overrides
        if survivor.identity_wardrobe is None and stray.identity_wardrobe is not None:
            survivor.identity_wardrobe = stray.identity_wardrobe

        if (
            survivor.reference_photo_base64 is None
            and stray.reference_photo_base64 is not None
        ):
            survivor.reference_photo_base64 = stray.reference_photo_base64
            survivor.reference_review_state = stray.reference_review_state
            survivor.reference_review = stray.reference_review

        if stray.location_timestamp is not None and (
            survivor.location_timestamp is None
            or stray.location_timestamp > survivor.location_timestamp
        ):
            survivor.latitude = stray.latitude
            survivor.longitude = stray.longitude
            survivor.location_timestamp = stray.location_timestamp
            survivor.location_accuracy = stray.location_accuracy

        # Team: go through the same team.users.append() join_team itself
        # uses, and send the same ticker announcement add_user_to_team does,
        # so dashboards see one consistent join rather than a silent
        # reassignment. Done on self._session directly rather than by calling
        # add_user_to_team, which would open a second, concurrent session on
        # the same rows this transaction hasn't committed yet.
        if survivor.team_id is None and stray.team_id is not None:
            team = stray.team
            stray.team = None
            survivor.game_id = team.game_id
            team.users.append(survivor)
            tk.send_ticker_message(
                tk.TickerMessageType.USER_JOINED_TEAM,
                {"user": survivor.name, "team": team.name},
                game_id=team.game_id,
                session=self._session,
            )

        # Re-point any alias that already pointed at the stray, then alias
        # the stray's session to the survivor, so a merge chain always
        # resolves in one hop.
        self._session.query(UserAlias).filter_by(user_id=stray_id).update(
            {"user_id": survivor_id}
        )
        self._session.add(UserAlias(session_id=stray_id, user_id=survivor_id))

        stray.team = None
        self._session.delete(stray)

        game_id = survivor.team.game_id if survivor.team else None
        survivor_name = survivor.name or "another player"
        self._announce_user_removed(
            f"{stray_name} rejoined as {survivor_name}", game_id, stray_id
        )

        # The survivor's own clients have just gained the stray's shots,
        # items and ammo, so they need to re-fetch too
        trigger_update_event("user", survivor_id)

    @db_scoped
    def get_all_shots(self) -> List[ShotModel]:
        query = self._session.query(Shot).order_by(Shot.time_created)

        shots = query.all()

        return [ShotModel.model_validate(s) for s in shots]

    @db_scoped
    def get_all_shot_ids(self) -> List[UUID]:
        query = self._session.query(Shot.id).order_by(Shot.time_created)

        shots = query.all()

        return [s.id for s in shots]

    @db_scoped
    def get_unchecked_shots(self, limit=5) -> Tuple[int, List[ShotModel]]:
        query = (
            self._session.query(Shot)
            .filter_by(checked=False)
            .order_by(Shot.time_created)
        )

        num_shots = query.count()
        filtered_shots = query.limit(limit).all()

        shot_models = [ShotModel.model_validate(s) for s in filtered_shots]

        self._session.close()

        for shot in shot_models:
            shot.image_base64 = draw_cross_on_image(shot.image_base64)

        return num_shots, shot_models

    @staticmethod
    def markup_shot_model(
        shot_model: ShotModel, add_targetting=True, add_annotations=False
    ):
        new_model = shot_model.model_copy()
        if add_targetting:
            new_model.image_base64 = draw_cross_on_image(new_model.image_base64)
        if add_annotations:
            if not shot_model.checked:
                status = "Unchecked"
            elif shot_model.target_user_id:
                target_name = (
                    UserInterface(shot_model.target_user_id).get_user_model().name
                )
                status = f"Hit {target_name}"
            elif shot_model.result == "bystander":
                status = "Hit a bystander"
            else:
                status = "Missed / refunded / invalidated"

            stats = {
                "Shooter": shot_model.user.name,
                "Damage": shot_model.shot_damage,
                "Result": status,
            }
            new_model.image_base64 = annotate_image_with_stats(
                new_model.image_base64, stats
            )

        return new_model

    @db_scoped
    def get_shots_ids(self, include_checked: bool = False) -> list[UUID]:
        """Shot ids, oldest first. Checked shots are excluded unless asked for
        -- the queue wants only what needs adjudicating, but reviewing a
        finished game wants everything."""
        query = self._session.query(Shot.id)
        if not include_checked:
            query = query.filter_by(checked=False)
        return [shot_id[0] for shot_id in query.order_by(Shot.time_created).all()]

    @db_scoped
    def get_shot_notes(self, shot_id) -> str:
        return self._get_shot_orm(shot_id).admin_notes or ""

    @db_scoped
    def set_shot_notes(self, shot_id, notes: str) -> None:
        self._get_shot_orm(shot_id).admin_notes = notes

    def hit_user_by_admin(self, user_id, num=1):
        with UserInterface(user_id) as ui:
            ui.hit(num)

            u: User = ui.get_user()

            user_name = u.name
            game_id = u.team.game_id

            if u.hit_points > 0:
                message_type = tk.TickerMessageType.ADMIN_HIT_USER
            else:
                message_type = tk.TickerMessageType.ADMIN_HIT_AND_KNOCKED_OUT_USER

            tk.send_ticker_message(
                message_type,
                {"user": user_name, "num": num},
                session=ui.get_session(),
                user_id=user_id,
                game_id=game_id,
            )

    @db_scoped
    def hit_user(self, shot_id, target_user_id):
        shot = self._get_shot_orm(shot_id)

        u_from = shot.user
        # Read before ui_target.hit() below commits and expires shot: it is
        # this shot's own tie-break for clear_unchecked_shots, the same one
        # get_queue_head uses against a clock with 1s resolution.
        shot_time_created = shot.time_created
        ui_target = UserInterface(target_user_id, session=self._session)

        # A shot that hits somebody already knocked out is just a hit that does
        # nothing: it is announced as a plain hit, and only the blow that
        # actually kills announces a knockout and invalidates the victim's
        # still-queued shots.
        # Reading the HP afterwards alone would credit a second killer.
        already_dead = self._get_user_orm(target_user_id).hit_points <= 0

        ui_target.hit(shot.shot_damage)

        u_to = self._get_user_orm(target_user_id)

        invalidated_count = 0
        if already_dead or u_to.hit_points > 0:
            message_type_public = tk.TickerMessageType.HIT_AND_DAMAGE
            message_type_private = tk.TickerMessageType.USER_GOT_HIT

        else:
            message_type_public = tk.TickerMessageType.HIT_AND_KNOCKOUT
            message_type_private = tk.TickerMessageType.USER_GOT_KNOCKED_OUT
            invalidated_count = ui_target.clear_unchecked_shots(
                shot_time_created, shot_id
            )

        tk.send_ticker_message(
            message_type_public,
            {"user": u_from.name, "target": u_to.name, "num": shot.shot_damage},
            game_id=u_from.team.game_id,
            session=self._session,
            highlight_user_id=u_from.id,
        )

        tk.send_ticker_message(
            message_type_private,
            {"user": u_from.name, "target": u_to.name, "num": shot.shot_damage},
            game_id=u_from.team.game_id,
            user_id=u_to.id,
            session=self._session,
            # So the line itself is the way in to the shot - and to appealing
            # it - rather than making the player go looking (roadmap R8)
            shot_id=shot.id,
        )

        if invalidated_count:
            tk.send_ticker_message(
                tk.TickerMessageType.SHOTS_INVALIDATED,
                {"num": invalidated_count},
                game_id=u_from.team.game_id,
                user_id=u_to.id,
                session=self._session,
            )

        try:
            _, previous = self._mark_shot_checked(shot_id, "hit")
        except HTTPException:
            # The fatal shot itself is excluded from clear_unchecked_shots
            # above (it gets its own "hit" result right here), so this no
            # longer fires for the ordinary self-shot case. Kept as a
            # defensive catch-all for two resolvers racing on the same
            # shot_id.
            shot.result = "hit"
            previous = None

        # Record the target user in the db
        shot.target_user_id = target_user_id

        # Settled after the new target is written, since who this shot now hits
        # is half of what decides whether the appeal was right
        if previous is not None:
            self._settle_appeal(shot, *previous)

        self._session.commit()

        # The shot has left the queue, so tell any admin watching it - the
        # shooter, whose shot history has a new outcome, and the target, who
        # has just lost a hit point and gained something to appeal
        trigger_update_event("shots", shot.game_id)
        trigger_update_event("user", u_from.id)
        trigger_update_event("user", u_to.id)

    def set_user_HP(self, user_id, num=1):
        with UserInterface(user_id) as ui:
            ui.set_HP(num)

            u = ui.get_user()

            if u.hit_points > 1:
                message_type = tk.TickerMessageType.ADMIN_GAVE_ARMOUR
            elif u.hit_points == 1:
                message_type = tk.TickerMessageType.ADMIN_REVIVED_USER
            else:
                message_type = tk.TickerMessageType.ADMIN_HIT_AND_KILLED_USER

            tk.send_ticker_message(
                message_type,
                {"user": u.name, "num": num - 1},
                user_id=user_id,
                game_id=u.team.game_id,
                team_id=u.team_id,
                session=ui.get_session(),
            )

    def award_user_ammo(self, user_id, num=1):
        with UserInterface(user_id) as ui:
            ui.award_ammo(num=num)

            user_model = ui.get_user_model()

            tk.send_ticker_message(
                tk.TickerMessageType.ADMIN_GAVE_AMMO,
                {"user": user_model.name, "num": num},
                user_id=user_id,
                game_id=user_model.game_id,
                team_id=user_model.team_id,
                session=ui.get_session(),
            )

    def award_user_appeals(self, user_id, num=1):
        """Hand a player appeals back.

        A referee who has just talked something through with a player needs to
        be able to give them another go: a budget with no override turns a
        judgement call into a dead end (roadmap R8).
        """
        with UserInterface(user_id) as ui:
            ui.award_appeals(num=num)

            user_model = ui.get_user_model()

            tk.send_ticker_message(
                tk.TickerMessageType.ADMIN_GAVE_APPEALS,
                {"user": user_model.name, "num": num},
                user_id=user_id,
                game_id=user_model.game_id,
                team_id=user_model.team_id,
                session=ui.get_session(),
            )

    @db_scoped
    def set_team_leader(self, user_id: UUID, is_team_leader: bool):
        """Nominate (or stand down) one player as their team's leader.

        A label, not a permission: it only decides whether the player is shown
        the leader's checklist of what "properly equipped" means.
        """
        user = self._get_user_orm(user_id)
        user.is_team_leader = is_team_leader
        self._session.commit()

        # The player's own screen, so the panel appears without a reload; and
        # the game's ticker event, which is what wakes the admin roster (see
        # generate_any_game_updates - there is no "admin" event of its own).
        trigger_update_event("user", user_id)
        if user.game_id is not None:
            trigger_update_event("ticker", user.game_id)

    def set_user_name(self, user_id, name: str):
        with UserInterface(user_id) as ui:
            ui.set_name(name)

            # Bump the game this user is in
            try:
                game_id = ui.get_user().team.game_id
                trigger_update_event("ticker", game_id)
            except AttributeError:
                # User is not in a team. Meh
                pass

    @db_scoped
    def _mark_shot_checked(
        self, shot_id, result: str
    ) -> Tuple[Shot, Optional[Tuple[Optional[str], Optional[UUID]]]]:
        """
        Mark a shot as checked and record how it was adjudicated. Ticker
        messages and update events are the caller's job.

        A checked shot is normally final. The exception is a contested one
        (roadmap R8): an open appeal re-opens the verdict for exactly one
        re-ruling, and what the shot used to say comes back with it so the
        caller can settle the appeal against it.

        Returns:
            (shot, previous), where ``previous`` is the (result, target user
            id) pair being overruled when this was a re-adjudication, and None
            when it was the first ruling on this shot.

        Raises:
            HTTPException: 404 if shot not found
            HTTPException: 400 if shot has already been checked and nobody is
                contesting it
        """
        shot = self._session.query(Shot).filter_by(id=shot_id).first()

        if not shot:
            raise HTTPException(404, f"Shot id {shot_id} not found")

        previous = None
        if shot.checked:
            if shot.appeal_state != APPEAL_OPEN:
                raise HTTPException(400, f"Shot id {shot_id} has already been checked")
            previous = (shot.result, shot.target_user_id)

        shot.checked = True
        shot.result = result

        # A shot that is no longer a hit is nobody's hit. hit_user writes the
        # new target back itself, immediately after calling this.
        if result != "hit":
            shot.target_user_id = None

        return shot, previous

    @db_scoped
    def _settle_appeal(self, shot: Shot, old_result, old_target_id) -> None:
        """Rule on the open appeal against a shot that has just been re-adjudicated.

        Upheld or rejected is *inferred* rather than asked for: if the admin's
        ruling differs from the one that was appealed, the appeal was right.
        A miss and a bystander call are not different rulings for this purpose
        - both say the shot hit no player, which is the only thing an appellant
        against either was arguing about - so swapping one for the other is a
        rejection. A shot the admin ends up refunding differs from whatever
        it said before, so the benefit of the doubt falls out of that rule rather than
        needing a case of its own. An admin who agrees with the outcome but for
        different reasons is a rejection, which is the right answer anyway
        since the game state is unchanged.

        **Nothing is unwound here.** Re-ruling a shot changes no HP and no
        ammo: there is no compensating action anywhere in this codebase for a
        knockout's cascade, and writing a general unwind is far more than this
        is worth. A wrongly-taken life is handed back by the admin with
        set_user_HP, by hand (roadmap R8).
        """
        upheld = not _same_appeal_outcome(old_result, shot.result) or (
            shot.result == "hit" and shot.target_user_id != old_target_id
        )

        appellants = []
        if shot.shooter_appeal_reason is not None:
            appellants.append(shot.user_id)
        if shot.target_appeal_reason is not None and old_target_id is not None:
            # The party who appealed is whoever the verdict said was hit at the
            # time, which is not necessarily who it says now
            if old_target_id not in appellants:
                appellants.append(old_target_id)

        shot.appeal_state = APPEAL_UPHELD if upheld else APPEAL_REJECTED
        game_id = shot.game_id
        shooter_name = shot.user.name

        for user_id in appellants:
            if upheld:
                # If both parties appealed, both are refunded: working out
                # which of them was vindicated is machinery this game does not
                # need, and the appeal only ever cost the one who was wrong.
                UserInterface(user_id, session=self._session).award_appeals(1)

            tk.send_ticker_message(
                (
                    tk.TickerMessageType.APPEAL_UPHELD_PRIVATE
                    if upheld
                    else tk.TickerMessageType.APPEAL_REJECTED_PRIVATE
                ),
                {},
                user_id=user_id,
                game_id=game_id,
                session=self._session,
                shot_id=shot.id,
            )

        if upheld:
            # A correction is a social event, not a database update
            tk.send_ticker_message(
                tk.TickerMessageType.APPEAL_UPHELD,
                {
                    "user": shooter_name,
                    "result": _APPEAL_RESULT_WORDS.get(shot.result, shot.result),
                },
                game_id=game_id,
                session=self._session,
                shot_id=shot.id,
            )

        self._session.commit()

        for user_id in {
            shot.user_id,
            old_target_id,
            shot.target_user_id,
            *appellants,
        }:
            if user_id is not None:
                trigger_update_event("user", user_id)
        trigger_update_event("shots", game_id)

    @db_scoped
    def mark_shot_missed(self, shot_id):
        shot, previous = self._mark_shot_checked(shot_id, "miss")
        user_id = shot.user_id
        game_id = shot.game_id

        tk.send_ticker_message(
            tk.TickerMessageType.MISSED_SHOT,
            {},
            user_id=user_id,
            game_id=game_id,
            session=self._session,
        )

        if previous is not None:
            self._settle_appeal(shot, *previous)

        self._session.commit()

        # The shot has left the queue, so tell any admin watching it - and the
        # shooter, whose shot history has a new outcome
        trigger_update_event("shots", game_id)
        trigger_update_event("user", user_id)

    @db_scoped
    def mark_shot_bystander(self, shot_id):
        """
        Mark a shot as having caught a bystander rather than a player.

        Mechanically identical to a miss - the ammo is spent and nobody takes
        damage - but recorded separately so the shooter's history (and the
        ticker) can say what actually happened.
        """
        shot, previous = self._mark_shot_checked(shot_id, "bystander")
        user_id = shot.user_id
        game_id = shot.game_id

        tk.send_ticker_message(
            tk.TickerMessageType.BYSTANDER_SHOT,
            {},
            user_id=user_id,
            game_id=game_id,
            session=self._session,
        )

        if previous is not None:
            self._settle_appeal(shot, *previous)

        self._session.commit()

        # The shot has left the queue, so tell any admin watching it - and the
        # shooter, whose shot history has a new outcome
        trigger_update_event("shots", game_id)
        trigger_update_event("user", user_id)

    @db_scoped
    def refund_shot(self, shot_id: UUID):
        """
        Refund a shot and mark it as checked

        Args:
            shot_id (UUID): Shot id

        Raises:
            HTTPException: 404 if shot not found
            HTTPException: 400 if shot has already been checked
        """
        shot, previous = self._mark_shot_checked(shot_id, "refunded")
        user_id = shot.user_id
        game_id = shot.game_id

        user = shot.user

        user.num_bullets += 1

        tk.send_ticker_message(
            tk.TickerMessageType.REFUNDED_SHOT,
            {},
            game_id=game_id,
            user_id=user_id,
            session=self._session,
        )

        if previous is not None:
            self._settle_appeal(shot, *previous)

        self._session.commit()

        trigger_update_event("shots", game_id)
        trigger_update_event("user", user_id)

    def make_new_item(
        self,
        item_type: str,
        item_data: dict,
        collected_only_once=True,
        collected_as_team=False,
        batch: Optional[str] = None,
        unlimited: bool = False,
    ) -> str:
        """Makes a new item with the given settings and encodes it into a URL

        Encoded items can be collected by visiting the URL. The item data itself
        is stored in a query parameter "d" - collecting the item via
        :meth:`UserInterface.collect_item` using this data directly also works.

        Items are signed using the SECRET_KEY environment variable. The URL
        domain is not part of the signature, so it's possible in theory to alter
        this in URLs, but might be annoying to do so, so better to make sure
        that `WEBSITE_URL` is set correctly in the .env file before generating QR
        codes.


        Args:
            item_type (str): The type of item to create
            item_data (dict): The data for the item - a dict that depends on the item type
            collected_only_once (bool, optional): Whether the item can only be collected once. Defaults to True. Otherwise can be collected by other users / teams even after first collection.
            collected_as_team (bool, optional): Whether the item is collected as a team. Defaults to False.
            batch (str, optional): A label minted into the payload so a set of codes can be withdrawn together. Defaults to None (unbatched, as every code printed before batches existed).
            unlimited (bool, optional): Whether the same player may scan this code any number of times - the sandbox's wall posters. Defaults to False.
        """
        logger.info("make_new_item item_type=%s, item_data=%s", item_type, item_data)
        try:
            item_type = ItemType(item_type)
        except ValueError:
            raise HTTPException(
                400,
                "Invalid item type. Valid choices are %s" % [t.value for t in ItemType],
            )

        item = ItemModel(
            id=get_uuid(),
            itype=item_type,
            data=item_data,
            collected_only_once=collected_only_once,
            collected_as_team=collected_as_team,
            batch=batch,
            unlimited=unlimited,
        )
        item.sign()

        encoded_item = item.to_base64()
        logger.info("Made new item: %s => %s", item, encoded_item)

        # Encode this into a URL
        encoded_url = add_params_to_url(os.environ["WEBSITE_URL"], {"d": encoded_item})

        return encoded_url

    @db_scoped
    def withdraw_batch(self, batch: str) -> List[dict]:
        """Stop every code minted into ``batch`` from being collectable.

        The only recall a printed code has: it cannot be un-printed, and
        rotating ``SECRET_KEY`` would take the team cards with it. Idempotent,
        because the admin pressing it twice at 16:00 means the same thing as
        pressing it once.
        """
        batch = batch.strip()
        if not batch:
            raise HTTPException(400, "Name the batch to withdraw.")

        logger.info("withdraw_batch %s", batch)

        if not self._session.get(RevokedBatch, batch):
            self._session.add(RevokedBatch(batch=batch))

        return self._revoked_batches()

    @db_scoped
    def restore_batch(self, batch: str) -> List[dict]:
        """Let a withdrawn batch be collected again - the undo for a press of
        the wrong button, since the row's presence is the whole state."""
        logger.info("restore_batch %s", batch)

        revoked = self._session.get(RevokedBatch, batch.strip())
        if revoked:
            self._session.delete(revoked)

        return self._revoked_batches()

    @db_scoped
    def get_revoked_batches(self) -> List[dict]:
        return self._revoked_batches()

    def _revoked_batches(self) -> List[dict]:
        """Every withdrawn batch, most recently withdrawn first."""
        return [
            {
                "batch": revoked.batch,
                "revoked_at": (
                    revoked.revoked_at.isoformat() if revoked.revoked_at else None
                ),
            }
            for revoked in self._session.query(RevokedBatch)
            .order_by(RevokedBatch.revoked_at.desc())
            .all()
        ]

    # The single-code register (the other half of withdrawing a batch). The
    # server has no list of what was minted -- a code is an HMAC over its
    # payload and nothing else -- so the only way to name one card is to scan
    # it back in. Everything here is keyed on the item id out of the payload.

    @db_scoped
    def register_code(self, encoded_item: str) -> dict:
        """Put a scanned code on the list of codes that can be switched off.

        Idempotent: scanning the same card twice is how an admin checks it is
        already on the list, so a second scan updates what the payload says
        and leaves ``enabled`` exactly as they set it.
        """
        item = ItemModel.from_base64(encoded_item)

        # Signed first, because an unsigned code is not a code: letting one
        # onto the list would hand the admin a switch that turns off nothing.
        signature_error = item.validate_signature()
        if signature_error:
            raise HTTPException(403, f"That code is invalid - {signature_error}")

        known = self._session.get(KnownCode, item.id)
        is_new = known is None

        if is_new:
            known = KnownCode(id=item.id, enabled=True)
            self._session.add(known)

        known.item_type = item.itype
        known.data = item.data_as_json()
        known.batch = item.batch
        known.unlimited = item.unlimited
        known.collected_as_team = item.collected_as_team

        logger.info("register_code %s (new=%s)", item.id, is_new)

        self._session.flush()

        return {
            "code": self._known_code_payload(known),
            "new": is_new,
            "codes": self._known_codes(),
        }

    @db_scoped
    def set_code_enabled(self, code_id: UUID, enabled: bool) -> List[dict]:
        """Switch one registered code on or off. Off is refused at the scan."""
        known = self._session.get(KnownCode, code_id)
        if not known:
            raise HTTPException(404, "That code is not on the list - scan it first.")

        logger.info("set_code_enabled %s -> %s", code_id, enabled)
        known.enabled = enabled

        return self._known_codes()

    @db_scoped
    def forget_code(self, code_id: UUID) -> List[dict]:
        """Take a code off the list, which puts it back to the default.

        The default is collectable, so forgetting a switched-off code turns it
        back on. This is for a card scanned in by mistake rather than an undo.
        """
        known = self._session.get(KnownCode, code_id)
        if known:
            logger.info("forget_code %s", code_id)
            self._session.delete(known)

        return self._known_codes()

    @db_scoped
    def get_known_codes(self) -> List[dict]:
        return self._known_codes()

    def _known_codes(self) -> List[dict]:
        """Every registered code, most recently scanned first."""
        return [
            self._known_code_payload(known)
            for known in self._session.query(KnownCode)
            .order_by(KnownCode.first_seen.desc())
            .all()
        ]

    def _known_code_payload(self, known: KnownCode) -> dict:
        data = json.loads(known.data) if known.data else {}

        return {
            "id": str(known.id),
            "description": describe_item(
                known.item_type, data, known.collected_as_team
            ),
            "item_type": known.item_type.value if known.item_type else None,
            "batch": known.batch,
            "unlimited": known.unlimited,
            "enabled": known.enabled,
            "first_seen": known.first_seen,
        }

    # Reading a code without doing anything to it (react-ui/src/AdminScanCode.js).
    # Every other scanner in the app spends what it sees: the player's collects
    # the item, the admin's list writes a KnownCode row. This one writes
    # nothing at all, which is what makes it safe to point at a card found on
    # the floor mid-game, or at a poster whose print run nobody can now
    # remember withdrawing.

    @db_scoped
    def identify_code(self, data: str) -> dict:
        """What a scanned string is, and what it would do if a player scanned it.

        Read-only: no item is collected, nothing is registered, no row is
        written. Every QR the game prints is answered - item cards, the pub
        and sandbox posters, the sign-up link, a team card and a legacy slot
        code - and anything else is said to be somebody else's QR code rather
        than reported as an error.
        """
        data = (data or "").strip()

        if not data:
            raise HTTPException(400, "Nothing was scanned")

        item = _parse_or_none(ItemModel.from_base64, data)
        if item is not None:
            return self._identify_item_code(item)

        join_code = _parse_or_none(JoinCodeModel.from_base64, data)
        if join_code is not None:
            return self._identify_join_code(join_code)

        return {
            "kind": "unknown",
            "headline": "Not one of this game's codes",
            "verdict": {
                "tone": "bad",
                "text": "Nothing in the game reads this - somebody else's QR code",
            },
            "facts": [{"label": "What was scanned", "value": data[:200]}],
        }

    def _identify_item_code(self, item: ItemModel) -> dict:
        """An item card, a pub certificate or a sandbox poster.

        The checks are asked in the order ``UserInterface.collect_item`` asks
        them, so the verdict names the first thing that would refuse the scan
        rather than an incidental second one.
        """
        # The headline is what the card hands out, so nothing below repeats it:
        # a phone screen has room for the answer or for the small print, and
        # an admin reading this is standing in the street.
        facts = [
            {
                "label": "Batch",
                "value": item.batch or "unbatched (printed before batches existed)",
            },
            {"label": "Scanning", "value": _scan_rule(item)},
            {"label": "Code", "value": str(item.id)},
        ]

        payload = {
            "kind": "item",
            "headline": describe_item(item.itype, item.data, item.collected_as_team),
            "facts": facts,
        }

        signature_error = item.validate_signature()
        if signature_error:
            payload["verdict"] = {
                "tone": "bad",
                "text": f"Not a code this server minted - {signature_error}",
            }
            return payload

        if (
            item.batch
            and self._session.query(RevokedBatch).filter_by(batch=item.batch).first()
        ):
            payload["verdict"] = {
                "tone": "bad",
                "text": f'Dead: the "{item.batch}" batch has been withdrawn',
            }
            return payload

        known = self._session.get(KnownCode, item.id)
        if known is not None and not known.enabled:
            payload["verdict"] = {
                "tone": "bad",
                "text": "Dead: this code was switched off on the Item codes page",
            }
            return payload

        collectors = self._item_collectors(item)
        if collectors and item.collected_only_once and not item.unlimited:
            payload["verdict"] = {
                "tone": "bad",
                "text": f"Spent: already collected by {collectors[0]}",
            }
            return payload

        if collectors:
            payload["facts"].append(
                {"label": "Collected so far by", "value": ", ".join(collectors)}
            )

        payload["verdict"] = {
            "tone": "good",
            "text": "Live - a player can collect this",
        }
        return payload

    def _item_collectors(self, item: ItemModel) -> List[str]:
        """Who has scanned this card already, newest last. Empty if nobody has."""
        collected = self._session.get(Item, item.id)
        if collected is None:
            return []

        return [
            f"{user.name or 'somebody'}"
            + (f" ({user.team.name})" if user.team and user.team.name else "")
            for user in collected.users
        ]

    def _identify_join_code(self, code: JoinCodeModel) -> dict:
        """A sign-up link, a team card, or one of the legacy per-slot codes."""
        team = self._session.get(Team, code.team_id) if code.team_id else None

        if code.team_id is None:
            headline = "Sign-up link"
            facts = [
                {
                    "label": "Does",
                    "value": "Puts the scanner in the game with no team, to pick an outfit",
                }
            ]
        elif code.slot is None:
            headline = f"Team card - {team.name if team else 'unknown team'}"
            facts = [
                {
                    "label": "Does",
                    "value": "Puts the scanner in that team, keeping the outfit they picked",
                }
            ]
        else:
            headline = f"Slot {code.slot} - {team.name if team else 'unknown team'}"
            facts = [
                {
                    "label": "Does",
                    "value": "The old per-slot code: joins that team wearing that outfit",
                }
            ]

        facts.append({"label": "Game", "value": str(code.game_id)})

        payload = {"kind": "join", "headline": headline, "facts": facts}

        signature_error = code.validate_signature()
        if signature_error:
            payload["verdict"] = {
                "tone": "bad",
                "text": f"Not a code this server minted - {signature_error}",
            }
            return payload

        if self._session.get(Game, code.game_id) is None:
            payload["verdict"] = {
                "tone": "bad",
                "text": "Dead: that game is not on this server any more",
            }
            return payload

        if code.team_id is not None and team is None:
            payload["verdict"] = {
                "tone": "bad",
                "text": "Dead: that team has been deleted",
            }
            return payload

        payload["verdict"] = {
            "tone": "good",
            "text": "Live - scanning it joins the game",
        }
        return payload

    @db_scoped
    def get_locations(self, game_id: UUID = None):
        # If game_id is not provided, get the game_id of the first game
        if not game_id:
            game_id = self._session.query(Game.id).first()[0]

        teams = self._session.query(Team).filter_by(game_id=game_id).all()
        locations = []
        for team in teams:
            for user in team.users:
                user: User
                locations.append(
                    {
                        "user_id": user.id,
                        "team_id": team.id,
                        "user": user.name,
                        "team": team.name,
                        "latitude": user.latitude,
                        "longitude": user.longitude,
                        "state": user.state,
                        "timestamp": user.location_timestamp,
                        # How good that fix was, in metres. Serialises into
                        # every shot's location_context along with the rest.
                        "accuracy": user.location_accuracy,
                    }
                )
        return locations

    @db_scoped
    def get_recent_shots(self, game_id: UUID, limit: int = 6) -> List[dict]:
        """The last few shots of a game, newest first, for the spectator screen.

        Includes checked shots: this is a history of what just happened, not a
        queue of what needs doing. Columns only, and no image -- the screen
        refetches this on every SSE bump, and the thumbnails come separately
        from :func:`get_shot_thumbnail` because they never change.

        ``time_created`` has 1s resolution and the ids are uuid4, so two shots
        fired in the same second come back in an arbitrary but *stable* order.
        Stability is the part that matters on a screen: an unstable tiebreak
        would make the feed visibly reshuffle on every refetch.
        """
        rows = (
            self._session.query(
                Shot.id,
                Shot.time_created,
                Shot.user_id,
                Shot.target_user_id,
                Shot.checked,
                Shot.result,
                Shot.ai_review_state,
                Shot.ai_review,
                Shot.ai_escalation_state,
                Shot.ai_escalation,
                Shot.location_context,
            )
            .filter_by(game_id=game_id)
            .order_by(Shot.time_created.desc(), Shot.id.desc())
            .limit(limit)
            .all()
        )

        # Resolved once for the whole feed, and reused as the candidate roster
        # for every shot's identification.
        users = self.get_users_for_game(game_id)
        by_id = {u.id: u for u in users}

        out = []
        for row in rows:
            shot = RecentShotRow(*row)
            shooter = by_id.get(shot.user_id)
            target = by_id.get(shot.target_user_id)
            out.append(
                {
                    "id": shot.id,
                    "time_created": shot.time_created,
                    "shooter_name": shooter.name if shooter else None,
                    "shooter_team": shooter.team_name if shooter else None,
                    "target_name": target.name if target else None,
                    "checked": shot.checked,
                    "result": shot.result,
                    **_ai_review_payload(shot, users),
                }
            )
        return out

    def get_shot_thumbnail(self, shot_id: UUID) -> str:
        """A shot's photograph, small enough to put on a screen repeatedly.

        Immutable for the life of the shot, so the frontend fetches it once per
        id and holds it -- the same "small live payload, heavy cached body"
        split that keeps admin_get_shot separate from admin_get_shot_ai_review.
        """
        image = self.get_shot_image_base64(shot_id)
        return draw_cross_on_image(
            downscale_jpeg(image, max_dimension=THUMBNAIL_MAX_DIMENSION, quality=70)
        )

    @db_scoped
    def get_scoreboard(self, game_id: UUID):
        teams_and_ids = (
            self._session.query(Team.id, Team.name).filter_by(game_id=game_id).all()
        )
        teams_by_id = {id: name for id, name in teams_and_ids}

        user_data = (
            self._session.query(
                User.id, User.name, User.team_id, User.hit_points, User.time_of_death
            )
            .filter(User.team_id.in_(teams_by_id.keys()))
            .all()
        )
        users_by_id = {
            id: (name, teams_by_id[team_id], hit_points, time_of_death)
            for id, name, team_id, hit_points, time_of_death in user_data
        }

        completed_shots_by_these_users = (
            self._session.query(Shot.user_id, Shot.shot_damage)
            .filter(
                and_(
                    Shot.user_id.in_(users_by_id.keys()),
                    Shot.checked,
                    Shot.target_user_id != None,
                )
            )
            .all()
        )

        self._session.close()

        table = []
        for user_id, (
            username,
            teamname,
            hitpoints,
            time_of_death,
        ) in users_by_id.items():
            total_damage = sum(
                map(
                    lambda s: s[1],
                    filter(lambda s: s[0] == user_id, completed_shots_by_these_users),
                )
            )
            table.append(
                {
                    # So a caller can join a row to its player exactly. Names
                    # are not unique and may be unset.
                    "user_id": user_id,
                    "name": username,
                    "team": teamname,
                    "hitpoints": hitpoints,
                    "total_damage": total_damage,
                    "state": User.calculate_state(teamname, hitpoints, time_of_death),
                }
            )

        table = sorted(table, key=lambda t: t["total_damage"], reverse=True)

        return {"table": table}

    @db_scoped
    def _get_all_game_ids(self):
        return self._session.query(Game.id).all()

    @db_scoped
    def reset_to_start_state(self, game_id: UUID):
        """Put a game back to how it should look the moment before it starts.

        This is the 16:00 button on the night (M2.1), not `reset_game`: the
        sandbox hour has to be swept away, but everything earned at the door
        has to survive it. So it keeps the reference photos, the identities,
        the teams, the last known locations and the nominated team leaders,
        and resets everything the sandbox touched.

        It **refuses unless the game is paused**, and that friction is
        deliberate: this wipes every shot and every scanned item in the game,
        and pausing first is both a second pair of eyes on a destructive
        button and the thing the runbook asks for anyway. Do not quietly
        relax it into a pause-then-reset.

        Unlike `reset_game` it walks the players by `game_id` rather than
        through the teams, so a player who signed up and has not yet scanned
        a team card at the door is reset too (roadmap R15) - `reset_game`'s
        team walk cannot see them at all.
        """
        game: Game = self._get_game_orm(game_id=game_id)

        if game.active:
            raise HTTPException(
                400, "Pause the game before resetting it to the start state"
            )

        users: list[User] = self._session.query(User).filter_by(game_id=game_id).all()

        for user in users:
            user.num_bullets = 0
            user.hit_points = STARTING_HIT_POINTS
            user.time_of_death = None
            user.shot_damage, user.shot_timeout = BASIC_WEAPON
            user.appeals_remaining = APPEALS_PER_GAME
            # Otherwise everybody starts the real game holding the cooldown
            # from a sandbox shot that no longer exists (M1.1)
            user.last_shot_at = None
            # A radar or a circle warning lit in the sandbox hour must not
            # still be running when the real game starts (M6.1, M6.2)
            user.radar_until = None
            user.circle_warning_until = None

        # By game rather than by shooter: a shot outlives the team its shooter
        # was in, and this has to empty the queue whoever is left in it
        for shot in self._session.query(Shot).filter_by(game_id=game_id).all():
            self._session.delete(shot)

        # The sandbox codes have been scanned; deleting the rows re-arms the
        # once-only ones, which is harmless here because the batch they belong
        # to is withdrawn separately (M2.2) and the real codes are unscanned
        for item in list(game.items):
            item.users.clear()
            self._session.delete(item)

        for ticker_entry in (
            self._session.query(TickerEntry).filter_by(game_id=game_id).all()
        ):
            self._session.delete(ticker_entry)

        # Any crate the sandbox hour left lying about (M4.3). Deleted rather
        # than cleared through clear_drop for the same reason the circles
        # below go straight onto the columns: that announces to a ticker this
        # is about to empty.
        for drop in self._session.query(Drop).filter_by(game_id=game_id).all():
            self._session.delete(drop)

        # All three circles, straight onto the columns rather than through
        # set_circles: that announces each change to a ticker this is about to
        # delete anyway, and would do it three times
        for prefix in ("exclusion", "next", "drop"):
            for field in ("lat", "long", "radius"):
                setattr(game, f"{prefix}_circle_{field}", None)
        game.next_circle_public = False

        # Back to the top of the circle plan, and the first one placed
        # privately there and then: the real game starts with a circle already
        # waiting for whoever finds an early-warning card (M6.2).
        game.circle_plan_index = 0
        self._arm_planned_circle(game)

        # And whatever was cued to happen next (M3.1), which was cued against
        # the sandbox clock
        game.next_event_kind = None
        game.next_event_at = None
        game.next_event_note = None
        # ...and the in-process clock behind it. Leaving it running is not
        # unsafe - fire_next_event re-reads the columns and finds nothing to
        # do - but a task asleep on a deadline that no longer exists is a
        # thing to explain later (M3.2).
        next_event.disarm(game_id)

        # Read before the commit expires them
        user_ids = [user.id for user in users]

        self._session.commit()

        for user_id in user_ids:
            trigger_update_event("user", user_id)
        trigger_update_event("shots", game_id)
        trigger_update_event("ticker", game_id)
        trigger_circle_update(game_id)

    @db_scoped
    def reset_game(self, game_id: UUID, keep_weapons=True):
        """
        Reset the game, including all scores, items etc. But not usernames
        """
        game: Game = self._get_game_orm(game_id=game_id)

        # Loop through all the items in this game and delete them all
        for item in game.items:
            del item

        # Get all the teams for this game
        teams: list[Team] = game.teams

        # For each, get all the users
        users: list[User] = []
        for team in teams:
            users += team.users

        # For each user, reset their stats
        for user in users:
            user.num_bullets = 0
            user.hit_points = STARTING_HIT_POINTS
            user.time_of_death = None
            user.appeals_remaining = APPEALS_PER_GAME
            # Otherwise a reset leaves everybody holding the cooldown from
            # whatever they fired last (M1.1), which a reset has just deleted.
            user.last_shot_at = None
            user.radar_until = None
            user.circle_warning_until = None

            # The kit-check photos are photographs of identifiable people and
            # have no meaning once the night they were taken for is over.
            user.reference_photo_base64 = None
            user.reference_review_state = None
            user.reference_review = None

            if not keep_weapons:
                user.shot_damage = 1
                user.shot_timeout = DEFAULT_SHOT_TIMEOUT

            # Delete their shots
            for shot in user.shots:
                self._session.delete(shot)

            # And their pickups
            for item in user.items:
                self._session.delete(item)

        # And any crate still on the ground (M4.3)
        for drop in self._session.query(Drop).filter_by(game_id=game_id).all():
            self._session.delete(drop)

        # The play area starts again as well: all three circles, straight onto
        # the columns rather than through set_circles, which would announce
        # each change to a ticker this is about to delete anyway
        for prefix in ("exclusion", "next", "drop"):
            for field in ("lat", "long", "radius"):
                setattr(game, f"{prefix}_circle_{field}", None)
        game.next_circle_public = False

        # ...and back to the top of the circle plan, with its first entry
        # placed privately there and then, exactly as reset_to_start_state
        # does it: a game that starts again starts with a circle already
        # waiting for whoever finds an early-warning card.
        game.circle_plan_index = 0
        self._arm_planned_circle(game)

        # Wipe the ticker
        for ticker_entry in (
            self._session.query(TickerEntry).filter_by(game_id=game_id).all()
        ):
            self._session.delete(ticker_entry)

        # Otherwise every open map keeps drawing the circles and the crates
        # this has just deleted until something else happens to fire the event
        self._session.commit()
        trigger_circle_update(game_id)

    async def generate_any_game_updates(self, timeout=None):
        """
        An async iterator that yields None every time any ticker, circle or shot
        queue is updated in any game, or at most after timeout seconds
        """
        while True:
            game_ids = self._get_all_game_ids()

            # Lookup / make an event for each game's ticker, circle and shots
            events = []
            for game_id in game_ids:
                logger.debug("(AdminInterface) Getting events for game %s", game_id[0])
                events.append(get_trigger_event("ticker", game_id[0]))
                events.append(get_trigger_event("circle", game_id[0]))
                events.append(get_trigger_event("shots", game_id[0]))

            # No games yet: there is nothing to wait on. Poll until a game
            # appears.
            if not events:
                await asyncio.sleep(1)
                yield
                continue

            logger.debug("(Admin Updater) Subscribing to events %s", events)
            waiters = [asyncio.ensure_future(event.wait()) for event in events]

            # Only one of these can win, and the losers wait on events that
            # trigger_update_event has already dropped from the registry - so
            # they can never finish on their own. Cancelling them in a finally
            # covers the generator being closed mid-wait too, which is how an
            # admin page that goes away ends.
            try:
                done, _ = await asyncio.wait(
                    waiters,
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for waiter in waiters:
                    waiter.cancel()
                await asyncio.gather(*waiters, return_exceptions=True)

            if done:
                logger.debug("(Admin Updater) Event received")
            else:
                logger.debug("(Admin Updater) Event timeout")

            yield
