"""Every cross-team meeting in the simulated hour: the candidate pool.

Photographs are *found* here rather than invented and then given coordinates.
That is what makes a scene's telemetry and its picture agree by construction:
the separation in the prompt is the separation on the truth track, the light
is the light at that moment of the world clock, and the staleness of the
target's fix is whatever their phone actually did.

A sweep of a six-team world yields hundreds of these. The selector in the next
phase picks ten; if it cannot satisfy its required distribution from what is
here, it says so and fails rather than fabricating an encounter.
"""

import datetime
from typing import Dict
from typing import List

import numpy as np

from backend.test_world import geo
from backend.test_world import locales
from backend.test_world import spec

_CHUNK = 600  # ticks per vectorised block


def _cross_team_pairs(cast: List[dict]):
    """Index pairs (i, j), i < j, whose players are on different teams."""
    pairs = [
        (i, j)
        for i in range(len(cast))
        for j in range(i + 1, len(cast))
        if cast[i]["team"] != cast[j]["team"]
    ]
    return np.array(pairs, dtype=int)


def _runs(mask: np.ndarray) -> List[tuple]:
    """Contiguous True stretches in a 1-D boolean, merging short gaps."""
    (ticks,) = np.nonzero(mask)
    if ticks.size == 0:
        return []
    splits = np.nonzero(np.diff(ticks) > spec.ENCOUNTER_GAP_S)[0]
    groups = np.split(ticks, splits + 1)
    return [
        (int(g[0]), int(g[-1]))
        for g in groups
        if g[-1] - g[0] >= spec.ENCOUNTER_MIN_DURATION_S
    ]


def sweep(cast: List[dict], positions: np.ndarray) -> List[dict]:
    """All encounter events in the world, newest information first computed.

    Each event is the *whole* stretch two players spent within
    ``ENCOUNTER_RADIUS_M`` of each other, summarised at its moment of closest
    approach -- which is the moment somebody would actually take the
    photograph.
    """
    pairs = _cross_team_pairs(cast)
    n_ticks = positions.shape[0]

    # Distance between every cross-team pair at every tick, in blocks so the
    # intermediate never has to be held whole.
    distances = np.empty((n_ticks, len(pairs)), dtype=np.float32)
    for start in range(0, n_ticks, _CHUNK):
        stop = min(start + _CHUNK, n_ticks)
        delta = (
            positions[start:stop, pairs[:, 0], :]
            - positions[start:stop, pairs[:, 1], :]
        )
        distances[start:stop] = np.hypot(delta[..., 0], delta[..., 1])

    within = distances <= spec.ENCOUNTER_RADIUS_M

    events: List[dict] = []
    for pair_index, (i, j) in enumerate(pairs):
        for first, last in _runs(within[:, pair_index]):
            window = distances[first : last + 1, pair_index]
            closest = int(first + np.argmin(window))
            events.append(
                _describe(cast, positions, int(i), int(j), first, last, closest)
            )

    events.sort(key=lambda e: (e["tick"], e["a"], e["b"]))
    for n, event in enumerate(events):
        event["id"] = f"E{n:04d}"
    return events


def _describe(cast, positions, i, j, first, last, closest) -> dict:
    a_east, a_north = positions[closest, i]
    b_east, b_north = positions[closest, j]
    separation = float(np.hypot(b_east - a_east, b_north - a_north))

    mid_east = float((a_east + b_east) / 2)
    mid_north = float((a_north + b_north) / 2)
    locale = locales.nearest(mid_east, mid_north)

    t_local = spec.START_LOCAL + datetime.timedelta(seconds=closest)

    # Anyone else close enough to be in the picture. They have to be rendered
    # whether we want them or not, so the scene description needs to know.
    others = []
    for k, person in enumerate(cast):
        if k in (i, j):
            continue
        d = float(
            np.hypot(
                positions[closest, k, 0] - mid_east,
                positions[closest, k, 1] - mid_north,
            )
        )
        if d <= spec.IN_FRAME_RADIUS_M:
            others.append(
                {
                    "slug": person["slug"],
                    "team": person["team"],
                    "distance_m": round(d, 1),
                }
            )
    others.sort(key=lambda o: o["distance_m"])

    lat, long = geo.to_latlong(mid_east, mid_north)

    return {
        "a": cast[i]["slug"],
        "b": cast[j]["slug"],
        "a_team": cast[i]["team"],
        "b_team": cast[j]["team"],
        "tick": closest,
        "first_tick": first,
        "last_tick": last,
        "duration_s": int(last - first),
        "time_local": t_local.strftime("%H:%M:%S"),
        "light": spec.light_band(t_local),
        "separation_m": round(separation, 1),
        # Bearing from a to b: what the shooter's compass would read if a
        # photographed b. Shot.heading gets this plus a compass error class,
        # chosen per scenario in the next phase.
        "bearing_a_to_b": round(
            float(geo.bearing_deg(a_east, a_north, b_east, b_north)), 1
        ),
        "lat": round(float(lat), 7),
        "long": round(float(long), 7),
        "locale": locale.name,
        "locale_kind": locale.kind,
        "others_in_frame": others,
    }


def summarise(events: List[dict]) -> Dict:
    """Counts by the axes the selector has to satisfy, for the gate."""
    from collections import Counter

    def band(separation):
        if separation <= 5:
            return "close 3-5m"
        if separation <= 15:
            return "mid 8-15m"
        if separation <= 35:
            return "distant 25-35m"
        return "over 35m"

    return {
        "total": len(events),
        "by_light": dict(Counter(e["light"] for e in events)),
        "by_locale_kind": dict(Counter(e["locale_kind"] for e in events)),
        "by_distance_band": dict(Counter(band(e["separation_m"]) for e in events)),
        "with_bystanders": sum(1 for e in events if e["others_in_frame"]),
        "team_pairs": dict(
            Counter(" / ".join(sorted((e["a_team"], e["b_team"]))) for e in events)
        ),
    }
