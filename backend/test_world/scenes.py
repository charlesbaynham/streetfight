"""Build all forty-one scene descriptions and their prompts.

Ten shot photographs selected from the world, thirty reference photographs
taken at the door, and the one living-room background they all share. The
background is generated (or supplied) *first*, because every reference prompt
passes it in as an input image with the instruction to place this person in
that room rather than to invent one -- so the only thing that varies between
the thirty is the person and their kit.
"""

import math
from typing import Dict
from typing import List

import numpy as np

from backend.test_world import geo
from backend.test_world import misreads
from backend.test_world import prompts as prompts_mod
from backend.test_world import scenarios as scen
from backend.test_world import select as select_mod
from backend.test_world import telemetry as telemetry_mod


def build(world: dict, positions: np.ndarray) -> dict:
    """Every scene, ready for review at Gate B. Free; no network."""
    import random

    chosen = select_mod.select(world, positions)
    cast_by_slug = {p["slug"]: p for p in world["cast"]}
    index_of = {p["slug"]: i for i, p in enumerate(world["cast"])}
    players = world["identity"]["players"]

    shots: List[dict] = []
    for scenario in scen.SCENARIOS:
        candidate = chosen[scenario.id]
        tick = candidate["tick"]
        extra = (
            select_mod._extra_kitted_at(
                world["cast"], positions, tick, candidate["target"], candidate["shooter"]
            )
            if scenario.needs_extra_kitted
            else []
        )
        scene = prompts_mod.scene_description(world, candidate, scenario, extra)

        shooter_i = index_of[candidate["shooter"]]
        target_i = index_of[candidate["target"]]
        true_bearing = float(
            geo.bearing_deg(
                positions[tick, shooter_i, 0],
                positions[tick, shooter_i, 1],
                positions[tick, target_i, 0],
                positions[tick, target_i, 1],
            )
        )
        rng = random.Random(f"{world['seed']}:heading:{scenario.id}")
        scene["true_bearing"] = round(true_bearing, 1)
        scene["compass_class"] = scenario.compass
        scene["heading"] = select_mod.compass_heading(
            true_bearing, scenario.compass, rng
        )

        # What the database will actually be told, so a reviewer can see the
        # gap between the picture and the evidence at a glance.
        scene["telemetry"] = _telemetry_view(world, positions, candidate)

        if scenario.id == "S4":
            misread = misreads.choose_misread(world, candidate["target"])
            if misread is None:
                raise RuntimeError(
                    "S4 needs an armband misread that still decodes to the "
                    f"intended player, and {candidate['target']} has none"
                )
            scene["misread"] = misread
            # The photograph must show the *wrong* colour, so the prompt has
            # to be built from a doctored appearance rather than the truth.
            doctored = dict(scene["target"]["appearance"])
            doctored[misread["channel"]] = misread["photographed_as"]
            scene["target"]["photographed_appearance"] = doctored
            scene["target"]["garments"] = prompts_mod.garment_sentence(
                doctored, scenario.garments_visible
            )

        scene["prompt"] = prompts_mod.shot_prompt(scene)
        shots.append(scene)

    references = []
    for person in world["cast"]:
        appearance = players[person["slug"]]["appearance"]
        references.append(
            {
                "slug": person["slug"],
                "team": person["team"],
                "persona": prompts_mod.person_sentence(person),
                "appearance": appearance,
                "prompt": prompts_mod.reference_prompt(person, appearance),
            }
        )

    return {
        "background": {"prompt": prompts_mod.BACKGROUND_PROMPT},
        "shots": shots,
        "references": references,
    }


def _telemetry_view(world, positions, candidate) -> dict:
    """The fixes the database will hold, and what they are worth."""
    cast = world["cast"]
    fixes = world["fixes"]
    index_of = {p["slug"]: i for i, p in enumerate(cast)}
    tick = candidate["tick"]

    out = {}
    for role in ("target", "shooter"):
        slug = candidate[role]
        fix = telemetry_mod.newest_fix_at(fixes[slug], tick)
        if fix is None:
            out[role] = {"slug": slug, "fix": None, "note": "never reported"}
            continue
        east, north = geo.to_m(fix["lat"], fix["long"])
        true_east, true_north = positions[tick, index_of[slug]]
        error = float(math.hypot(float(east) - true_east, float(north) - true_north))
        age = tick - fix["t"]
        out[role] = {
            "slug": slug,
            "phone_class": next(p["phone_class"] for p in cast if p["slug"] == slug),
            "fix_age_s": int(age),
            "fix_error_m": round(error, 1),
            "accuracy_m": fix["accuracy"],
            "sigma_eff_m": round(telemetry_mod.effective_sigma_m(fix["accuracy"], age), 1),
            "lambda_at_true_position": round(
                telemetry_mod.likelihood_ratio(fix["accuracy"], age, error), 2
            ),
        }
    return out
