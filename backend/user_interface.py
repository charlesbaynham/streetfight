import asyncio
import datetime
import json
import logging
import time
from threading import RLock
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
from uuid import UUID
from uuid import uuid4 as get_uuid

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.orm import Session as SQLAlchemySession

from . import asyncio_triggers
from .asyncio_triggers import get_trigger_event
from .database import session_scope
from .database_scope_provider import DatabaseScopeProvider
from .image_processing import save_image
from .item_actions import do_item_actions
from .items import ItemModel
from .model import APPEAL_REASONS
from .model import Game
from .model import GameModel
from .model import Item
from .model import Shot
from .model import Team
from .model import TeamModel
from .model import User
from .model import UserModel
from .shot_escalation import VERDICT_BYSTANDER
from .shot_escalation import VERDICT_MISS
from .shot_escalation import VERDICT_PLAYER
from .shot_identification import rank_candidates
from .shot_vision import HIT_BYSTANDER
from .ticker import Ticker

logger = logging.getLogger(__name__)

# 10 minutes to get to safety
TIME_KNOCKED_OUT = 10 * 60

# Default weapon settings
DEFAULT_SHOT_TIMEOUT = 6.0
DEFAULT_SHOT_DAMAGE = 0

make_user_lock = RLock()

# The escalated verdicts that are a bottom line, in the shooter's vocabulary.
# "unsure" is deliberately absent: it means an admin still has to look, so
# there is nothing to tell the shooter that the weak review didn't already say.
_ESCALATED_SUGGESTIONS = {
    VERDICT_PLAYER: "hit",
    VERDICT_MISS: "miss",
    VERDICT_BYSTANDER: "bystander",
}


def _completed_escalation(shot: Shot) -> Optional[dict]:
    """A finished escalation's stored payload, or None if there isn't one."""
    if shot.ai_escalation_state != "done" or not shot.ai_escalation:
        return None
    try:
        escalation = json.loads(shot.ai_escalation)
    except ValueError:
        return None
    return escalation if isinstance(escalation, dict) else None


def _completed_review(shot: Shot) -> Optional[dict]:
    """The cheap pass's stored reading, or None if there isn't one."""
    if shot.ai_review_state != "done" or not shot.ai_review:
        return None
    try:
        review = json.loads(shot.ai_review)
    except ValueError:
        return None
    return review if isinstance(review, dict) else None


def _ai_suggestion(shot: Shot) -> Optional[str]:
    """The AI's provisional verdict for the shooter's own shot history.

    Only ever the bottom line -- the reasoning and the clothing readings stay
    admin-only. A completed escalation wins over the cheap review, because the
    whole reason the shot was escalated is that the cheap reading was not good
    enough to act on; anything else falls back to it.
    """
    escalation = _completed_escalation(shot)
    if escalation is not None:
        suggestion = _ESCALATED_SUGGESTIONS.get(escalation.get("verdict"))
        if suggestion is not None:
            return suggestion

    review = _completed_review(shot)
    if review is None:
        return None
    if review.get("outcome") == HIT_BYSTANDER:
        return "bystander"
    # Reviews stored before outcomes existed only have is_hit
    return "hit" if review.get("is_hit") else "miss"


def _ai_target_name(shot: Shot, users: List[User], names: dict) -> Optional[str]:
    """Who the AI thinks this shot hit, for the shooter's own shot history.

    Only ever offered beside a "hit" suggestion on an unchecked shot -- once an
    admin has ruled, ``target_name`` is the answer and this guess is noise. The
    precedence is :func:`_ai_suggestion`'s: an escalation that named somebody
    named them, and nothing else gets a say.

    Falling back to the cheap reading, the bar is the one
    :mod:`backend.shot_auto_actions` applies before acting on a ranking
    unattended -- confident, untied, and contradicted by nothing in the
    reading. Anything short of that names nobody rather than naming a guess:
    the shooter would read it as who they shot.
    """
    escalation = _completed_escalation(shot)
    if escalation is not None and escalation.get("verdict") == VERDICT_PLAYER:
        return escalation.get("target_name")

    review = _completed_review(shot)
    if review is None:
        return None

    ranked = rank_candidates(shot, users, review)
    if ranked is None or not ranked.confident:
        return None
    if ranked.ambiguous or ranked.inconsistent:
        return None
    return names.get(ranked.best)


# The two people who were actually there, and so the only two who may appeal a
# shot: whoever fired it and whoever the verdict says it hit.
APPEAL_PARTY_SHOOTER = "shooter"
APPEAL_PARTY_TARGET = "target"

# An appeal is live only while the state is "open". "upheld" and "rejected" are
# terminal - the admin's word ends the loop.
APPEAL_OPEN = "open"
APPEAL_UPHELD = "upheld"
APPEAL_REJECTED = "rejected"


def appeal_party(shot: Shot, user_id: UUID) -> Optional[str]:
    """Which side of a shot a user is on, or None if they were not there."""
    if shot.user_id == user_id:
        return APPEAL_PARTY_SHOOTER
    if shot.target_user_id == user_id:
        return APPEAL_PARTY_TARGET
    return None


def appeal_reason(shot: Shot, party: str) -> Optional[str]:
    """The reason this party gave for appealing, or None if they haven't."""
    if party == APPEAL_PARTY_SHOOTER:
        return shot.shooter_appeal_reason
    return shot.target_appeal_reason


def appeal_refusal(shot: Shot, user: User, party: str) -> Optional[str]:
    """Why ``party`` may not appeal this shot, in words, or None if they may.

    The single source of truth for the whole feature: ``can_appeal`` in both
    shot lists is this returning None, and :meth:`UserInterface.appeal_shot`
    refuses with the very string it returns, so the button a player is shown
    and the endpoint behind it can never disagree.
    """
    if not shot.checked:
        return "This shot hasn't been adjudicated yet"
    if shot.result is None or shot.result in ("refunded", "invalidated"):
        return "There's no verdict on this shot to appeal"
    if shot.appeal_state not in (None, APPEAL_OPEN):
        return "The referee has already ruled on an appeal against this shot"
    if appeal_reason(shot, party) is not None:
        return "You've already appealed this shot"
    if user.appeals_remaining <= 0:
        return "You have no appeals left"
    # A miss or a bystander call takes nothing off anybody, so only the shooter
    # has a case to make about it.
    if party == APPEAL_PARTY_TARGET and shot.result != "hit":
        return "You can only appeal a shot that was ruled a hit on you"
    return None


def touch_user(user_interface: "UserInterface"):
    logger.debug("Touching user %s", user_interface.user_id)
    user = (
        user_interface._session.query(User).filter_by(id=user_interface.user_id).first()
    )
    user.touch()


def announce_updates(user_interface):
    """Fire this scope's update events, now the session has committed.

    Every scope announces the user itself. A call that also changes something
    the rest of the game watches queues its own event with
    :meth:`UserInterface.announce_after_commit` instead of firing it inline,
    so the announcement lands *after* the row exists rather than before it -
    and, more to the point, so it lands however the call was reached. The
    ``/api/submit_shot`` route is not the only way a shot enters a game: the
    demo drip and ``npm run demoshots`` go through the interface directly, and
    a shot that reaches the database without a "shots" event is a shot no
    spectator screen, admin queue or nav-bar counter ever hears about.
    """
    asyncio_triggers.trigger_update_event("user", user_interface.user_id)

    pending = user_interface._pending_announcements
    user_interface._pending_announcements = []
    for event_type, key in pending:
        asyncio_triggers.trigger_update_event(event_type, key)


UserScopeWrapper = DatabaseScopeProvider(
    "users",
    precommit_method=touch_user,
    postcommit_method=announce_updates,
)
db_scoped = UserScopeWrapper.db_scoped


class UserInterface:
    """
    Class to query / interact with Users
    """

    def __init__(self, user_id: Union[UUID, str], session=None):
        if isinstance(user_id, str):
            self.user_id = UUID(user_id)
        elif isinstance(user_id, UUID):
            self.user_id = user_id
        else:
            raise TypeError

        self._session: SQLAlchemySession = session
        self._session_users = 0
        self._session_is_external = bool(session)
        self._db_scoped_altering = False
        self._pending_announcements: List[tuple] = []

    def __enter__(self):
        from . import database

        # Create a session here instead of letting db_scoped do it. This will
        # mean that we have ownership of it here, so db_scoped will leave it
        # alone and let us manage its lifecycle.
        if self._session:
            self._session.close()

        self._session = database.Session()

        return self

    def __exit__(self, *args):
        if not self._session_is_external:
            if self._session:
                logger.debug(
                    "UserInterface %s closing session",
                    hash(self),
                )
                self._session.close()

    def get_session(self):
        return self._session

    def announce_after_commit(self, event_type: str, key) -> None:
        """Queue an update event for :func:`announce_updates` to fire."""
        self._pending_announcements.append((event_type, key))

    @db_scoped
    def _make_user(self) -> User:
        """
        Make a new user
        """
        user = User(
            id=self.user_id,
            shot_damage=DEFAULT_SHOT_DAMAGE,
            shot_timeout=DEFAULT_SHOT_TIMEOUT,
        )
        self._session.add(user)
        self._session.commit()

        logger.info("Making new user {}".format(user.id))

        return user

    @db_scoped
    def get_user(self) -> User:
        "Return an ORM object for this user, making a new one if required"

        with make_user_lock:
            user = self._session.get(User, self.user_id)

            if not user:
                user = self._make_user()

        return user

    @db_scoped
    def hit(self, num=1) -> User:
        "Take num hitpoints from the user, leaving them on as least zero"
        u: User = self.get_user()
        initial_HP = u.hit_points

        u.hit_points -= num

        if u.hit_points < 0:
            u.hit_points = 0

        # Record the time of death if this shot killed the user. Note that we
        # check if this was the death blow, since the user could be shot more
        # than once
        if initial_HP > 0 and u.hit_points <= 0:
            u.time_of_death = time.time() + TIME_KNOCKED_OUT

    @db_scoped
    def award_HP(self, num=1) -> User:
        "Give health to the user"
        self.get_user().hit_points += num

    @db_scoped
    def set_HP(self, num) -> User:
        """
        Set the user's health, wiping any death state
        """
        u: User = self.get_user()
        u.hit_points = num
        u.time_of_death = 0

    @db_scoped
    def award_ammo(self, num=1) -> User:
        "Give ammo to the user"
        self.get_user().num_bullets += num

    @db_scoped
    def award_appeals(self, num=1) -> User:
        "Give appeals to the user, leaving them on at least zero"
        u: User = self.get_user()
        u.appeals_remaining = max(0, u.appeals_remaining + num)

    @db_scoped
    def get_user_model(self) -> UserModel:
        u = self.get_user()
        return UserModel.model_validate(u) if u else None

    @db_scoped
    def get_team_id(self) -> UUID:
        return self.get_user().team_id

    @db_scoped
    def get_game_id(self) -> UUID:
        team = self.get_user().team
        if team is None:
            return None
        return team.game_id

    @db_scoped
    def get_team_model(self) -> TeamModel:
        team = self.get_user().team
        return TeamModel.model_validate(team) if team else None

    @db_scoped
    def get_game_model(self) -> GameModel:
        team = self.get_user().team
        if not team:
            return None

        game = team.game
        return GameModel.model_validate(game) if game else None

    @db_scoped
    def _get_item_from_database(self, item_id: int) -> Item:
        return self._session.query(Item).filter_by(id=item_id).first()

    @db_scoped
    def set_name(self, new_name: str):
        self.get_user().name = new_name.strip()

    @db_scoped
    def set_identity(self, slot: Optional[int], overrides_json: Optional[str]):
        """Write the user's identity slot + overrides (JSON text, or None).

        Just the column write -- validation (slot usability, uniqueness,
        collisions, override label checks) lives in backend/identity_admin.py,
        which is the impure bridge to the pure backend/identity package. Using
        UserInterface here (rather than a raw AdminInterface column set) gets
        the usual touch-on-write + update-event-on-commit behaviour for free.
        """
        u = self.get_user()
        u.identity_slot = slot
        u.identity_overrides = overrides_json

    @db_scoped
    def clear_identity(self):
        """Null the identity slot, overrides and wardrobe, freeing the
        outfit for everyone else. Just the column write -- the player stays
        in their team (see backend/identity_admin.py's clear_identity, which
        is the admin-facing entry point; team removal is admin_delete_user's
        job, not this).
        """
        u = self.get_user()
        u.identity_slot = None
        u.identity_overrides = None
        u.identity_wardrobe = None

    @db_scoped
    def set_weapon_data(self, damage: int, fire_delay: float):
        u = self.get_user()
        u.shot_timeout = fire_delay
        u.shot_damage = damage

    @db_scoped
    def join_team(self, team_id: UUID):
        from .admin_interface import AdminInterface

        team = self._session.query(Team).filter_by(id=team_id).first()

        if not team:
            game_ids = self._session.query(Game.id).filter_by().all()
            if len(game_ids) == 0:
                game_id = AdminInterface().create_game()
                logger.warning(
                    "Team does not exist and no games are running - creating it and making a new game (%s)",
                    game_id,
                )
            elif len(game_ids) > 1:
                logger.error(
                    "Cannot assign team to game automatically since multiple teams exist"
                )
                raise HTTPException(
                    405,
                    "Cannot join team - team does not exist and multiple games are running",
                )
            else:
                game_id = game_ids[0]
                logger.warning(
                    "Team does not exist - creating it and adding it to the only game (%s)",
                    game_id,
                )

            logger.info("Creating new team with uuid=%s", team_id)
            team = Team(id=team_id, game_id=game_id)
            self._session.add(team)

        team.users.append(self.get_user())

    @db_scoped
    def join_team_and_claim_slot(
        self,
        team_id: UUID,
        slot: int,
        overrides_json: Optional[str] = None,
        wardrobe_json: Optional[str] = None,
    ):
        """Join ``team_id`` and claim identity ``slot`` in one transaction.

        Unlike join_team this never auto-creates the team: join codes are
        signed against an existing team, so a missing one is a 404, not a
        provisioning request. The slot-holder check is re-run here, inside
        the same transaction as the write, so two players scanning the same
        code can't both claim it - the loser gets a 409.

        Claiming a slot rewrites the whole identity, so a canonical claim
        (which passes neither ``overrides_json`` nor ``wardrobe_json``) clears
        any previous overrides and wardrobe. That is deliberate and symmetric.
        """
        team = self._session.query(Team).filter_by(id=team_id).first()

        if not team:
            raise HTTPException(404, f"Team {team_id} not found")

        holder = (
            self._session.query(User)
            .join(Team, User.team_id == Team.id)
            .filter(
                Team.game_id == team.game_id,
                User.identity_slot == slot,
                User.id != self.user_id,
            )
            .first()
        )
        if holder is not None:
            raise HTTPException(
                409, f"Outfit #{slot} was just claimed by {holder.name}"
            )

        user = self.get_user()
        team.users.append(user)
        user.identity_slot = slot
        user.identity_overrides = overrides_json
        user.identity_wardrobe = wardrobe_json

    @db_scoped
    def submit_shot(
        self,
        image_base64: str,
        heading: Optional[float] = None,
        shot_id: Optional[UUID] = None,
        time_created: Optional[datetime.datetime] = None,
    ):
        """Record a shot. ``heading`` is where the phone was pointing in
        degrees clockwise from north, and is None whenever the device could
        not say - telemetry must never stop somebody firing.

        ``shot_id`` and ``time_created`` exist for replaying a simulated game
        into a development database (``backend/test_world/replay.py``), where
        a photograph is of a moment an hour ago and the location context has
        to be the one that moment had. A real shot mints its own id and is
        stamped with the wall clock, which is the only honest answer when a
        player fires: ``/api/submit_shot`` passes neither, and must not.
        """
        from .admin_interface import AdminInterface

        user: User = self.get_user()
        team = user.team

        if not team:
            raise HTTPException(405, "User is not in a team yet")

        game = team.game

        if user.hit_points <= 0:
            raise HTTPException(403, "User is dead")

        if user.num_bullets <= 0:
            raise HTTPException(403, "User has no ammo")

        # Read before anything below dirties the session: an attribute read
        # on an expired object autoflushes, and a flush clears the dirty flag
        # @db_scoped uses to decide whether to announce anything at all (the
        # same trap the shot id is assigned by hand to avoid, below). The
        # AdminInterface call just below is what expires them: a @db_scoped
        # call from another interface sharing this session commits it.
        game_id = game.id
        review_enabled = game.ai_shot_review_enabled

        logger.info("User %s submitting shot to game %s", user.id, game_id)

        all_user_locations = AdminInterface(session=self._session).get_locations(
            game_id=game_id
        )

        # Assign the id here rather than letting the column default do it at
        # flush time, so it can be returned without flushing. Flushing would
        # clear the session's dirty flag and rob @db_scoped of the signal it
        # uses to fire the post-commit update event.
        shot_id = shot_id or get_uuid()

        shot_entry = Shot(
            id=shot_id,
            user=user,
            team=team,
            game=game,
            image_base64=image_base64,
            shot_damage=user.shot_damage,
            shot_timeout=user.shot_timeout,
            location_context=json.dumps(all_user_locations, default=str),
            heading=heading,
        )
        # Only when asked: the column has a server default, and setting the
        # attribute to None explicitly would insert a null over the top of it.
        if time_created is not None:
            shot_entry.time_created = time_created
        self._session.add(shot_entry)

        user.num_bullets -= 1

        # Save to folder
        save_image(base64_image=image_base64, name=user.name)

        # Everything watching the queue - the admin's shot list, its nav-bar
        # counter, the spectator screen's feed - hears about the shot here
        # rather than in the route, so a shot fired by the demo drip announces
        # itself exactly like a shot fired by a player.
        self.announce_after_commit("shots", game_id)

        # The review is queued here for the same reason, and it is the half
        # that decides whether anybody ever *rules* on the shot: with no
        # review there is nothing for the auto-action drain to act on, so a
        # demo-fired shot sat at "waiting for admin" until an admin flipped
        # the recognition toggle off and on to sweep it up as backlog.
        #
        # Fired inline rather than queued, because it is not an announcement:
        # `enqueue_review` only creates a task, and a task cannot start until
        # the event loop regains control - which is after @db_scoped has
        # committed this shot and run the hook above.
        if review_enabled:
            from . import ai_shot_review

            ai_shot_review.enqueue_review(shot_id)

        return shot_id

    @db_scoped
    def get_own_shots(self) -> List[dict]:
        """
        A light summary of every shot this user has fired, newest first, for
        the user-facing shot history. Deliberately excludes the images: they
        are big and immutable, so the frontend fetches (and caches) them
        separately by id via get_own_shot_image, while this list stays cheap
        to re-poll every time a status changes.
        """
        shots = (
            self._session.query(Shot)
            .filter_by(user_id=self.user_id)
            .order_by(Shot.time_created.desc())
            .all()
        )

        # Naming a shot's target scores it against the whole game, so the
        # roster is fetched once for the list -- and not at all when no shot in
        # it is waiting on a suggested hit.
        users: Optional[List[User]] = None
        names: dict = {}

        me = self.get_user()

        out = []
        for shot in shots:
            target_name = None
            if shot.target_user_id:
                target = self._session.get(User, shot.target_user_id)
                target_name = target.name if target else None

            suggestion = _ai_suggestion(shot)
            ai_target_name = None
            if suggestion == "hit" and not shot.checked:
                if users is None:
                    users = self._game_users()
                    names = {user.id: user.name for user in users}
                ai_target_name = _ai_target_name(shot, users, names)

            out.append(
                {
                    "id": shot.id,
                    "time_created": shot.time_created,
                    "checked": shot.checked,
                    "result": shot.result,
                    "target_name": target_name,
                    "ai_review_state": shot.ai_review_state,
                    "ai_suggestion": suggestion,
                    "ai_target_name": ai_target_name,
                    # Lets the frontend name the weapon (react-ui/src/weapons.js's
                    # WEAPONS, shared with the admin queue) without a second
                    # round trip.
                    "shot_damage": shot.shot_damage,
                    "shot_timeout": shot.shot_timeout,
                    **self._appeal_fields(shot, me, APPEAL_PARTY_SHOOTER),
                }
            )

        return out

    @db_scoped
    def get_shots_received(self) -> List[dict]:
        """Every shot adjudicated as having hit this user, newest first.

        The other half of the shot history (roadmap R8): before this, a player
        who was hit got one private ticker line and nothing to appeal against.
        No new exposure - it is a photograph of them, taken of them, and the
        ticker has already named the shooter. Excludes the images for the same
        reason :meth:`get_own_shots` does.
        """
        shots = (
            self._session.query(Shot)
            .filter_by(target_user_id=self.user_id)
            .order_by(Shot.time_created.desc())
            .all()
        )

        me = self.get_user()

        return [
            {
                "id": shot.id,
                "time_created": shot.time_created,
                "result": shot.result,
                "shooter_name": shot.user.name if shot.user else None,
                **self._appeal_fields(shot, me, APPEAL_PARTY_TARGET),
            }
            for shot in shots
        ]

    def _appeal_fields(self, shot: Shot, user: User, party: str) -> dict:
        """What one party needs to know about appealing one shot. Shared by
        both shot lists so the two sides answer by the same rules."""
        return {
            "appeal_state": shot.appeal_state,
            "my_appeal_reason": appeal_reason(shot, party),
            "can_appeal": appeal_refusal(shot, user, party) is None,
        }

    @db_scoped
    def appeal_shot(self, shot_id: UUID, reason: str) -> None:
        """Contest the verdict on a shot this user was part of.

        Marks the shot contested and puts it in front of the admin: it changes
        no HP, no ammo and no ticker by itself, so an appeal can never corrupt
        the game state (roadmap R8). 404s for anybody who was not there rather
        than 403, the same posture :meth:`get_own_shot_image` takes - whether
        the id exists at all is nobody else's business.
        """
        shot = self._session.get(Shot, shot_id)
        party = appeal_party(shot, self.user_id) if shot else None
        if party is None:
            raise HTTPException(404, f"Shot {shot_id} not found")

        if reason not in APPEAL_REASONS:
            raise HTTPException(400, f"'{reason}' is not a reason to appeal")

        user = self.get_user()
        refusal = appeal_refusal(shot, user, party)
        if refusal:
            raise HTTPException(400, refusal)

        if party == APPEAL_PARTY_SHOOTER:
            shot.shooter_appeal_reason = reason
            other_party_id = shot.target_user_id
        else:
            shot.target_appeal_reason = reason
            other_party_id = shot.user_id

        shot.appeal_state = APPEAL_OPEN
        if shot.appealed_at is None:
            shot.appealed_at = time.time()
        user.appeals_remaining -= 1

        # @db_scoped fires this user's own update event on commit. The other
        # party's shot list has changed too, and every admin dashboard has a
        # new entry in its contested queue.
        if other_party_id is not None and other_party_id != self.user_id:
            asyncio_triggers.trigger_update_event("user", other_party_id)
        asyncio_triggers.trigger_update_event("shots", shot.game_id)

    def _game_users(self) -> List[User]:
        """Everybody in this user's game: the candidate set a photograph of
        theirs is scored against."""
        team = self.get_user().team
        if team is None:
            return []
        return (
            self._session.query(User)
            .join(Team, User.team_id == Team.id)
            .filter(Team.game_id == team.game_id)
            .all()
        )

    @db_scoped
    def get_own_shot_image(self, shot_id: UUID) -> str:
        """
        The full image for a shot this user was part of: one they fired, or
        one the verdict says hit them.

        The target sees it because they cannot appeal a photograph they were
        never shown, and it costs them nothing - it is a photograph of them,
        and the ticker has already named the shooter (roadmap R8).

        Responds 404 rather than 403 for a third party's shot: whether the id
        exists at all is nobody else's business.
        """
        shot = self._session.get(Shot, shot_id)

        if not shot or appeal_party(shot, self.user_id) is None:
            raise HTTPException(404, f"Shot {shot_id} not found")

        return shot.image_base64

    @db_scoped
    def collect_item(self, encoded_item: str) -> None:
        """
        Add the scanned item into a user's inventory

        Args:
            encoded_item (str): The item to collect, encoded as a base64 string.
            Optionally can be a URL with the item as a query parameter "d".
        """

        item = ItemModel.from_base64(encoded_item)

        item_validation_error = item.validate_signature()
        if item_validation_error:
            raise HTTPException(
                403, f"The scanned item is invalid - error {item_validation_error}"
            )

        user: User = self.get_user()

        if user.team is None:
            raise HTTPException(
                403,
                "Cannot collect item, you are not in a game. How did you even get here?",
            )

        item_from_db = self._get_item_from_database(item.id)

        already_collected = False

        if item_from_db:
            if item.collected_only_once:
                already_collected = True
            else:
                if item.collected_as_team:
                    team_ids = [u.team_id for u in item_from_db.users]
                    if user.team_id in team_ids:
                        already_collected = True
                else:
                    if user in item_from_db.users:
                        already_collected = True

        if already_collected:
            raise HTTPException(403, "Item has already been collected")

        try:
            do_item_actions(self, item)
        except RuntimeError as e:
            raise HTTPException(403, str(e))

        if item_from_db:
            user.items.append(item_from_db)
        else:
            user.items.append(
                Item(
                    id=item.id,
                    item_type=item.itype,
                    data=item.data_as_json(),
                    game=user.team.game,
                )
            )

    @db_scoped
    def get_circles(self):
        game_model: GameModel = self.get_game_model()

        if game_model is None:
            return None

        return {
            "exclusion_circle_lat": game_model.exclusion_circle_lat,
            "exclusion_circle_long": game_model.exclusion_circle_long,
            "exclusion_circle_radius": game_model.exclusion_circle_radius,
            "next_circle_lat": game_model.next_circle_lat,
            "next_circle_long": game_model.next_circle_long,
            "next_circle_radius": game_model.next_circle_radius,
            "drop_circle_lat": game_model.drop_circle_lat,
            "drop_circle_long": game_model.drop_circle_long,
            "drop_circle_radius": game_model.drop_circle_radius,
        }

    @db_scoped
    def get_messages(
        self, num, private=False, newest_first=True
    ) -> List[Tuple[str, str, Optional[UUID]]]:
        """
        Get ticker messages for this user

        Args:
            num (int): Number of messages to get
            private (bool, optional): If True, only get messages that are private for this user. Defaults to False.
            newest_first (bool, optional): If True, get the newest messages first. Defaults to True.

        Returns:
            List[Tuple[str,str,Optional[UUID]]]: A list of messages, each as a
            tuple of (type, message, shot id) - see Ticker.get_messages
        """
        user = self.get_user()

        if not user.team:
            return []

        return Ticker(
            game_id=user.team.game.id,
            session=self.get_session(),
            user_id=self.user_id if private else None,
        ).get_messages(num_messages=num, newest_first=newest_first)

    def generate_user_updates(self, timeout=None):
        """
        An async generator that yields None every time an update is available
        for this user

        Note that this does not hold a database session open, so it can be used
        in parallel with other database operations

        Args:
            timeout (int, optional): Maximum number of seconds to wait for an
            update. Defaults to no timeout.
        """

        # For now, just cheat and assume that any relevant updates for this user
        # will come with a ticker message
        return self.generate_ticker_updates(timeout=timeout)

    def generate_ticker_updates(self, timeout=None):
        """
        An async generator that yields None every time an update is available
        for this user's ticker

        Note that this does not hold a database session open, so it can be used
        in parallel with other database operations

        Args:
            timeout (int, optional): Maximum number of seconds to wait for an
            update. Defaults to no timeout.
        """

        with self:
            team_id = self.get_user().team_id
            if team_id:
                game_id = self.get_user().team.game_id

        if team_id is None:
            raise ValueError("User is not in a game")

        ticker = Ticker(
            game_id=game_id,
            user_id=self.user_id,
        )

        return ticker.generate_updates(timeout=timeout)

    @db_scoped
    def clear_unchecked_shots(
        self, since_time_created: datetime.datetime, since_shot_id: UUID
    ) -> int:
        """
        Invalidate this user's own unchecked shots, fired for the knockout
        that has just killed them.

        Only shots at or after ``(since_time_created, since_shot_id)`` -- the
        fatal shot's own tie-break, the same one
        AdminInterface.get_queue_head uses for a clock with 1s resolution --
        qualify, and the fatal shot itself is always excluded: it gets its
        own adjudication as a hit right after this call returns (including
        the self-shot edge case, where the fatal shot is one of this same
        user's own unchecked shots). A shot fired *before* the fatal one was
        taken while this user was still alive and playing fair; it is only
        sitting unchecked because the queue has not reached it yet, and
        invalidating it would wipe out a legitimate shot for no reason but
        bad luck in the queue order.

        Mechanically the same as an admin's refund - checked, no result,
        ammo back - but recorded as "invalidated" rather than "refunded" so
        the two are told apart: this one was never looked at by anybody,
        because its shooter was already out.

        Returns how many shots were invalidated, so the caller can decide
        whether there is anything to tell the player.
        """

        u = self.get_user()
        unchecked_shots = (
            self._session.query(Shot)
            .filter_by(user_id=self.user_id, team_id=u.team_id, checked=False)
            .filter(Shot.id != since_shot_id)
            .filter(
                or_(
                    Shot.time_created > since_time_created,
                    and_(
                        Shot.time_created == since_time_created,
                        Shot.id >= since_shot_id,
                    ),
                )
            )
            .all()
        )

        bullet_refunds = 0
        for shot in unchecked_shots:
            shot.checked = True
            shot.result = "invalidated"
            bullet_refunds += 1

        self.award_ammo(bullet_refunds)
        return bullet_refunds

    def set_location(
        self, latitute: float, longitude: float, accuracy: Optional[float] = None
    ):
        """
        Record the location of the user

        ``accuracy`` is the browser's own radius-in-metres estimate for the
        fix, and is None when the client didn't send one.

        This method should be quick and _does not_ prompt a user update event
        """
        timestamp = time.time()

        # Make our own session, detached from the usual machinery to ensure no update events
        with session_scope() as session:
            user = session.get(User, self.user_id)
            user.latitude = latitute
            user.longitude = longitude
            user.location_timestamp = timestamp
            user.location_accuracy = accuracy

    async def generate_user_updates(self, timeout=None):
        """
        A generator that yields None every time an update is available for this
        user, or at most after timeout seconds

        Does not use the database.
        """
        while True:
            # Lookup / make an event for this user and subscribe to it
            event = get_trigger_event("user", self.user_id)

            try:
                logger.info("Subscribing to event %s for user %s", event, self.user_id)
                await asyncio.wait_for(event.wait(), timeout=timeout)
                logger.info(f"Event received for user {self.user_id}")
                yield
            except asyncio.TimeoutError:
                logger.info(f"Event timeout for user {self.user_id}")
                yield
