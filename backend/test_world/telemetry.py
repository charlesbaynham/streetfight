"""Phone-shaped position reports, derived from the truth track.

The app only reports a position while the phone is on and the page is open,
so a player does not have *a* location -- they have a timeline of fixes with
gaps in it, and by the time somebody photographs them the newest fix may be
minutes old and hundreds of metres away. That case is not an edge case; it is
Saturday night with a phone in a coat pocket.

Only what this module produces is ever written to the database. The truth
track that it samples stays in the world file, for composing photographs and
for scoring afterwards.

The numbers are chosen against the real model in
``backend.shot_identification``: sigma_eff^2 = sigma_fix^2 + 2*D*age with
D = 20 m^2/s, and Lambda = max(1, (A / 2*pi*sigma_eff^2) * exp(-d^2 / 2*sigma_eff^2))
with A = 1e6 m^2. A fix about 66 minutes old contributes nothing at all
whatever the distance; a 15-minute-old fix 400 m away is already silent. The
world is simulated long enough to produce that naturally rather than by
backdating a timestamp.
"""

from typing import Dict
from typing import List

import numpy as np

from backend.test_world import geo
from backend.test_world import spec
from backend.test_world.movement import _stream_seed

PHONE_BY_NAME = {p.name: p for p in spec.PHONE_CLASSES}


def _windows_for(phone, rng: np.random.Generator) -> List[tuple]:
    """The (start_tick, end_tick) stretches during which the app is open."""
    n = int(rng.integers(phone.windows[0], phone.windows[1] + 1))

    if phone.name == "phone_in_pocket":
        # One early window and then nothing, so that by the second half of the
        # game this player's newest fix is 10-40 minutes old *by construction*:
        # it is genuinely where they were when the app was last open, and the
        # truth track has walked on at a real speed since.
        # Spread the single window across the first twenty minutes rather than
        # the first ten, so the five pocket players do not all go stale in
        # lockstep: the selector needs a choice of players whose fix is 10-40
        # minutes old at the moment of a given encounter, not one moment when
        # all five are.
        start = int(rng.integers(0, 1200))
        length = int(rng.integers(*phone.window_length_s))
        return [(start, min(start + length, spec.N_TICKS))]

    # Otherwise scatter the windows across the hour without overlapping.
    starts = sorted(
        int(s) for s in rng.choice(spec.N_TICKS, n, replace=False)
    )
    windows = []
    for start in starts:
        length = int(rng.integers(*phone.window_length_s))
        end = min(start + length, spec.N_TICKS)
        if windows and start < windows[-1][1]:
            # Overlaps the previous window: extend it rather than dropping
            # this one, so a class's total coverage is not quietly eaten by
            # collisions between its own windows.
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
            continue
        windows.append((start, end))
    return windows


def fix_timelines(
    seed: int, cast: List[dict], positions: np.ndarray
) -> Dict[str, List[dict]]:
    """One list of fixes per player slug, oldest first.

    Each fix carries what the browser would hand us: latitude, longitude, an
    accuracy in metres, and the timestamp it was taken at. The error is drawn
    with sigma equal to that reported accuracy, which is what makes the
    urban-canyon class *honest* rather than merely inaccurate -- it reports a
    large accuracy and is wrong by about that much.
    """
    out: Dict[str, List[dict]] = {}

    for index, person in enumerate(cast):
        phone = PHONE_BY_NAME[person["phone_class"]]
        rng = np.random.default_rng(_stream_seed(seed, "phone", person["slug"]))

        # One accuracy per player: a given handset in a given place is
        # consistently good or consistently poor, and re-drawing it per fix
        # would average that character away.
        accuracy = float(rng.uniform(*phone.accuracy_m))

        fixes = []
        for start, end in _windows_for(phone, rng):
            for tick in range(start, end, spec.READING_INTERVAL_S):
                true_east, true_north = positions[tick, index]
                error = rng.normal(0.0, accuracy, size=2)
                lat, long = geo.to_latlong(
                    true_east + error[0], true_north + error[1]
                )
                fixes.append(
                    {
                        "t": int(tick),
                        "lat": round(float(lat), 7),
                        "long": round(float(long), 7),
                        "accuracy": round(accuracy, 1),
                    }
                )
        out[person["slug"]] = fixes

    return out


def newest_fix_at(fixes: List[dict], tick: int):
    """The most recent fix at or before ``tick``, or None if there is none."""
    newest = None
    for fix in fixes:
        if fix["t"] > tick:
            break
        newest = fix
    return newest


def effective_sigma_m(accuracy: float, age_s: float) -> float:
    """``shot_identification``'s sigma_eff, for reporting at the gate."""
    from backend.shot_identification import DIFFUSION_M2_PER_S

    return float(np.sqrt(accuracy**2 + 2 * DIFFUSION_M2_PER_S * max(age_s, 0.0)))


def likelihood_ratio(accuracy: float, age_s: float, distance_m: float) -> float:
    """``shot_identification``'s Lambda, for reporting at the gate.

    A ratio of 1.0 means the fix has stopped speaking: it neither supports nor
    suppresses this candidate. That is the state the phone-in-pocket players
    are built to reach.
    """
    from backend.shot_identification import GAME_AREA_M2

    sigma = effective_sigma_m(accuracy, age_s)
    spread = 2 * np.pi * sigma**2
    return float(
        max(1.0, (GAME_AREA_M2 / spread) * np.exp(-(distance_m**2) / (2 * sigma**2)))
    )
