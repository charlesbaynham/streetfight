"""Assemble the whole world into one file, and read it back.

``world.json`` is the single source of truth. The cast, the telemetry, the
encounter pool and (later) the scene descriptions and every image's prompt
hash live here; everything else -- the manifest, the fixture directory -- is
*derived* from it by a command rather than maintained by hand.

Two things are deliberately kept out of the reproducible core:

* **The truth track** is written to a separate file. It is 30 x 5400 x 2
  floats, which would swamp a file meant to be read by a human at a gate, and
  it is regenerated identically from the seed anyway.
* **Database ids** live in their own section and are excluded from the
  reproducibility check. They are an artifact of materialising the world into
  a particular database, not a property of the world.
"""

import json
from pathlib import Path
from typing import Optional

import numpy as np

from backend.test_world import encounters as encounters_mod
from backend.test_world import spec
from backend.test_world import telemetry as telemetry_mod
from backend.test_world.movement import truth_track
from backend.test_world.personas import build_cast

WORLD_VERSION = 1


def build(seed: int, provision_db: bool = True) -> dict:
    """The entire world, as a plain dictionary.

    ``provision_db`` writes the cast into whatever database is currently
    configured, through the real picking code, and records what each player
    ended up wearing. Turn it off to compute the geometry alone -- useful for
    inspecting a candidate seed without touching a database.
    """
    cast = build_cast(seed)
    track = truth_track(seed, cast)
    positions = track["positions"]
    fixes = telemetry_mod.fix_timelines(seed, cast, positions)
    events = encounters_mod.sweep(cast, positions)

    identity = None
    if provision_db:
        from backend.test_world.cast import provision

        identity = provision(seed, cast)

    world = {
        "version": WORLD_VERSION,
        "seed": seed,
        "venue": _venue_summary(),
        "clock": {
            "date": spec.GAME_DATE.isoformat(),
            "start_local": spec.START_LOCAL.strftime("%H:%M"),
            "end_local": spec.END_LOCAL.strftime("%H:%M"),
            "sunset_local": spec.SUNSET_LOCAL.strftime("%H:%M"),
            "civil_dusk_local": spec.CIVIL_DUSK_LOCAL.strftime("%H:%M"),
            "utc_offset_hours": spec.UTC_OFFSET_HOURS,
            "ticks": spec.N_TICKS,
        },
        "cast": cast,
        "teams": [
            {
                "name": name,
                "slug": name.lower().replace(" ", "-"),
                "start_landmark": spec.TEAM_START_LANDMARKS[name],
            }
            for name in spec.TEAM_NAMES
        ],
        "fixes": fixes,
        "encounters": events,
        "encounter_summary": encounters_mod.summarise(events),
        "telemetry_summary": _telemetry_summary(cast, positions, fixes),
    }
    if identity is not None:
        world["identity"] = {
            k: v for k, v in identity.items() if k in ("team_colours", "players")
        }
        world["database_ids"] = {
            "game_id": identity["game_id"],
            "team_ids": identity["team_ids"],
            "player_ids": {
                slug: entry["user_id"] for slug, entry in identity["players"].items()
            },
        }
        for entry in world["identity"]["players"].values():
            entry.pop("user_id", None)

    return world


def _venue_summary() -> dict:
    from backend.venues import ACTIVE_VENUE

    bounds = ACTIVE_VENUE.map.bounds
    return {
        "name": ACTIVE_VENUE.name,
        "bounds": {
            "north": bounds.north,
            "south": bounds.south,
            "east": bounds.east,
            "west": bounds.west,
        },
    }


def _telemetry_summary(cast, positions, fixes) -> dict:
    """How stale and how wrong each phone class actually turned out.

    Reported at the gate because it is the thing most likely to drift when
    somebody retunes the movement: if a class stops matching the staleness it
    is defined by, the scenarios that depend on it quietly stop testing what
    they claim to.
    """
    from collections import defaultdict

    from backend.test_world import geo

    ages = defaultdict(list)
    errors = defaultdict(list)
    for tick in range(spec.N_TICKS // 2, spec.N_TICKS, 120):
        for index, person in enumerate(cast):
            fix = telemetry_mod.newest_fix_at(fixes[person["slug"]], tick)
            if fix is None:
                continue
            east, north = geo.to_m(fix["lat"], fix["long"])
            true_east, true_north = positions[tick, index]
            ages[person["phone_class"]].append(tick - fix["t"])
            errors[person["phone_class"]].append(
                float(np.hypot(east - true_east, north - true_north))
            )

    return {
        name: {
            "median_age_s": round(float(np.median(ages[name])), 1),
            "p90_age_s": round(float(np.percentile(ages[name], 90)), 1),
            "median_position_error_m": round(float(np.median(errors[name])), 1),
            "note": phone.note,
        }
        for name, phone in ((p.name, p) for p in spec.PHONE_CLASSES)
        if ages[name]
    }


def save(world: dict, path: Path, track: Optional[dict] = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(world, indent=1, sort_keys=True) + "\n")
    if track is not None:
        np.savez_compressed(
            path.with_suffix(".truth.npz"), positions=track["positions"]
        )


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def reproducible_core(world: dict) -> str:
    """The part of a world that a seed determines, canonically serialised.

    Excludes ``database_ids``, which depend on nothing but the seed either but
    are an artifact of materialisation rather than of the world.
    """
    core = {k: v for k, v in world.items() if k != "database_ids"}
    return json.dumps(core, indent=1, sort_keys=True)
