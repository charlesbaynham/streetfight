"""Where everybody actually is, second by second: the truth track.

This is the ground truth, and it never reaches the database. It exists to
find encounters and to compose photographs; what the game gets to see is the
error-laden sample of it in ``telemetry.py``. Keeping the two apart is the
whole point of the exercise, so they live in separate modules and the world
file keeps them in separate keys.

Motion is ballistic rather than diffusive, because people walk rather than
jiggle: each member holds a heading that turns slowly, at a speed drawn once
per player, with a restoring pull toward their team's centroid that keeps the
group together. A pure random walk with the same step size would take hours
to cross a 55 m cloud, which is not how a group of five in a pub garden
behaves.
"""

import hashlib
from typing import Dict
from typing import List

import numpy as np

from backend.test_world import geo
from backend.test_world import spec


def _stream_seed(seed: int, *parts: str) -> int:
    """A stable per-stream seed.

    Python's ``hash()`` of a string is salted per process, so it cannot be
    used here: the world would differ between runs of the same seed. A digest
    is stable across processes and interpreter versions, which is what
    byte-identical output requires.
    """
    key = ":".join((str(seed),) + parts).encode()
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big")


def _centroid_route(team_name: str, rng: np.random.Generator) -> np.ndarray:
    """A team centroid's path over the hour, as (N_TICKS, 2) metres.

    Starts at the team's pub and walks to further landmarks, pausing at each.
    The pauses matter as much as the walking: a team that never stops never
    produces the sustained encounters a photograph needs.
    """
    from backend.venues import ACTIVE_VENUE

    start = np.array(geo.landmark_m(spec.TEAM_START_LANDMARKS[team_name]))

    # Candidate waypoints: every pub-ish landmark, so routes stay on the parts
    # of the map players actually walk between.
    names = [n for n in ACTIVE_VENUE.landmarks if not n.startswith(("CIRCLE", "DROP_"))]
    points = np.array([geo.landmark_m(n) for n in names])

    path = np.zeros((spec.N_TICKS, 2))
    pos = start.copy()
    tick = 0
    while tick < spec.N_TICKS:
        pause = int(rng.integers(*spec.WAYPOINT_PAUSE_S))
        stop = min(tick + pause, spec.N_TICKS)
        path[tick:stop] = pos
        tick = stop
        if tick >= spec.N_TICKS:
            break

        # Prefer a nearby waypoint: a team crossing the whole map mid-game is
        # not what an evening in a few streets looks like.
        distances = np.hypot(*(points - pos).T)
        weights = np.exp(-distances / 250.0)
        weights[distances < 1.0] = 0.0
        target = points[rng.choice(len(points), p=weights / weights.sum())]

        speed = rng.uniform(*spec.CENTROID_SPEED_MS)
        leg = np.hypot(*(target - pos))
        steps = max(int(leg / speed), 1)
        steps = min(steps, spec.N_TICKS - tick)
        for i in range(steps):
            path[tick + i] = pos + (target - pos) * ((i + 1) / max(steps, 1))
        pos = path[tick + steps - 1].copy()
        tick += steps

    return path


def _member_offsets(n_members: int, rng: np.random.Generator) -> np.ndarray:
    """Each member's offset from their centroid over time, (N_TICKS, n, 2).

    Drawn from an isotropic Gaussian of ``TEAM_SPREAD_SIGMA_M`` per axis and
    then integrated forward, with the truncation applied throughout rather
    than only at the start.
    """
    sigma = spec.TEAM_SPREAD_SIGMA_M
    limit = sigma * spec.TEAM_SPREAD_TRUNCATE_SIGMA

    offsets = np.zeros((spec.N_TICKS, n_members, 2))
    pos = rng.normal(0.0, sigma, size=(n_members, 2))
    pos = _truncate(pos, limit)

    speeds = rng.uniform(*spec.WALK_SPEED_MS, size=n_members)
    heading = rng.uniform(0.0, 2 * np.pi, size=n_members)

    for t in range(spec.N_TICKS):
        offsets[t] = pos
        # A slowly turning heading: people walk in a direction for a while.
        heading = heading + rng.normal(0.0, 0.09, size=n_members)
        step = np.stack([np.sin(heading), np.cos(heading)], axis=1) * speeds[:, None]
        pos = pos + step - spec.CENTROID_RESTORE_PER_S * pos
        pos = _truncate(pos, limit)

    return offsets


def _truncate(pos: np.ndarray, limit: float) -> np.ndarray:
    """Pull anything beyond the truncation radius back onto it."""
    radius = np.hypot(pos[:, 0], pos[:, 1])
    over = radius > limit
    if np.any(over):
        pos = pos.copy()
        pos[over] *= (limit / radius[over])[:, None]
    return pos


def truth_track(seed: int, cast: List[dict]) -> Dict[str, np.ndarray]:
    """The whole world's motion.

    Returns ``{"positions": (N_TICKS, N_PLAYERS, 2) metres,
    "centroids": {team: (N_TICKS, 2)}}`` with players in ``cast`` order.
    """
    positions = np.zeros((spec.N_TICKS, spec.N_PLAYERS, 2))
    centroids: Dict[str, np.ndarray] = {}

    for team_index, team_name in enumerate(spec.TEAM_NAMES):
        rng = np.random.default_rng(_stream_seed(seed, "team", team_name))
        centroid = _centroid_route(team_name, rng)
        centroids[team_name] = centroid

        members = [i for i, p in enumerate(cast) if p["team"] == team_name]
        offsets = _member_offsets(len(members), rng)
        for slot, player_index in enumerate(members):
            positions[:, player_index, :] = centroid + offsets[:, slot, :]

    return {"positions": positions, "centroids": centroids}
