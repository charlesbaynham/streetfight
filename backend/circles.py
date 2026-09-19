"""The game circles: the plan they are placed from, and their SSE updates."""

import asyncio
import logging
import os
from typing import List
from typing import NamedTuple
from typing import Optional
from typing import Tuple

from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event
from .venues import ACTIVE_VENUE

logger = logging.getLogger(__name__)


# The night's circles, in the order they close. Charles and Gaby chose them on
# a marked-up map; only the *names* are here, because this repository is
# public - both halves of an entry are supplied by the environment, the
# coordinates as a landmark (`LANDMARK_CIRCLE0=...`, see
# `venues.landmarks_from_env`) and the radius beside it
# (`CIRCLE_RADIUS_CIRCLE0=0.70`). How big the last circle is gives away as
# much about the night as where it is.
#
# This list is what stops the one mistake that would neuter the early-warning
# card: cueing a countdown having forgotten to place NEXT. The game holds a
# pointer into it (`Game.circle_plan_index`) and arms the next entry by
# itself - at a reset to the start state, when the game starts, and the moment
# a circle closes - so there is always a private circle for a card to reveal
# and the admin only ever presses the countdown.
CIRCLE_PLAN: Tuple[str, ...] = ("CIRCLE0", "CIRCLE1", "CIRCLE2", "CIRCLE3")

# The radius of a planned circle, in km: `CIRCLE_RADIUS_CIRCLE0="0.70"`.
CIRCLE_RADIUS_ENV_PREFIX = "CIRCLE_RADIUS_"


def radius_from_env(name: str) -> Optional[float]:
    """The radius the environment gives circle `name`, in km, or None.

    Malformed is the same as missing, and logged rather than raised, for the
    reason `venues.landmarks_from_env` gives: a typo in a secrets file must
    not be why the server will not boot mid-game. An entry without a radius is
    one the admin places by hand, exactly as one without coordinates is.
    """
    key = CIRCLE_RADIUS_ENV_PREFIX + name
    value = os.environ.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        logger.warning("Ignoring %s: expected a radius in km, got %r", key, value)
        return None


class PlannedCircle(NamedTuple):
    """One entry of `CIRCLE_PLAN`, resolved against the active venue."""

    index: int
    name: str
    radius_km: Optional[float] = None
    lat: Optional[float] = None
    long: Optional[float] = None

    @property
    def known(self) -> bool:
        """Has the environment actually supplied this circle - both where it
        closes and how big it is? An entry missing either half is a circle the
        admin has to place by hand, not a reason to refuse to run."""
        return (
            self.lat is not None
            and self.long is not None
            and self.radius_km is not None
        )


def planned_circle(index: int) -> Optional[PlannedCircle]:
    """The `index`th circle of the plan, or None once the plan runs out."""
    if index < 0 or index >= len(CIRCLE_PLAN):
        return None

    name = CIRCLE_PLAN[index]
    radius_km = radius_from_env(name)
    lat_long = ACTIVE_VENUE.landmarks.get(name)

    if lat_long is None:
        return PlannedCircle(index=index, name=name, radius_km=radius_km)

    return PlannedCircle(
        index=index,
        name=name,
        radius_km=radius_km,
        lat=lat_long[0],
        long=lat_long[1],
    )


def circle_plan() -> List[PlannedCircle]:
    """The whole plan, for the admin page to say what is coming and which
    entries the environment has not supplied."""
    return [planned_circle(index) for index in range(len(CIRCLE_PLAN))]


def trigger_circle_update(game_id):
    """
    Trigger an update event for the circles in this game
    """
    logger.debug("Triggering circle update for game %s", game_id)
    trigger_update_event("circle", game_id)


async def generate_circle_updates(game_id, timeout=None):
    """
    A generator that yields None every time an update is available for the
    circles in this game, or at most after timeout seconds

    Does not block the database session.
    """
    while True:
        # Lookup / make an event for this game and subscribe to it
        event = get_trigger_event("circle", game_id)

        try:
            logger.debug(
                "(Circle %s) Subscribing to event %s",
                game_id,
                event,
            )
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.debug("(Circle %s) Event received", game_id)
            yield
        except asyncio.TimeoutError:
            logger.debug("(Circle %s) Event timeout", game_id)
            yield
