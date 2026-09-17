import logging
import os
import subprocess
from contextlib import contextmanager
from enum import Enum
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from uuid import UUID

import pydantic
from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.responses import StreamingResponse

from . import demo_game
from . import how_it_works as how_it_works_payload
from . import identity_admin
from . import identity_demo
from .admin_interface import CircleTypes
from .dotenv import load_env_vars
from .item_actions import WEAPON_NAME_LOOKUP
from .join_codes import JoinCodeModel
from .ticker_message_dispatcher import send_generic_message
from .venues import ACTIVE_VENUE
from .venues import Venue


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
    Path("./logs/").mkdir(exist_ok=True)
    rotating_handler = RotatingFileHandler("./logs/backend.log", backupCount=10)

    # Configure the format for log messages
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    rotating_handler.setFormatter(formatter)

    root_logger.addHandler(rotating_handler)
    rotating_handler.doRollover()

    # Set the uvicorn logger to inherit from the root logger
    uvicorn_logger.setLevel("NOTSET")

    # Set the root logger level to LOG_LEVEL if specified
    if "LOG_LEVEL" in os.environ:
        root_logger.setLevel(os.environ.get("LOG_LEVEL"))
        root_logger.warning(
            "Setting log level to %s from env var config", os.environ.get("LOG_LEVEL")
        )
    else:
        root_logger.setLevel(logging.INFO)
        root_logger.warning("Setting log level to INFO by default")

    if "LOG_OVERRIDES" in os.environ:
        overrides = os.environ["LOG_OVERRIDES"]

        for override in overrides.split(","):
            target_logger, level = override.split(":")

            target_logger = target_logger.strip()
            level = level.strip()

            logging.warning('Setting logger "%s" to level "%s"[]', target_logger, level)
            logging.getLogger(target_logger).setLevel(level)


load_env_vars()
setup_logging()

from . import ai_shot_review
from . import generate_pub_pages
from . import generate_qr_items
from . import image_processing
from . import map_poster
from . import printables
from . import reference_photos
from . import shot_auto_actions
from . import shot_escalation
from . import shot_vision
from . import sse_event_streams
from . import team_cards
from .admin_auth import is_admin_authed
from .admin_auth import mark_admin_authed
from .admin_auth import require_admin_auth

# Import these after logging is setup since they might have side effects (e.g. database setup)
from .admin_interface import AdminInterface
from .model import AI_REVIEW_STATE_DONE
from .model import DEFAULT_SHOT_TIMEOUT
from .model import GameModel
from .model import ShotModel
from .next_event import NextEventKind
from .ticker import Ticker
from .user_id import get_user_id
from .user_interface import UserInterface
from .vision_client import VisionError
from .vision_client import fetch_openrouter_key_balance
from .vision_client import get_escalation_client
from .vision_client import get_vision_client

app = FastAPI()
router = APIRouter()
logger = logging.getLogger(__name__)

if "SECRET_KEY" not in os.environ:
    logger.warning("No SECRET_KEY found in environment, using default value")
    os.environ["SECRET_KEY"] = "none"

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SECRET_KEY"],
    max_age=60 * 60 * 24 * 365 * 10,
)


@router.get("/hello")
async def hello():
    return {"msg": "Hello world!"}


def _current_version() -> str:
    """Which code this is running. Deployments have the revision baked into
    the installed package at build time; when developing from a checkout
    instead, ask git directly."""
    version_file = Path(__file__).resolve().parent / "VERSION"
    if version_file.exists():
        version = version_file.read_text().strip()
        if version:
            return version

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


VERSION = _current_version()


@router.get("/get_version")
async def get_version() -> Dict[str, str]:
    return {"version": VERSION}


@router.get("/my_id")
async def get_my_id(
    user_id=Depends(get_user_id),
) -> UUID:
    return user_id


@router.get("/user_info")
async def get_user_info(
    user_id=Depends(get_user_id),
):
    with UserInterface(user_id) as ui:
        return ui.get_user_model()


@router.get("/get_venue")
async def get_venue() -> Venue:
    """The place this game is being played: its map, that map's
    georeferencing, and its landmarks. See backend/venues.py."""
    return ACTIVE_VENUE


@router.get("/get_circles")
async def get_circles(
    user_id=Depends(get_user_id),
):
    with UserInterface(user_id) as ui:
        return ui.get_circles()


@router.get("/radar")
async def get_radar(
    user_id=Depends(get_user_id),
):
    """Where everybody else was last seen, for a player holding a live radar
    (M6.1). A 403 while no radar is running, so the map can stop polling."""
    with UserInterface(user_id) as ui:
        return ui.get_radar()


class _Shot(BaseModel):
    photo: str
    # Degrees clockwise from north at the moment of capture. Optional on
    # purpose: a client with no compass, or a player who refused the
    # permission, still gets to fire.
    heading: Optional[float] = None


@router.post("/submit_shot")
async def submit_shot(
    shot: _Shot,
    user_id=Depends(get_user_id),
):
    logger.info("Received shot from user %s", user_id)

    # Waking the shot queue and queueing the review belong to
    # UserInterface.submit_shot, not here: this route is not the only thing
    # that fires a shot (backend/test_world/replay.py is the other), and the
    # two must not be able to drift apart.
    with UserInterface(user_id) as ui:
        shot_id = ui.submit_shot(shot.photo, heading=shot.heading)

    return shot_id


@router.get("/user_shots")
async def get_user_shots(
    user_id=Depends(get_user_id),
):
    """This user's own shots, newest first, without the images"""
    with UserInterface(user_id) as ui:
        return ui.get_own_shots()


@router.get("/user_shots_received")
async def get_user_shots_received(
    user_id=Depends(get_user_id),
):
    """The shots ruled to have hit this user, newest first, without the images"""
    with UserInterface(user_id) as ui:
        return ui.get_shots_received()


@router.post("/appeal_shot")
async def appeal_shot(
    shot_id: UUID,
    reason: str,
    user_id=Depends(get_user_id),
):
    """Contest the verdict on a shot this user was part of (roadmap R8).

    Marks it contested and puts it in front of the admin; it changes nothing
    about the game state by itself.
    """
    with UserInterface(user_id) as ui:
        ui.appeal_shot(shot_id, reason)
    return {"appealed": True}


@router.get("/user_shot_image")
async def get_user_shot_image(
    shot_id: UUID,
    user_id=Depends(get_user_id),
):
    """The image for one of this user's own shots. Immutable, so the frontend
    caches these by id and only ever fetches each one once."""
    with UserInterface(user_id) as ui:
        return {"image_base64": ui.get_own_shot_image(shot_id)}


@router.post("/set_name")
async def set_name(
    name: str,
    user_id=Depends(get_user_id),
):
    logger.info("Changing user %s name to %s", user_id, name)
    with UserInterface(user_id) as ui:
        ui.set_name(name)


class _EncodedJoinCode(BaseModel):
    data: str


def _decoded_join_code(data: str) -> JoinCodeModel:
    """Decode and signature-check a join code, the way every join-code
    endpoint must. Raises the same ``HTTPException``s ``join_game`` always
    has, so later endpoints (e.g. ``join_options``) can reuse this rather
    than re-deriving the checks.
    """
    try:
        code = JoinCodeModel.from_base64(data)
    except ValueError:
        raise HTTPException(400, "Malformed data")

    code_validation_error = code.validate_signature()
    if code_validation_error:
        raise HTTPException(
            403, f"The scanned join code is invalid - error {code_validation_error}"
        )

    return code


@router.post("/join_game")
async def join_game(
    encoded_code: _EncodedJoinCode,
    user_id=Depends(get_user_id),
):
    """Join a game or a team by scanning a signed join code.

    The body is ``{"data": <url-or-b64>}``, same shape as collect_item. A
    code with a concrete ``slot`` claims it immediately (unchanged). A code
    with no slot is either the game-wide sign-up link or a team's door code
    (roadmap R15): a *team* code scanned by somebody who already holds an
    outfit in the game puts them in that team, keeping the outfit, and hands
    back their row with ``joined``. Any other slot-less scan - a game code,
    or a team code by somebody with no outfit yet - writes nothing and hands
    back ``needs_pick`` so the frontend routes the player to the outfit
    picker, which joins the team as part of the pick when the code names one.
    """
    code = _decoded_join_code(encoded_code.data)

    logger.info(
        "User %s joining game %s team %s with slot %s",
        user_id,
        code.game_id,
        code.team_id,
        code.slot,
    )

    if code.slot is not None:
        with _identity_admin_errors():
            return identity_admin.claim_join_slot(user_id, code)

    admin = AdminInterface()
    admin.get_game_model(code.game_id)  # 404s if missing
    team = None
    if code.team_id is not None:
        team = admin.get_team_model(code.team_id)  # 404s if missing
        if team.game_id != code.game_id:
            raise HTTPException(400, "join code's team does not belong to its game")

    # Scanning the game's roster rather than UserInterface.get_user(), which
    # would mint a User row for a link-preview bot (see join_options).
    scanner = next(
        (u for u in admin.get_users_for_game(code.game_id) if u.id == user_id), None
    )
    if team is not None and scanner is not None and scanner.identity_slot is not None:
        with _identity_admin_errors():
            row = identity_admin.join_team_by_code(user_id, code)
        return {"joined": True, **row}

    return {
        "needs_pick": True,
        "team_id": team.id if team else None,
        "team_name": team.name if team else None,
    }


@router.get("/join_options")
async def join_options(data: str, user_id=Depends(get_user_id)) -> dict:
    """The outfit-picking page's first load: team identity, palette and the
    caller's own state if they have one. Non-mutating on purpose - see
    ``identity_admin.join_options``."""
    code = _decoded_join_code(data)
    with _identity_admin_errors():
        return identity_admin.join_options(user_id, code)


class _OutfitOptionsRequest(BaseModel):
    data: str
    wardrobe: Dict[str, List[str]] = {}
    relaxed: bool = False
    page: int = 0


@router.post("/outfit_options")
async def outfit_options(
    request: _OutfitOptionsRequest, user_id=Depends(get_user_id)
) -> dict:
    """A ranked, paginated page of candidate outfits. A POST because the
    wardrobe is a body, but it writes nothing - see
    ``identity_admin.outfit_options_page``."""
    code = _decoded_join_code(request.data)
    with _identity_admin_errors():
        return identity_admin.outfit_options_page(
            user_id, code, request.wardrobe, request.relaxed, request.page
        )


class _PickOutfitRequest(BaseModel):
    data: str
    wardrobe: Dict[str, List[str]] = {}
    appearance: Dict[str, str] = {}
    confirmed: bool = False


@router.post("/pick_outfit")
async def pick_outfit(
    request: _PickOutfitRequest, user_id=Depends(get_user_id)
) -> dict:
    """Claim a picked outfit - see ``identity_admin.pick_outfit``."""
    code = _decoded_join_code(request.data)
    with _identity_admin_errors():
        return identity_admin.pick_outfit(
            user_id, code, request.wardrobe, request.appearance, request.confirmed
        )


@router.get("/how_it_works")
async def how_it_works(user_id=Depends(get_user_id)) -> dict:
    """The figures on the ``/how-it-works`` essay, for this reader.

    Non-mutating, and unauthenticated beyond the session cookie everyone
    already has: the page is linked from the outfit picker and a reader who
    has picked nothing still gets the general figures.
    """
    return how_it_works_payload.how_it_works(user_id)


class _EncodedItem(BaseModel):
    data: str


@router.post("/collect_item")
async def collect_item(
    encoded_item: _EncodedItem,
    user_id=Depends(get_user_id),
):
    try:
        with UserInterface(user_id) as ui:
            return ui.collect_item(encoded_item.data)
    except ValueError:
        raise HTTPException(400, "Malformed data")


@router.get("/ticker_messages")
async def get_ticker_messages(
    num_messages=3,
    user_id=Depends(get_user_id),
):
    return UserInterface(user_id).get_messages(num_messages, private=True)


@router.get("/get_users")
async def get_users(game_id: str = None, team_id: str = None):
    if game_id is not None:
        try:
            game_id = UUID(game_id)
        except ValueError as e:
            raise HTTPException(400, str(e))
    if team_id is not None:
        try:
            team_id = UUID(team_id)
        except ValueError as e:
            raise HTTPException(400, str(e))

    return AdminInterface().get_users(game_id=game_id, team_id=team_id)


@router.get("/get_scoreboard")
async def get_scoreboard(user_id=Depends(get_user_id)):
    with UserInterface(user_id) as ui:
        game_id = ui.get_user_model().game_id

    if game_id is None:
        raise HTTPException(404, "User is not in a game")

    return AdminInterface().get_scoreboard(game_id)


@router.post("/set_location")
async def set_location(
    latitude: float,
    longitude: float,
    accuracy: Optional[float] = None,
    user_id=Depends(get_user_id),
):
    logger.info("Setting location for user %s to %f, %f", user_id, latitude, longitude)
    with UserInterface(user_id) as ui:
        ui.set_location(latitude, longitude, accuracy=accuracy)


######## ADMIN ###########


def admin_method(path: str, method: str = "POST"):
    def decorator(func):
        target = router.get if method == "GET" else router.post

        @target(path, dependencies=[Depends(require_admin_auth)])
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


@router.get("/admin_is_authed")
async def admin_is_authed(
    is_admin_authed=Depends(is_admin_authed),
) -> bool:
    return is_admin_authed


@router.post("/admin_authenticate")
async def admin_authenticate(request: Request, password: str) -> bool:
    return mark_admin_authed(request, password)


@admin_method(path="/admin_create_game", method="POST")
async def admin_create_game() -> UUID:
    game_id = AdminInterface().create_game()
    logger.info("Created new game with id = %s", game_id)
    return game_id


@admin_method(path="/admin_create_team", method="POST")
async def admin_create_team(game_id: UUID, team_name: str) -> UUID:
    logger.info("Creating new team '%s' for game %s", team_name, game_id)
    return AdminInterface().create_team(game_id, team_name)


@admin_method(path="/admin_set_team_name", method="POST")
async def admin_set_team_name(team_id: UUID, name: str) -> None:
    logger.info("Renaming team %s to '%s'", team_id, name)
    AdminInterface().set_team_name(team_id=team_id, name=name)


@admin_method(path="/admin_delete_team", method="POST")
async def admin_delete_team(team_id: UUID) -> None:
    logger.info("admin_delete_team %s", team_id)
    AdminInterface().delete_team(team_id)


@admin_method(path="/admin_delete_game", method="POST")
async def admin_delete_game(game_id: UUID) -> None:
    logger.info("admin_delete_game %s", game_id)
    AdminInterface().delete_game(game_id)


@admin_method(path="/admin_add_user_to_team", method="POST")
async def admin_add_user_to_team(
    user_id: UUID, team_id: UUID, slot: Optional[int] = None
) -> None:
    """Put a user in a team and, optionally, assign them an identity slot.

    Not atomic: the team join commits before the slot is validated, so a
    rejected slot leaves the user in the team and returns 400 - the admin
    repairs the slot via the identity page.
    """
    logger.info("Adding user %s to team %s (slot %s)", user_id, team_id, slot)
    AdminInterface().add_user_to_team(user_id, team_id)
    if slot is not None:
        with _identity_admin_errors():
            identity_admin.set_identity(
                identity_admin.IdentitySetRequest(user_id=user_id, slot=slot)
            )


@admin_method("/admin_list_games", method="GET")
async def admin_list_games() -> List[GameModel]:
    logger.info("admin_list_games")
    return AdminInterface().get_games()


@admin_method("/admin_get_shots", method="GET")
async def admin_get_shots(limit=5):
    num_in_queue, filtered_shots = AdminInterface().get_unchecked_shots(limit=limit)
    return {"numInQueue": num_in_queue, "shots": filtered_shots}


@admin_method("/admin_get_shots_info", method="GET")
async def admin_get_shots_info(include_checked: bool = False) -> list[UUID]:
    return AdminInterface().get_shots_ids(include_checked=include_checked)


@admin_method("/admin_get_contested_shots_info", method="GET")
async def admin_get_contested_shots_info() -> list[UUID]:
    """The contested queue: shots with an open appeal, oldest complaint first.

    Separate from admin_get_shots_info because these are checked shots and so
    are not in the live queue at all - they are an argument to settle, not a
    backlog to drain.
    """
    return AdminInterface().get_contested_shot_ids()


@admin_method("/admin_get_shot_appeal", method="GET")
async def admin_get_shot_appeal(shot_id: UUID) -> dict:
    """Who is contesting one shot, and on what grounds."""
    return AdminInterface().get_shot_appeal(shot_id)


@admin_method("/admin_get_shot_notes", method="GET")
async def admin_get_shot_notes(shot_id: UUID) -> dict:
    # Separate from the shot model itself for the same reason as the AI
    # review: ShotCache caches shot models permanently, so anything editable
    # must live behind its own endpoint.
    return {"notes": AdminInterface().get_shot_notes(shot_id)}


@admin_method(path="/admin_set_shot_notes", method="POST")
async def admin_set_shot_notes(shot_id: UUID, notes: str):
    AdminInterface().set_shot_notes(shot_id, notes)


@admin_method("/admin_get_shot", method="GET")
async def admin_get_shot(shot_id: UUID) -> ShotModel:
    shot_model = AdminInterface().get_shot_model(shot_id=shot_id)
    return AdminInterface.markup_shot_model(shot_model)


@admin_method(path="/admin_shot_hit_user", method="POST")
async def admin_shot_hit_user(shot_id: UUID, target_user_id: UUID):
    game_id = AdminInterface().get_shot_game_id(shot_id)
    AdminInterface().hit_user(shot_id, target_user_id)
    # Resolving the head may unblock confident reviews queued behind it. The
    # drain lives here, not inside hit_user, so it cannot recurse.
    shot_auto_actions.process_queue_head(game_id)


@admin_method(path="/admin_set_hp", method="POST")
async def admin_set_hp(user_id, num: int = 1):
    AdminInterface().set_user_HP(user_id, num=num)


Weapon = Enum("Weapon", {v: v for k, v in WEAPON_NAME_LOOKUP.items()})
WEAPON_DATA_LOOKUP = {Weapon(v): k for k, v in WEAPON_NAME_LOOKUP.items()}


@admin_method(path="/admin_set_weapon", method="POST")
async def admin_set_weapon(user_id, weapon: Weapon):  # type: ignore
    shot_damage, shot_timeout = WEAPON_DATA_LOOKUP[weapon]
    UserInterface(user_id=user_id).set_weapon_data(
        damage=shot_damage, fire_delay=shot_timeout
    )


@admin_method(path="/admin_hit_user", method="POST")
async def admin_hit_user(user_id, num: int = 1):
    AdminInterface().hit_user_by_admin(user_id, num=num)


@admin_method(path="/admin_give_ammo", method="POST")
async def admin_give_ammo(user_id, num: int = 1):
    AdminInterface().award_user_ammo(user_id, num=num)


@admin_method(path="/admin_give_appeals", method="POST")
async def admin_give_appeals(user_id, num: int = 1):
    AdminInterface().award_user_appeals(user_id, num=num)


@admin_method(path="/admin_refund_shot", method="POST")
async def admin_refund_shot(shot_id):
    game_id = AdminInterface().get_shot_game_id(shot_id)
    AdminInterface().refund_shot(shot_id)
    shot_auto_actions.process_queue_head(game_id)


@admin_method(path="/admin_mark_shot_missed", method="POST")
async def admin_mark_shot_missed(shot_id):
    game_id = AdminInterface().get_shot_game_id(shot_id)
    AdminInterface().mark_shot_missed(shot_id)
    shot_auto_actions.process_queue_head(game_id)


@admin_method(path="/admin_mark_shot_bystander", method="POST")
async def admin_mark_shot_bystander(shot_id):
    game_id = AdminInterface().get_shot_game_id(shot_id)
    AdminInterface().mark_shot_bystander(shot_id)
    shot_auto_actions.process_queue_head(game_id)


@admin_method(path="/admin_set_ai_shot_review", method="POST")
async def admin_set_ai_shot_review(game_id: UUID, enabled: bool):
    """Turn AI review of the shot queue on or off for a game.

    Switching it on also puts the shots already waiting in the queue through,
    not just the ones that arrive afterwards.
    """
    backlog = AdminInterface().set_ai_shot_review_enabled(game_id, enabled)
    started = ai_shot_review.enqueue_reviews(backlog)
    return {"enabled": enabled, "backlog": len(backlog), "started": started}


@admin_method(path="/admin_set_ai_auto_actions", method="POST")
async def admin_set_ai_auto_actions(game_id: UUID, enabled: bool):
    """Turn acting on confident AI verdicts on or off for a game.

    Independent of the review toggle: reviews only annotate, this flag decides
    whether confident verdicts resolve the head of the queue. Switching it on
    also starts escalations for the whole reviewed backlog that needs one
    (shot_auto_actions.escalate_backlog) before draining an already-reviewed
    confident head that was waiting for it.
    """
    AdminInterface().set_ai_auto_actions_enabled(game_id, enabled)
    if enabled:
        shot_auto_actions.escalate_backlog(game_id)
        shot_auto_actions.process_queue_head(game_id)
    return {"enabled": enabled}


@admin_method(path="/admin_set_ai_escalation", method="POST")
async def admin_set_ai_escalation(game_id: UUID, enabled: bool):
    """Turn escalation of hard shots to the stronger model on or off for a game.

    A kill switch inside auto-actions rather than a third opt-in: with it off,
    a shot the ladder wants escalated waits for the admin instead, exactly as
    it does with no escalation model configured. Switching it on also starts
    escalations for the whole backlog that needs one
    (shot_auto_actions.escalate_backlog), so a head that has been sitting on
    the escalate rung gets its second opinion now rather than whenever the
    queue next moves.
    """
    AdminInterface().set_ai_escalation_enabled(game_id, enabled)
    if enabled:
        shot_auto_actions.escalate_backlog(game_id)
        shot_auto_actions.process_queue_head(game_id)
    return {"enabled": enabled}


@admin_method(path="/admin_set_ai_resolve_everything", method="POST")
async def admin_set_ai_resolve_everything(game_id: UUID, enabled: bool):
    """Turn "resolve everything" on or off for a game.

    With it on the drain resolves an unconfident or unidentifiable head as best
    the reading allows rather than handing it to the admin - the bet appeals
    (roadmap R8) make safe, because an automatic error is then loud and
    recoverable. Switching it on also drains the heads that were waiting for
    exactly this.
    """
    AdminInterface().set_ai_resolve_everything_enabled(game_id, enabled)
    if enabled:
        shot_auto_actions.process_queue_head(game_id)
    return {"enabled": enabled}


@admin_method(path="/admin_get_openrouter_balance", method="GET")
async def admin_get_openrouter_balance() -> dict:
    """The remaining credit balance on the configured OpenRouter key, for the
    admin footer readout (CharlesBot's fuel gauge). ``configured: False`` when
    no key is set at all; a failed lookup still returns 200 with an ``error``
    so a flaky OpenRouter call doesn't blow up the whole admin page."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"configured": False}

    try:
        balance = await fetch_openrouter_key_balance(api_key)
    except VisionError as e:
        return {"configured": True, "error": str(e)}

    return {"configured": True, **balance}


@admin_method("/admin_get_shot_ai_review", method="GET")
async def admin_get_shot_ai_review(shot_id: UUID):
    """The AI's reading of one shot.

    Separate from admin_get_shot because the frontend caches shot responses
    permanently by id, and a review that arrives afterwards would never be seen.
    """
    return AdminInterface().get_shot_ai_review(shot_id)


@admin_method(path="/admin_review_shot", method="POST")
async def admin_review_shot(shot_id: UUID):
    """Review (or re-review) one shot now, whatever the toggle says.

    The fast loop for tuning the prompt or trying a different OPENROUTER_MODEL.
    """
    if ai_shot_review.enqueue_review(shot_id) is None:
        raise HTTPException(503, "No vision model configured - set OPENROUTER_API_KEY")
    return {"queued": True}


@admin_method(path="/admin_escalate_shot", method="POST")
async def admin_escalate_shot(shot_id: UUID):
    """Escalate one shot to the stronger model now, whatever the toggles say.

    The admin asking for the second opinion by hand, so neither the
    auto-actions toggle nor the escalation one gates it. Re-running over an
    existing escalation is the point of the button as often as not: the old
    verdict is replaced by a fresh one.
    """
    client = get_escalation_client()
    if client is None:
        raise HTTPException(400, "No vision model configured - set OPENROUTER_API_KEY")
    review = AdminInterface().get_shot_ai_review(shot_id)
    if review["state"] != AI_REVIEW_STATE_DONE or not review["review"]:
        # The candidate ranking the stronger model is given is built from that
        # reading, so there is nothing to escalate without one.
        raise HTTPException(
            400,
            "This shot has no completed AI review to escalate from - run the AI "
            "review first",
        )
    shot_escalation.enqueue_escalation(shot_id, client)
    return {"queued": True}


class _ReplayRequest(BaseModel):
    shot_id: UUID
    prompt: Optional[str] = None
    # The shape of the exchange and the shape of the reply. Both travel with
    # the prompt: a custom prompt answered against the pipeline's own schema,
    # through the pipeline's own follow-up turns, has been overruled -- the
    # model can only answer the question the schema asks, whatever it was told.
    zoom_mode: str = shot_vision.ZOOM_SCREENED
    # Named "response_schema" rather than "schema": pydantic's BaseModel owns
    # the latter.
    response_schema: Optional[dict] = None
    reasoning_effort: Optional[str] = None


@admin_method(path="/admin_replay_shot_review", method="POST")
async def admin_replay_shot_review(request: _ReplayRequest) -> dict:
    """Fire one shot through the vision pipeline and return the reading.

    The admin replay workbench: the same pipeline as a real review (aim marker,
    resize, the zoom), but with the whole contract -- prompt, conversation
    shape and response schema -- customisable on the fly, and nothing stored:
    no state changes, no events, no auto-actions. A reply that is not a
    standard reading comes back raw rather than as an error, since under a
    custom contract that is the answer rather than a failure.
    ``reasoning_effort`` overrides OPENROUTER_REASONING_EFFORT for this replay
    only, for trialling reasoning depth against real shots.
    """
    if request.zoom_mode not in shot_vision.ZOOM_MODES:
        raise HTTPException(
            400,
            f"Unknown zoom_mode {request.zoom_mode!r}; "
            f"expected one of {', '.join(shot_vision.ZOOM_MODES)}",
        )
    client = get_vision_client(reasoning_effort=request.reasoning_effort)
    if client is None:
        raise HTTPException(503, "No vision model configured - set OPENROUTER_API_KEY")
    try:
        return await ai_shot_review.replay_shot_review(
            request.shot_id,
            client,
            prompt=request.prompt or None,
            zoom_mode=request.zoom_mode,
            schema=request.response_schema or None,
        )
    except Exception as e:
        raise HTTPException(502, f"Replay failed: {e}")


class _EscalationReplayRequest(BaseModel):
    shot_id: UUID
    reasoning_effort: Optional[str] = None


@admin_method(path="/admin_replay_shot_escalation", method="POST")
async def admin_replay_shot_escalation(request: _EscalationReplayRequest) -> dict:
    """Escalate one shot and return the payload, storing nothing.

    The workbench's second rung: what the *stronger* model made of a shot, with
    its full transcript, without spending a verdict on the shot the way the
    queue's "Run escalated review" button does. Unlike the review replay above
    there is no contract to vary -- the escalation prompt is assembled from the
    candidate ranking, so the page's prompt, schema and zoom controls do not
    reach this path; ``reasoning_effort`` does, overriding
    OPENROUTER_ESCALATION_REASONING_EFFORT for this call only.

    The same precondition as admin_escalate_shot: the ranking is built from the
    cheap pass's stored reading, so a shot nobody has reviewed has nothing to
    escalate from.
    """
    client = get_escalation_client(reasoning_effort=request.reasoning_effort)
    if client is None:
        raise HTTPException(503, "No vision model configured - set OPENROUTER_API_KEY")
    review = AdminInterface().get_shot_ai_review(request.shot_id)
    if review["state"] != AI_REVIEW_STATE_DONE or not review["review"]:
        raise HTTPException(
            400,
            "This shot has no completed AI review to escalate from - run the AI "
            "review first",
        )
    try:
        return await shot_escalation.replay_shot_escalation(request.shot_id, client)
    except Exception as e:
        raise HTTPException(502, f"Escalation replay failed: {e}")


@admin_method("/admin_get_shot_vision_images", method="GET")
async def admin_get_shot_vision_images(shot_id: UUID) -> dict:
    """Return the shot image formatted exactly as the vision model sees it, at
    every zoom level the pipeline can reach.

    Three images are returned:
    - full: the whole frame with aim marker, downscaled to 1024px max (what
      prepare_for_vision produces)
    - zoomed: the centre 12.5% of the original, cropped and upscaled to 1024px
      with a fresh aim marker -- the first zoom (what zoom_image produces)
    - zoomed2: the centre 12.5% of *that*, i.e. 1/ZOOM_FACTOR**2 of the
      original -- the second zoom, spent only if the first wasn't enough

    Which of these a replay actually used is ShotVisionResult.zoom_count, not
    anything about the shot itself, so the caller decides how many to show.
    All three are JPEG data URLs ready to render in <img>.
    """
    original = AdminInterface().get_shot_image_base64(shot_id)

    # Full frame: aim marker + downscale to 1024px max
    full = image_processing.prepare_for_vision(
        image_processing.draw_aim_marker(original)
    )

    # Zoomed frames: successive centre crops from ORIGINAL, each upscaled to
    # 1024px with its own aim marker, compounding as ZOOM_FACTOR**level exactly
    # as backend.ai_shot_review's zoom_provider does.
    zoomed = image_processing.zoom_image(original, factor=shot_vision.ZOOM_FACTOR)
    zoomed2 = image_processing.zoom_image(original, factor=shot_vision.ZOOM_FACTOR**2)

    return {"full": full, "zoomed": zoomed, "zoomed2": zoomed2}


@admin_method("/admin_get_default_vision_prompt", method="GET")
async def admin_get_default_vision_prompt(
    zoom_mode: str = shot_vision.ZOOM_SCREENED,
) -> dict:
    """The contract the live pipeline currently uses, to seed the workbench's.

    Both halves of it: the prompt and the JSON schema the reply is asked to
    match. ``zoom_mode`` picks which conversation shape the prompt should
    describe -- the zoom wording is part of the prompt, so the default text
    only makes sense alongside the exchange it is about to be sent into.
    """
    if zoom_mode not in shot_vision.ZOOM_MODES:
        raise HTTPException(
            400,
            f"Unknown zoom_mode {zoom_mode!r}; "
            f"expected one of {', '.join(shot_vision.ZOOM_MODES)}",
        )
    return {
        "prompt": shot_vision.build_prompt(zoom_mode=zoom_mode),
        "schema": shot_vision.build_schema(),
    }


class _ReferencePhoto(BaseModel):
    user_id: UUID
    photo: str


@admin_method(path="/admin_capture_reference_photo", method="POST")
async def admin_capture_reference_photo(reference: _ReferencePhoto) -> UUID:
    """Store the kit-check photo of one player, taken at the door.

    The review that follows is not gated on the game's ai_shot_review toggle:
    that toggle is about annotating the shot queue, and this is its own
    feature. It is only skipped when there is no vision client at all, in
    which case the photo is still stored and the review state simply stays
    null -- capture must never fail because the AI is off.
    """
    if not image_processing.is_decodable(reference.photo):
        raise HTTPException(400, "The camera had no frame yet; try again")
    logger.info("Storing a reference photo for user %s", reference.user_id)
    AdminInterface().set_reference_photo(reference.user_id, reference.photo)
    reference_photos.enqueue_review(reference.user_id)
    return reference.user_id


@admin_method("/admin_get_reference_photo", method="GET")
async def admin_get_reference_photo(user_id: UUID) -> str:
    photo = AdminInterface().get_reference_photo(user_id)
    if not photo:
        raise HTTPException(404, f"No reference photo stored for user {user_id}")
    return photo


@admin_method("/admin_get_reference_review", method="GET")
async def admin_get_reference_review(user_id: UUID):
    """The AI's reading of one player's reference photo, plus who it decoded to."""
    return AdminInterface().get_reference_review(user_id)


@admin_method(path="/admin_review_reference_photo", method="POST")
async def admin_review_reference_photo(user_id: UUID):
    """Review (or re-review) the stored reference photo of one player now."""
    if not AdminInterface().get_reference_photo(user_id):
        raise HTTPException(404, f"No reference photo stored for user {user_id}")
    if reference_photos.enqueue_review(user_id) is None:
        raise HTTPException(503, "No vision model configured - set OPENROUTER_API_KEY")
    return {"queued": True}


@admin_method(path="/admin_delete_reference_photo", method="POST")
async def admin_delete_reference_photo(user_id: UUID):
    AdminInterface().clear_reference_photo(user_id)


@admin_method("/admin_get_reference_photo_status", method="GET")
async def admin_get_reference_photo_status(game_id: UUID) -> List[dict]:
    """The door roster: every player in the game and how their kit check went."""
    return AdminInterface().get_reference_photo_status(game_id)


@admin_method("/admin_get_recent_shots", method="GET")
async def admin_get_recent_shots(game_id: UUID, limit: int = 6) -> List[dict]:
    """The last few shots of a game, newest first, with their adjudication.

    Feeds the spectator screen (react-ui/src/SpectatorView.js). Carries no
    image: the photographs come one at a time from admin_get_shot_thumbnail,
    which the client caches by id.
    """
    return AdminInterface().get_recent_shots(game_id, limit=limit)


@admin_method("/admin_get_shot_thumbnail", method="GET")
async def admin_get_shot_thumbnail(shot_id: UUID) -> dict:
    """One shot's photograph, downsized for a screen rather than a model."""
    return {"image_base64": AdminInterface().get_shot_thumbnail(shot_id)}


@admin_method("/admin_get_scoreboard", method="GET")
async def admin_get_scoreboard(game_id: UUID) -> dict:
    """The scoreboard for a game, keyed by game rather than by the caller.

    The player-facing /get_scoreboard resolves the game from the caller's own
    session and 404s if they are not in one -- which a browser wired to a TV
    never is. Same table, addressed the way the admin pages address things.
    """
    return AdminInterface().get_scoreboard(game_id)


@admin_method("/admin_get_locations", method="GET")
async def admin_get_locations(game_id=None):
    """
    Get the locations of all users in a game

    :param game_id: The game to get locations for. If None, use the first game.
    """
    return AdminInterface().get_locations(game_id=game_id)


@admin_method(path="/admin_make_new_item", method="POST")
async def admin_make_new_item(
    item_type: str,
    item_data: Dict,
    collected_only_once=True,
    collected_as_team=False,
    batch: Optional[str] = generate_qr_items.DEFAULT_BATCH,
    unlimited: bool = False,
):
    logger.info("admin_make_new_item")
    try:
        encoded_url = AdminInterface().make_new_item(
            item_type,
            item_data,
            collected_only_once=collected_only_once,
            collected_as_team=collected_as_team,
            batch=batch,
            unlimited=unlimited,
        )
    except pydantic.ValidationError as e:
        raise HTTPException(400, f"Invalid submission - {e}")

    return {
        "itype": item_type,
        "item_data": item_data,
        "encoded_item": encoded_url,
        "encoded_url": encoded_url,
    }


@admin_method(path="/admin_set_game_active", method="POST")
async def admin_set_game_active(game_id: UUID, active: bool):
    logger.info("admin_set_game_active")
    AdminInterface().set_game_active(game_id, active)


@admin_method(path="/admin_delete_user", method="POST")
async def admin_delete_user(user_id: UUID):
    """Delete a player outright - the repair for a duplicate user created by
    joining on the wrong phone or browser."""
    logger.info("admin_delete_user %s", user_id)
    AdminInterface().delete_user(user_id)


@admin_method(path="/admin_merge_user", method="POST")
async def admin_merge_user(user_id: UUID, into_user_id: UUID):
    """Fold a stray session into the player it actually belongs to - the
    repair for someone who joined on a second phone or cleared their cookies,
    orphaning the real player behind a fresh, empty ``User``. Everything the
    stray accrued (items, shots, bullets, ...) moves onto the survivor, and
    the stray's session cookie is aliased so every future request it makes is
    served as the survivor."""
    logger.info("admin_merge_user %s into %s", user_id, into_user_id)
    AdminInterface().merge_user(user_id, into_user_id)


@admin_method(path="/admin_set_user_name", method="POST")
async def admin_set_user_name(user_id: UUID, name: str):
    logger.info("admin_set_user_name")
    AdminInterface().set_user_name(user_id=user_id, name=name)


@admin_method(path="/admin_set_team_leader", method="POST")
async def admin_set_team_leader(user_id: UUID, is_team_leader: bool):
    logger.info("admin_set_team_leader - %s", locals())
    AdminInterface().set_team_leader(user_id=user_id, is_team_leader=is_team_leader)


@admin_method(path="/admin_set_courier_location", method="POST")
async def admin_set_courier_location(
    game_id: UUID, lat: float, long: float, accuracy: Optional[float] = None
):
    """Where the courier is now (M4.1). Posted about once a second while
    somebody is walking a crate to a drop; the fan-out to the players is
    throttled server-side.

    Deliberately not logged, unlike every other admin route here: at one call
    a second it would be most of the log for as long as a drop takes.
    """
    AdminInterface().set_courier_location(
        game_id=game_id, lat=lat, long=long, accuracy=accuracy
    )


@admin_method(path="/admin_clear_courier", method="POST")
async def admin_clear_courier(game_id: UUID):
    logger.info("admin_clear_courier - %s", locals())
    AdminInterface().clear_courier(game_id=game_id)


@admin_method(path="/admin_set_circle", method="POST")
async def admin_set_circle(
    game_id: UUID, name: CircleTypes, lat: float, long: float, radius_km: float
):
    logger.info("admin_set_circle - %s", locals())
    AdminInterface().set_circles(
        game_id=game_id, name=name, lat=lat, long=long, radius=radius_km
    )


@admin_method(path="/admin_cue_next_event", method="POST")
async def admin_cue_next_event(
    game_id: UUID,
    kind: NextEventKind,
    minutes: float,
    note: Optional[str] = None,
):
    """Start the countdown the players' phones show. Minutes, not seconds:
    this is typed on a phone in a hurry, and every real cue is a round number
    of them."""
    logger.info("admin_cue_next_event - %s", locals())
    return AdminInterface().cue_next_event(
        game_id=game_id, kind=kind.value, seconds=minutes * 60, note=note
    )


@admin_method(path="/admin_cancel_cue", method="POST")
async def admin_cancel_cue(game_id: UUID):
    logger.info("admin_cancel_cue - %s", locals())
    AdminInterface().cancel_cue(game_id=game_id)


Landmark = Enum("Landmark", {k: k for k in ACTIVE_VENUE.landmarks})


@admin_method(path="/admin_set_circle_by_location", method="POST")
async def admin_set_circle_by_location(
    game_id: UUID,
    name: CircleTypes,
    location: Landmark,  # type: ignore
    radius_km: float,
):
    logger.info("admin_set_circle_by_location - %s", locals())

    location = str(location.value).upper().replace(" ", "_")
    try:
        lat, long = ACTIVE_VENUE.landmarks[location]
    except KeyError:
        raise HTTPException(404, f"Unknown location {location}")

    AdminInterface().set_circles(
        game_id=game_id, name=name, lat=lat, long=long, radius=radius_km
    )


@admin_method(path="/admin_get_landmarks", method="GET")
async def admin_get_landmarks() -> list[str]:
    logger.info("admin_get_landmarks - %s", locals())
    return [k for k in ACTIVE_VENUE.landmarks]


@admin_method(path="/admin_clear_circle", method="POST")
async def admin_set_circle(
    game_id: UUID,
    name: CircleTypes,
):
    logger.info("admin_clear_circle - %s", locals())

    AdminInterface().set_circles(
        game_id=game_id, name=name, lat=None, long=None, radius=None
    )


@admin_method(path="/admin_reset_game", method="POST")
async def admin_reset_game(game_id: UUID, keep_weapons: bool = True):
    logger.info("admin_reset_game - %s", locals())

    AdminInterface().reset_game(game_id=game_id, keep_weapons=keep_weapons)


@admin_method(path="/admin_reset_to_start_state", method="POST")
async def admin_reset_to_start_state(game_id: UUID):
    """The 16:00 button (M2.1): sweep the sandbox away but keep the door's
    work. Refuses unless the game is paused."""
    logger.info("admin_reset_to_start_state - %s", locals())

    AdminInterface().reset_to_start_state(game_id=game_id)


@admin_method("/admin_ticker_messages", method="GET")
async def admin_ticker_messages(game_id: UUID, num_messages: int = 10):
    """Public ticker messages for a game, keyed by game rather than by the
    admin's own player session (the admin's player may not be in the game)."""
    return Ticker(game_id, user_id=None).get_messages(num_messages)


@admin_method(path="/admin_send_custom_ticker_message", method="POST")
async def admin_send_custom_ticker_message(
    game_id: UUID,
    message: str,
):
    logger.info("admin_send_custom_ticker_message - %s", locals())

    send_generic_message(game_id, message)


@admin_method(path="/admin_dump_images", method="POST")
async def admin_dump_images():
    logger.info("admin_dump_images - %s", locals())

    from .postprocess_shot_images import zip_shot_images

    zip_bytes = zip_shot_images()

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="shot_images.zip"'},
    )


######## DEMO GAME ###########
#
# The sample game, provisioned and then fired one shot at a time so a
# dashboard can be watched reacting rather than found already full. Refuses
# outright if anybody in a team is not one of the thirty simulated players -
# see backend/demo_game.py.


@admin_method(path="/admin_start_demo_game", method="POST")
async def admin_start_demo_game() -> dict:
    """Start the drip, or report the run already going. Idempotent."""
    logger.info("admin_start_demo_game")
    try:
        return demo_game.start()
    except demo_game.DemoGameRefused as refusal:
        raise HTTPException(409, str(refusal))


@admin_method(path="/admin_cancel_demo_game", method="POST")
async def admin_cancel_demo_game() -> dict:
    logger.info("admin_cancel_demo_game")
    return demo_game.cancel()


@admin_method("/admin_demo_game_status", method="GET")
async def admin_demo_game_status() -> dict:
    return demo_game.status()


######## IDENTITY (colour code) DEMO ###########
#
# A stateless sandbox for the player-identification scheme: build a scheme,
# decode a hand-typed reading, or simulate many noisy readings. Nothing here
# touches the database or a running game.


@admin_method(path="/admin_identity_defaults", method="GET")
async def admin_identity_defaults() -> dict:
    return identity_demo.demo_defaults()


@admin_method(path="/admin_identity_scheme", method="POST")
async def admin_identity_scheme(
    spec: identity_demo.SchemeSpec, max_rows: int = identity_demo.MAX_CODEBOOK_ROWS
) -> dict:
    with _identity_demo_errors():
        return identity_demo.describe_scheme(spec, max_rows=max_rows)


@admin_method(path="/admin_identity_decode", method="POST")
async def admin_identity_decode(request: identity_demo.DecodeRequest) -> dict:
    with _identity_demo_errors():
        return identity_demo.decode_reading(request)


@admin_method(path="/admin_identity_simulate", method="POST")
async def admin_identity_simulate(request: identity_demo.SimulateRequest) -> dict:
    with _identity_demo_errors():
        return identity_demo.simulate(request)


@contextmanager
def _identity_demo_errors():
    """Turn the demo module's complaints into a readable HTTP 400."""
    try:
        yield
    except identity_demo.DemoError as e:
        raise HTTPException(400, str(e))


######## IDENTITY (colour code) ADMIN INTEGRATION ###########
#
# The first database wiring of backend/identity/: a per-game report of who's
# assigned which slot / override, and the two mutating endpoints the admin
# "Identity overrides" page (react-ui/src/AdminIdentity.js) is coded against.
# See backend/identity_admin.py for the actual logic -- this is deliberately
# thin, matching the identity-demo endpoints just above.


@admin_method(path="/admin_identity_report", method="GET")
async def admin_identity_report(game_id: UUID) -> dict:
    with _identity_admin_errors():
        return identity_admin.build_report(game_id)


@admin_method(path="/admin_join_qr_codes", method="GET")
async def admin_join_qr_codes(game_id: UUID) -> dict:
    """The game's sign-up link and one signed team join QR per team. See
    ``identity_admin.build_join_codes`` for why this GET writes (it pins
    each team's display colour)."""
    with _identity_admin_errors():
        return identity_admin.build_join_codes(game_id)


@admin_method(path="/admin_game_join_url", method="GET")
async def admin_game_join_url(game_id: UUID) -> dict:
    """The game's sign-up link on its own - the link and QR that go out over
    WhatsApp. Unlike ``/admin_join_qr_codes`` this needs no teams and writes
    nothing."""
    with _identity_admin_errors():
        return identity_admin.game_join_url(game_id)


@admin_method(path="/admin_map_poster_pdf", method="GET")
async def admin_map_poster_pdf(size: str = map_poster.DEFAULT_PAGE_SIZE):
    """The map poster (backend/map_poster.py): the active venue's map on one
    sheet, with a numbered legend of the pubs. A GET, unlike the two
    code-minting printables below: it draws what `venues.py` already says and
    mints, records and signs nothing."""
    try:
        pdf = map_poster.render_pdf(size=size.upper())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _pdf_response(pdf, f"map_poster_{size.lower()}.pdf")


@admin_method(path="/admin_team_cards_pdf", method="GET")
async def admin_team_cards_pdf(game_id: UUID):
    """The printable team cards (backend/team_cards.py): one A4 page per
    team, each carrying that team's door code. Built here rather than by a
    CLI because the team ids the codes carry only exist in the running
    server's database."""
    with _identity_admin_errors():
        codes = identity_admin.build_join_codes(game_id)
    pdf = team_cards.render_pdf(
        [(team["team_name"], team["encoded_url"]) for team in codes["teams"]]
    )
    return _pdf_response(pdf, "team_cards.pdf")


# The other two printables (backend/printables.py). POST rather than GET
# because each call *mints fresh codes* and records them: a link a browser is
# free to prefetch would put phantom batches in qr_codes.csv and hand the
# admin a sheet that is not the one the log describes. The team cards above
# re-render the codes a game already has, so they stay a plain download link.


@admin_method(path="/admin_item_sheets_pdf", method="POST")
async def admin_item_sheets_pdf(
    itype: str,
    num: int,
    sheets: int = 1,
    damage: int = 1,
    timeout: float = DEFAULT_SHOT_TIMEOUT,
    collected_only_once: bool = True,
    collected_as_team: bool = False,
    tag: str = "",
    batch: Optional[str] = generate_qr_items.DEFAULT_BATCH,
    unlimited: bool = False,
    minutes: Optional[int] = None,
):
    """The drop cards: sheets of eight item codes, to be cut up and hidden."""
    logger.info("admin_item_sheets_pdf - %s", locals())

    try:
        pdf = printables.item_sheets_pdf(
            itype,
            num,
            sheets=sheets,
            damage=damage,
            timeout=timeout,
            collected_only_once=collected_only_once,
            collected_as_team=collected_as_team,
            tag=tag,
            batch=batch,
            unlimited=unlimited,
            minutes=minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _pdf_response(pdf, f"item_cards_{itype}.pdf")


@admin_method(path="/admin_pub_pages_pdf", method="POST")
async def admin_pub_pages_pdf(
    count: int,
    num_bullets: int = generate_pub_pages.BULLETS_PER_TEAM_MEMBER,
    tag: str = "pub",
    batch: Optional[str] = generate_qr_items.DEFAULT_BATCH,
):
    """The pub certificates: one A4 poster per pub, each a team-wide ammo
    code the first team to scan it collects for everybody."""
    logger.info("admin_pub_pages_pdf - %s", locals())

    try:
        pdf = printables.pub_pages_pdf(
            count, num_bullets=num_bullets, tag=tag, batch=batch
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _pdf_response(pdf, "pub_pages.pdf")


@admin_method(path="/admin_sandbox_sheets_pdf", method="POST")
async def admin_sandbox_sheets_pdf(copies: int = 1):
    """The sandbox posters: one sheet of eight for every kind of card the
    warm-up room carries, every code unlimited so the same player can scan it
    again and again, and every one in the "sandbox" batch so the whole room is
    withdrawn in a single press at 16:00."""
    logger.info("admin_sandbox_sheets_pdf - %s", locals())

    try:
        pdf = printables.sandbox_sheets_pdf(copies)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _pdf_response(pdf, "sandbox_sheets.pdf")


# Withdrawing a batch (M2.2). The only recall a printed code has: a card
# cannot be un-printed, and rotating SECRET_KEY would take the team cards with
# it. POST for the two that change something, GET for the list.


@admin_method(path="/admin_withdraw_batch", method="POST")
async def admin_withdraw_batch(batch: str) -> List[dict]:
    """Stop every code minted into ``batch`` from being collectable - what
    turns the sandbox's posters off at 16:00. Returns the batches now
    withdrawn, so the page never has to ask twice."""
    logger.info("admin_withdraw_batch %s", batch)
    return AdminInterface().withdraw_batch(batch)


@admin_method(path="/admin_restore_batch", method="POST")
async def admin_restore_batch(batch: str) -> List[dict]:
    """Let a withdrawn batch be collected again."""
    logger.info("admin_restore_batch %s", batch)
    return AdminInterface().restore_batch(batch)


@admin_method(path="/admin_revoked_batches", method="GET")
async def admin_revoked_batches() -> List[dict]:
    """Every batch currently withdrawn, most recent first."""
    return AdminInterface().get_revoked_batches()


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_method(path="/admin_identity_set", method="POST")
async def admin_identity_set(request: identity_admin.IdentitySetRequest) -> dict:
    with _identity_admin_errors():
        return identity_admin.set_identity(request)


@admin_method(path="/admin_clear_identity", method="POST")
async def admin_clear_identity(request: identity_admin.IdentityClearRequest) -> dict:
    with _identity_admin_errors():
        return identity_admin.clear_identity(request.user_id)


@admin_method(path="/admin_identity_suggest", method="POST")
async def admin_identity_suggest(
    request: identity_admin.IdentitySuggestRequest,
) -> dict:
    with _identity_admin_errors():
        return identity_admin.suggest_identity(request)


@contextmanager
def _identity_admin_errors():
    """Turn identity_admin's complaints into a readable HTTP error.

    ``OutfitUnavailableError`` (a ``pick_outfit`` claim that failed
    re-validation - someone just took it, or it stopped qualifying) maps to
    409, distinguishable from the plain 400 a malformed request gets; check
    it first since it subclasses ``IdentityAdminError``.
    """
    try:
        yield
    except identity_admin.OutfitUnavailableError as e:
        raise HTTPException(409, str(e))
    except identity_admin.IdentityAdminError as e:
        raise HTTPException(400, str(e))


@router.get("/sse_updates")
async def sse_updates(
    user_id=Depends(get_user_id),
):
    return StreamingResponse(
        sse_event_streams.updates_generator(user_id),
        headers={
            "Content-type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@admin_method("/sse_admin_updates", method="GET")
async def sse_admin_updates():
    return StreamingResponse(
        sse_event_streams.admin_updates_generator(),
        headers={
            "Content-type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.on_event("startup")
def _make_debug_entries() -> None:
    """Build the sample game, once the app is actually assembled.

    Not done during ``database.load()``: the sample game is built through
    AdminInterface, and load() runs while that module's own import is still
    in flight. See backend/reset_db.py.
    """
    from .reset_db import make_debug_entries_if_wanted

    make_debug_entries_if_wanted()


@app.on_event("startup")
async def _rearm_event_cues() -> None:
    """Rebuild the countdown timers from the database.

    The timers are in-process asyncio tasks and die with the process; the
    deadlines are columns and do not. Without this, deploying in the middle of
    a ten-minute countdown would leave thirty phones counting down to a circle
    that never closed - and the admin with no sign that anything was wrong.
    See backend/next_event.py.
    """
    from . import next_event

    found = next_event.sweep()
    if found:
        logger.info("Re-armed %d event cue(s) at startup", found)


app.include_router(router, prefix="/api")
