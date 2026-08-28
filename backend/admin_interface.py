import asyncio
import json
import logging
import os
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

from . import ticker_message_dispatcher as tk
from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event
from .circles import trigger_circle_update
from .database_scope_provider import DatabaseScopeProvider
from .image_processing import annotate_image_with_stats
from .image_processing import draw_cross_on_image
from .items import ItemModel
from .model import AI_REVIEW_STATE_DONE
from .model import AI_REVIEW_STATE_ERROR
from .model import AI_REVIEW_STATE_PENDING
from .model import DEFAULT_SHOT_TIMEOUT
from .model import Game
from .model import GameModel
from .model import ItemType
from .model import Shot
from .model import ShotModel
from .model import Team
from .model import TeamModel
from .model import TickerEntry
from .model import User
from .model import UserModel
from .ticker import Ticker
from .user_interface import UserInterface
from .utils import add_params_to_url

logger = logging.getLogger(__name__)


AdminScopeWrapper = DatabaseScopeProvider("admin")
db_scoped = AdminScopeWrapper.db_scoped


# What the auto-action drain needs to know about the head of a game's shot
# queue -- deliberately not a ShotModel, so image_base64 is never loaded.
QueueHead = namedtuple(
    "QueueHead",
    [
        "id",
        "user_id",
        "ai_review_state",
        "ai_review",
        "ai_escalation_state",
        "ai_escalation",
        "location_context",
    ],
)


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
    """
    blank = {"matches_expected": None, "top_name": None, "top_probability": None}
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
    }


class CircleTypes(str, Enum):
    EXCLUSION = "EXCLUSION"
    NEXT = "NEXT"
    BOTH = "BOTH"
    DROP = "DROP"


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

    @db_scoped
    def get_queue_head(self, game_id: UUID) -> Optional[QueueHead]:
        """The oldest unchecked shot in a game, or None if the queue is empty.

        Ordered by (time_created, id): timestamps have 1s resolution, so the id
        breaks ties deterministically. Selects columns only -- never
        image_base64, which the auto-action drain has no use for.
        ``location_context`` is here because the drain's identification step
        builds its location term from it (backend.shot_identification), and the
        escalation columns because the drain's ladder reads them to decide
        whether this head is still waiting on a stronger model
        (backend.shot_escalation).
        """
        row = (
            self._session.query(
                Shot.id,
                Shot.user_id,
                Shot.ai_review_state,
                Shot.ai_review,
                Shot.ai_escalation_state,
                Shot.ai_escalation,
                Shot.location_context,
            )
            .filter_by(game_id=game_id, checked=False)
            .order_by(Shot.time_created, Shot.id)
            .first()
        )
        return QueueHead(*row) if row else None

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
        """Every user on a team belonging to ``game_id``. 404s if the game
        doesn't exist. Used by the identity admin report/suggest logic
        (backend/identity_admin.py), which needs the whole game's roster to
        compute pairwise distances and slot uniqueness.
        """
        self._get_game_orm(game_id)  # 404 if the game doesn't exist

        users = (
            self._session.query(User).join(Team).filter(Team.game_id == game_id).all()
        )
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
    def create_game(self) -> UUID:
        logger.info("AdminInterface - create_game")
        g = Game()
        self._session.add(g)
        self._session.commit()

        return g.id

    @db_scoped
    def set_circles(
        self, game_id: UUID, name: CircleTypes, lat: float, long: float, radius: float
    ):
        logger.info("AdminInterface - set_circles")
        game: Game = self._get_game_orm(game_id)

        if name == CircleTypes.EXCLUSION:
            game.exclusion_circle_lat = lat
            game.exclusion_circle_long = long
            game.exclusion_circle_radius = radius
            message_type = tk.TickerMessageType.ADMIN_SET_CIRCLE_EXCLUSION
        elif name == CircleTypes.NEXT:
            game.next_circle_lat = lat
            game.next_circle_long = long
            game.next_circle_radius = radius
            message_type = tk.TickerMessageType.ADMIN_SET_CIRCLE_NEXT
        elif name == CircleTypes.BOTH:
            game.exclusion_circle_lat = lat
            game.exclusion_circle_long = long
            game.exclusion_circle_radius = radius
            game.next_circle_lat = lat
            game.next_circle_long = long
            game.next_circle_radius = radius
            message_type = tk.TickerMessageType.ADMIN_SET_CIRCLE_BOTH
        elif name == CircleTypes.DROP:
            game.drop_circle_lat = lat
            game.drop_circle_long = long
            game.drop_circle_radius = radius

            message_type = tk.TickerMessageType.ADMIN_SET_CIRCLE_DROP
        else:
            raise HTTPException(400, f"Invalid circle name {name}")

        self._session.commit()

        # Announce the circle change
        tk.send_ticker_message(
            message_type,
            {},
            game_id=game_id,
            session=self._session,
        )

        # Trigger a circle update
        trigger_circle_update(game_id)

    @db_scoped
    def create_team(self, game_id: UUID, name: str) -> UUID:
        logger.info("AdminInterface - create_team")
        game = self._get_game_orm(game_id)
        team = Team(name=name)
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
    def _get_game_ticker(self, game_id: UUID) -> Ticker:
        return Ticker(game_id, user_id=None, session=self._session)

    @db_scoped
    def set_game_active(self, game_id: UUID, active: bool) -> int:
        logger.info("AdminInterface - set_game_active %s/%s", game_id, active)

        game = self._get_game_orm(game_id)
        game.active = active

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
    def get_shot_ai_review(self, shot_id: UUID) -> dict:
        """The stored AI review for one shot, and any escalation of it.

        Deliberately its own endpoint rather than a field on the shot: the
        frontend caches shot responses permanently by id, so a review that
        lands after the image was cached would never be seen. Keeping the big
        image cached and this small payload live avoids that.
        """
        shot = self._get_shot_orm(shot_id)
        return {
            "state": shot.ai_review_state,
            "review": _stored_json(shot.ai_review),
            "escalation_state": shot.ai_escalation_state,
            "escalation": _stored_json(shot.ai_escalation),
        }

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

        Selects columns only -- never reference_photo_base64, which the roster
        has no use for and which would make this response enormous.
        """
        self._get_game_orm(game_id)  # 404 if the game doesn't exist

        rows = (
            self._session.query(
                User.id,
                User.name,
                Team.name,
                User.reference_photo_base64.isnot(None),
                User.reference_review_state,
                User.reference_review,
            )
            .join(Team, User.team_id == Team.id)
            .filter(Team.game_id == game_id)
            .order_by(Team.name, User.name)
            .all()
        )

        return [
            {
                "user_id": user_id,
                "name": name,
                "team_name": team_name,
                "has_photo": bool(has_photo),
                "review_state": state,
                **_reference_verdict(state, review),
            }
            for user_id, name, team_name, has_photo, state, review in rows
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

        if game_id:
            # Posting the message also touches the game's ticker tag and
            # commits the session, mirroring add_user_to_team's announcement
            tk.send_generic_message(
                game_id, f"{user_name} has left the game", session=self._session
            )
        else:
            self._session.commit()

        # Their queued shots vanished from the queue, and any client session
        # still holding this user id needs to find out it is gone
        if game_id:
            trigger_update_event("shots", game_id)
            trigger_update_event("ticker", game_id)
        trigger_update_event("user", user_id)

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
                status = "Missed / refunded"

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
        ui_target = UserInterface(target_user_id, session=self._session)

        # A shot that hits somebody already knocked out is just a hit that does
        # nothing: it is announced as a plain hit, and only the blow that
        # actually kills announces a knockout and refunds the victim's queue.
        # Reading the HP afterwards alone would credit a second killer.
        already_dead = self._get_user_orm(target_user_id).hit_points <= 0

        ui_target.hit(shot.shot_damage)

        u_to = self._get_user_orm(target_user_id)

        if already_dead or u_to.hit_points > 0:
            message_type_public = tk.TickerMessageType.HIT_AND_DAMAGE
            message_type_private = tk.TickerMessageType.USER_GOT_HIT

        else:
            message_type_public = tk.TickerMessageType.HIT_AND_KNOCKOUT
            message_type_private = tk.TickerMessageType.USER_GOT_KNOCKED_OUT
            ui_target.clear_unchecked_shots()

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
        )

        try:
            self._mark_shot_checked(shot_id, "hit")
        except HTTPException:
            # Handle the edge case where a user shoots themselves: the knockout
            # above already marked their unchecked shots as refunded
            shot.result = "hit"

        # Record the target user in the db
        shot.target_user_id = target_user_id

        self._session.commit()

        # The shot has left the queue, so tell any admin watching it - and the
        # shooter, whose shot history has a new outcome
        trigger_update_event("shots", shot.game_id)
        trigger_update_event("user", u_from.id)

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
    def _mark_shot_checked(self, shot_id, result: str) -> Shot:
        """
        Mark a shot as checked and record how it was adjudicated. Ticker
        messages and update events are the caller's job.

        Raises:
            HTTPException: 404 if shot not found
            HTTPException: 400 if shot has already been checked
        """
        shot = self._session.query(Shot).filter_by(id=shot_id).first()

        if not shot:
            raise HTTPException(404, f"Shot id {shot_id} not found")

        if shot.checked:
            raise HTTPException(400, f"Shot id {shot_id} has already been checked")

        shot.checked = True
        shot.result = result

        return shot

    @db_scoped
    def mark_shot_missed(self, shot_id):
        shot = self._mark_shot_checked(shot_id, "miss")
        user_id = shot.user_id
        game_id = shot.game_id

        tk.send_ticker_message(
            tk.TickerMessageType.MISSED_SHOT,
            {},
            user_id=user_id,
            game_id=game_id,
            session=self._session,
        )

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
        shot = self._mark_shot_checked(shot_id, "bystander")
        user_id = shot.user_id
        game_id = shot.game_id

        tk.send_ticker_message(
            tk.TickerMessageType.BYSTANDER_SHOT,
            {},
            user_id=user_id,
            game_id=game_id,
            session=self._session,
        )

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
        shot = self._mark_shot_checked(shot_id, "refunded")
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

        self._session.commit()

        trigger_update_event("shots", game_id)
        trigger_update_event("user", user_id)

    def make_new_item(
        self,
        item_type: str,
        item_data: dict,
        collected_only_once=True,
        collected_as_team=False,
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
        )
        item.sign()

        encoded_item = item.to_base64()
        logger.info("Made new item: %s => %s", item, encoded_item)

        # Encode this into a URL
        encoded_url = add_params_to_url(os.environ["WEBSITE_URL"], {"d": encoded_item})

        return encoded_url

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
            user.hit_points = 1
            user.time_of_death = None

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

        # Wipe the ticker
        for ticker_entry in (
            self._session.query(TickerEntry).filter_by(game_id=game_id).all()
        ):
            self._session.delete(ticker_entry)

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

            # No games yet: there are no events to wait on, and
            # asyncio.as_completed([]) would raise StopIteration and kill this
            # generator. Poll until a game appears.
            if not events:
                await asyncio.sleep(1)
                yield
                continue

            # make futures for waiting for all these events
            futures = [
                asyncio.wait_for(event.wait(), timeout=timeout) for event in events
            ]

            try:
                logger.debug("(Admin Updater) Subscribing to events %s", events)
                await next(asyncio.as_completed(futures))

                logger.debug("(Admin Updater) Event received")
                yield
            except asyncio.TimeoutError:
                logger.debug("(Admin Updater) Event timeout")
                yield
