"""Find ten encounters in the world that genuinely have what each scene needs.

Nothing here invents an encounter. A scenario states the properties its
photograph must be a picture of -- the locale, the light, the separation, the
target's phone class, and for two of them a specific fact about the target's
newest fix -- and this module searches the pool for encounters that already
have them. If the pool cannot satisfy the ten, it says which scenario ran out
of candidates and stops. Fabricating the missing one would produce a fixture
whose telemetry and photograph disagree, which is the one thing this design
exists to prevent.

Search is exhaustive with backtracking rather than greedy. Greedy assignment
can consume the only encounter a later, more constrained scenario could have
used and then report an impossibility that is not real -- and "the world
cannot do this" is a claim that has to be true when it is made.
"""

import math
from typing import Dict
from typing import List
from typing import Optional

import numpy as np

from backend.test_world import geo
from backend.test_world import scenarios as scen
from backend.test_world import spec
from backend.test_world import telemetry as telemetry_mod


class SelectionFailed(RuntimeError):
    """The pool could not satisfy the ten. Carries the shortfall."""


def _phone_of(cast: List[dict], slug: str) -> str:
    return next(p["phone_class"] for p in cast if p["slug"] == slug)


def _team_of(cast: List[dict], slug: str) -> str:
    return next(p["team"] for p in cast if p["slug"] == slug)


def _fix_facts(fixes, positions, cast, slug, tick):
    """(age_s, distance_m) of the target's newest fix at the moment of a shot.

    ``None`` when the phone has never reported, which is itself a legitimate
    world state but cannot satisfy a scenario that constrains the fix.
    """
    fix = telemetry_mod.newest_fix_at(fixes[slug], tick)
    if fix is None:
        return None
    index = next(i for i, p in enumerate(cast) if p["slug"] == slug)
    east, north = geo.to_m(fix["lat"], fix["long"])
    true_east, true_north = positions[tick, index]
    return (
        tick - fix["t"],
        float(np.hypot(float(east) - true_east, float(north) - true_north)),
    )


def _fix_quality_ok(requirement, facts) -> bool:
    """Does a (age, error) reading meet a "fresh" / "poor" requirement?"""
    if requirement is None:
        return True
    if facts is None:
        # Never reported at all. That is poor by any reading, and certainly
        # not fresh.
        return requirement == "poor"
    age, error = facts
    if requirement == "fresh":
        return age <= scen.FIX_FRESH[0] and error <= scen.FIX_FRESH[1]
    return age >= scen.FIX_POOR[0] or error >= scen.FIX_POOR[1]


def _extra_kitted_at(cast, positions, tick, target, shooter) -> List[dict]:
    """Kitted players other than the pair who are in frame at ``tick``."""
    from backend.test_world import spec as _spec

    index_of = {p["slug"]: i for i, p in enumerate(cast)}
    ti, si = index_of[target], index_of[shooter]
    mid_east = (positions[tick, ti, 0] + positions[tick, si, 0]) / 2
    mid_north = (positions[tick, ti, 1] + positions[tick, si, 1]) / 2
    target_team = _team_of(cast, target)

    out = []
    for k, person in enumerate(cast):
        if person["slug"] in (target, shooter):
            continue
        distance = float(
            math.hypot(
                positions[tick, k, 0] - mid_east, positions[tick, k, 1] - mid_north
            )
        )
        if distance <= _spec.IN_FRAME_RADIUS_M and person["team"] != target_team:
            out.append({"slug": person["slug"], "team": person["team"],
                        "distance_m": round(distance, 1)})
    out.sort(key=lambda o: o["distance_m"])
    return out


def _candidates(scenario, world, positions) -> List[dict]:
    """Every (encounter, tick, target) that could serve this scenario.

    The photograph is taken at a moment *during* an encounter, not necessarily
    at its closest approach -- a pair closing from forty metres to three passes
    through every distance band on the way. So this searches the ticks inside
    each event rather than only its summary, which is both far more permissive
    and a truer account of when somebody actually presses the shutter.
    """
    import datetime

    cast = world["cast"]
    fixes = world["fixes"]
    index_of = {p["slug"]: i for i, p in enumerate(cast)}
    low, high = scen.DISTANCE_BANDS[scenario.distance]

    out = []
    for event in world["encounters"]:
        if event["locale_kind"] != scenario.locale_kind:
            continue

        ia, ib = index_of[event["a"]], index_of[event["b"]]
        for tick in range(event["first_tick"], event["last_tick"] + 1):
            delta = positions[tick, ia] - positions[tick, ib]
            separation = float(math.hypot(delta[0], delta[1]))
            if not (low <= separation <= high):
                continue
            t_local = spec.START_LOCAL + datetime.timedelta(seconds=int(tick))
            if spec.light_band(t_local) != scenario.light:
                continue

            for target, shooter in ((event["a"], event["b"]), (event["b"], event["a"])):
                if scenario.target_phone and _phone_of(cast, target) != scenario.target_phone:
                    continue
                if not _fix_quality_ok(
                    scenario.target_fix, _fix_facts(fixes, positions, cast, target, tick)
                ):
                    continue
                if not _fix_quality_ok(
                    scenario.shooter_fix, _fix_facts(fixes, positions, cast, shooter, tick)
                ):
                    continue

                if scenario.needs_extra_kitted:
                    # A second kitted player who is *in the picture*. The
                    # shooter is behind the camera, so their team is a
                    # perfectly good source of a distractor -- the question
                    # this scene asks is which of two visible candidates gets
                    # named, and they only have to be on different teams from
                    # each other.
                    #
                    # Computed at *this* tick, not read off the event summary:
                    # that list is who was in frame at the moment of closest
                    # approach, which is a different instant from the one this
                    # photograph is taken at, and using it silently answers
                    # the wrong question.
                    if not _extra_kitted_at(cast, positions, tick, target, shooter):
                        continue

                if scenario.target_fix_age_s or scenario.target_fix_distance_m:
                    facts = _fix_facts(fixes, positions, cast, target, tick)
                    if facts is None:
                        continue
                    age, distance = facts
                    if scenario.target_fix_age_s:
                        lo, hi = scenario.target_fix_age_s
                        if not (lo <= age <= hi):
                            continue
                    if scenario.target_fix_distance_m:
                        lo, hi = scenario.target_fix_distance_m
                        if not (lo <= distance <= hi):
                            continue

                out.append({
                    "event": event,
                    "tick": int(tick),
                    "separation_m": round(separation, 1),
                    "target": target,
                    "shooter": shooter,
                })

    # Prefer the middle of the distance band and a longer encounter: both make
    # a more photographable moment, and both are deterministic.
    mid = (low + high) / 2
    out.sort(
        key=lambda c: (
            abs(c["separation_m"] - mid),
            -c["event"]["duration_s"],
            c["event"]["id"],
            c["tick"],
            c["target"],
        )
    )
    return out


def select(world: dict, positions: np.ndarray) -> Dict[str, dict]:
    """Assign every scenario an encounter, or explain why it cannot be done."""
    scenarios = list(scen.SCENARIOS)
    pools = {s.id: _candidates(s, world, positions) for s in scenarios}

    empty = [s.id for s in scenarios if not pools[s.id]]
    if empty:
        raise SelectionFailed(
            "no encounter in the pool can serve "
            + ", ".join(empty)
            + ".\n"
            + "\n".join(_shortfall(s, world) for s in scenarios if s.id in empty)
        )

    # Most-constrained first, so backtracking is cheap.
    order = sorted(scenarios, key=lambda s: len(pools[s.id]))
    chosen: Dict[str, dict] = {}
    used_events: set = set()
    used_players: set = set()

    def place(index: int) -> bool:
        if index == len(order):
            return True
        scenario = order[index]
        for candidate in pools[scenario.id]:
            event = candidate["event"]
            if event["id"] in used_events:
                continue
            # No player is the target or the shooter of more than one
            # photograph, so thirty people are not represented by the same
            # four faces. Appearing in the background of another scene is
            # fine and realistic, and is not excluded here.
            if candidate["target"] in used_players or candidate["shooter"] in used_players:
                continue
            chosen[scenario.id] = candidate
            used_events.add(event["id"])
            used_players.update({candidate["target"], candidate["shooter"]})
            if place(index + 1):
                return True
            del chosen[scenario.id]
            used_events.discard(event["id"])
            used_players.difference_update({candidate["target"], candidate["shooter"]})
        return False

    if not place(0):
        raise SelectionFailed(
            "the ten scenarios cannot be satisfied simultaneously: every "
            "assignment leaves some scenario without a distinct encounter and "
            "an unused pair of players.\nPool sizes: "
            + ", ".join(f"{s.id}={len(pools[s.id])}" for s in scenarios)
        )

    return {s.id: chosen[s.id] for s in scenarios}


def _shortfall(scenario, world) -> str:
    """Say precisely which requirement emptied the pool, one at a time."""
    events = world["encounters"]
    low, high = scen.DISTANCE_BANDS[scenario.distance]
    steps = [
        ("locale_kind", lambda e: e["locale_kind"] == scenario.locale_kind),
        ("light", lambda e: e["light"] == scenario.light),
        ("distance", lambda e: low <= e["separation_m"] <= high),
    ]
    lines = [f"  {scenario.id}:"]
    remaining = events
    for label, predicate in steps:
        remaining = [e for e in remaining if predicate(e)]
        lines.append(f"    after {label}: {len(remaining)} encounters")
    return "\n".join(lines)


def compass_heading(true_bearing: float, compass: str, rng) -> float:
    """``Shot.heading``: the true bearing plus this scenario's compass error."""
    kind, centre, sigma = scen.COMPASS_ERROR_DEG[compass]
    offset = centre + rng.gauss(0.0, sigma) if kind == "offset" else rng.gauss(centre, sigma)
    return round(math.fmod(true_bearing + offset + 360.0, 360.0), 1)
