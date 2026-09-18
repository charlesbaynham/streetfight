"""The game circles: the plan they are placed from, and their SSE updates."""

import asyncio
import logging
from typing import List
from typing import NamedTuple
from typing import Optional
from typing import Tuple

from .asyncio_triggers import get_trigger_event
from .asyncio_triggers import trigger_update_event
from .venues import ACTIVE_VENUE

logger = logging.getLogger(__name__)


# The night's circles, in the order they close, with the radius each is placed
# at. Charles and Gaby chose them on a marked-up map; the *names* are here and
# the coordinates are not, because this repository is public - each one is a
# landmark supplied by the environment (see `venues.landmarks_from_env`).
#
# This list is what stops the one mistake that would neuter the early-warning
# card: cueing a countdown having forgotten to place NEXT. The game holds a
# pointer into it (`Game.circle_plan_index`) and arms the next entry by
# itself - at a reset to the start state, when the game starts, and the moment
# a circle closes - so there is always a private circle for a card to reveal
# and the admin only ever presses the countdown.
CIRCLE_PLAN: Tuple[Tuple[str, float], ...] = (
    ("CIRCLE0", 0.70),
    ("CIRCLE1", 0.42),
    ("CIRCLE2", 0.18),
    ("CIRCLE3", 0.05),
)


class PlannedCircle(NamedTuple):
    """One entry of `CIRCLE_PLAN`, resolved against the active venue."""

    index: int
    name: str
    radius_km: float
    lat: Optional[float] = None
    long: Optional[float] = None

    @property
    def known(self) -> bool:
        """Has this circle's landmark actually been supplied? A plan entry
        whose `LANDMARK_<name>` is unset is a circle the admin has to place by
        hand, not a reason to refuse to run."""
        return self.lat is not None and self.long is not None


def planned_circle(index: int) -> Optional[PlannedCircle]:
    """The `index`th circle of the plan, or None once the plan runs out."""
    if index < 0 or index >= len(CIRCLE_PLAN):
        return None

    name, radius_km = CIRCLE_PLAN[index]
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
    entries it has no coordinates for."""
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
