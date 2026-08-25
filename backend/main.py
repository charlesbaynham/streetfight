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
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.responses import StreamingResponse

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
from . import image_processing
from . import shot_auto_actions
from . import shot_vision
from . import sse_event_streams
from .admin_auth import is_admin_authed
from .admin_auth import mark_admin_authed
from .admin_auth import require_admin_auth

# Import these after logging is setup since they might have side effects (e.g. database setup)
from .admin_interface import AdminInterface
from .asyncio_triggers import trigger_update_event
from .model import GameModel
from .model import ShotModel
from .ticker import Ticker
from .user_id import get_user_id
from .user_interface import UserInterface
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


class _Shot(BaseModel):
    photo: str


@router.post("/submit_shot")
async def submit_shot(
    shot: _Shot,
    user_id=Depends(get_user_id),
):
    logger.info("Received shot from user %s", user_id)

    with UserInterface(user_id) as ui:
        shot_id = ui.submit_shot(shot.photo)
        game_id = ui.get_user().team.game_id

    # Outside the session: queueing the review must not slow down the player
    # who fired, and the review itself must not hold a database session while
    # it waits on the network.
    trigger_update_event("shots", game_id)
    if AdminInterface().is_ai_shot_review_enabled(game_id):
        ai_shot_review.enqueue_review(shot_id)

    return shot_id


@router.get("/user_shots")
async def get_user_shots(
    user_id=Depends(get_user_id),
):
    """This user's own shots, newest first, without the images"""
    with UserInterface(user_id) as ui:
        return ui.get_own_shots()


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


@router.post("/join_game")
async def join_game(
    encoded_code: _EncodedJoinCode,
    user_id=Depends(get_user_id),
):
    """Join a team and claim an identity slot by scanning a signed join code.

    The body is ``{"data": <url-or-b64>}``, same shape as collect_item.
    """
    try:
        code = JoinCodeModel.from_base64(encoded_code.data)
    except ValueError:
        raise HTTPException(400, "Malformed data")

    code_validation_error = code.validate_signature()
    if code_validation_error:
        raise HTTPException(
            403, f"The scanned join code is invalid - error {code_validation_error}"
        )

    logger.info(
        "User %s joining team %s with slot %s", user_id, code.team_id, code.slot
    )

    with _identity_admin_errors():
        return identity_admin.claim_join_slot(user_id, code)


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
    user_id=Depends(get_user_id),
):
    logger.info("Setting location for user %s to %f, %f", user_id, latitude, longitude)
    with UserInterface(user_id) as ui:
        ui.set_location(latitude, longitude)


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
    also drains an already-reviewed confident head that was waiting for it.
    """
    AdminInterface().set_ai_auto_actions_enabled(game_id, enabled)
    if enabled:
        shot_auto_actions.process_queue_head(game_id)
    return {"enabled": enabled}


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


class _ReplayRequest(BaseModel):
    shot_id: UUID
    prompt: Optional[str] = None
    always_zoom: bool = True


@admin_method(path="/admin_replay_shot_review", method="POST")
async def admin_replay_shot_review(request: _ReplayRequest) -> dict:
    """Fire one shot through the vision pipeline and return the reading.

    The admin replay workbench: same pipeline as a real review (aim marker,
    resize, mandatory zoom), but with the prompt customisable on the fly and
    nothing stored -- no state changes, no events, no auto-actions.
    """
    client = get_vision_client()
    if client is None:
        raise HTTPException(503, "No vision model configured - set OPENROUTER_API_KEY")
    try:
        return await ai_shot_review.replay_shot_review(
            request.shot_id,
            client,
            prompt=request.prompt or None,
            always_zoom=request.always_zoom,
        )
    except Exception as e:
        raise HTTPException(502, f"Replay failed: {e}")


@admin_method("/admin_get_shot_vision_images", method="GET")
async def admin_get_shot_vision_images(shot_id: UUID) -> dict:
    """Return the shot image formatted exactly as the vision model sees it.

    Two images are returned:
    - full: the whole frame with aim marker, downscaled to 1024px max (what
      prepare_for_vision produces)
    - zoomed: the centre 25% of the original, cropped and upscaled to 1024px
      with a fresh aim marker (what zoom_image produces)

    Both are JPEG data URLs ready to render in <img>.
    """
    from .admin_interface import AdminInterface

    shot_model = AdminInterface().get_shot_model(shot_id=shot_id)
    original = shot_model.image_base64

    # Full frame: aim marker + downscale to 1024px max
    full = image_processing.prepare_for_vision(
        image_processing.draw_aim_marker(original)
    )

    # Zoomed frame: centre 25% crop from ORIGINAL, upscale to 1024px, aim marker
    zoomed = image_processing.zoom_image(original, factor=shot_vision.ZOOM_FACTOR)

    return {"full": full, "zoomed": zoomed}


@admin_method("/admin_get_default_vision_prompt", method="GET")
async def admin_get_default_vision_prompt() -> dict:
    """The prompt the live pipeline currently uses, to seed the workbench's."""
    return {"prompt": shot_vision.build_prompt()}


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
):
    logger.info("admin_make_new_item")
    try:
        encoded_url = AdminInterface().make_new_item(
            item_type,
            item_data,
            collected_only_once=collected_only_once,
            collected_as_team=collected_as_team,
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


@admin_method(path="/admin_set_user_name", method="POST")
async def admin_set_user_name(user_id: UUID, name: str):
    logger.info("admin_set_user_name")
    AdminInterface().set_user_name(user_id=user_id, name=name)


@admin_method(path="/admin_set_circle", method="POST")
async def admin_set_circle(
    game_id: UUID, name: CircleTypes, lat: float, long: float, radius_km: float
):
    logger.info("admin_set_circle - %s", locals())
    AdminInterface().set_circles(
        game_id=game_id, name=name, lat=lat, long=long, radius=radius_km
    )


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
async def admin_join_qr_codes(game_id: UUID, slots_per_team: int = 8) -> dict:
    """Signed join QR URLs for every team in a game: scanning one joins that
    team and claims that identity slot. Deterministic, so reprints match."""
    with _identity_admin_errors():
        return identity_admin.build_join_codes(game_id, slots_per_team)


@admin_method(path="/admin_identity_set", method="POST")
async def admin_identity_set(request: identity_admin.IdentitySetRequest) -> dict:
    with _identity_admin_errors():
        return identity_admin.set_identity(request)


@admin_method(path="/admin_identity_suggest", method="POST")
async def admin_identity_suggest(
    request: identity_admin.IdentitySuggestRequest,
) -> dict:
    with _identity_admin_errors():
        return identity_admin.suggest_identity(request)


@contextmanager
def _identity_admin_errors():
    """Turn identity_admin's complaints into a readable HTTP 400."""
    try:
        yield
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


app.include_router(router, prefix="/api")
