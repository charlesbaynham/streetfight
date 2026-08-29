"""The ten photographs: what each is for, and what it must be a picture of.

Each scenario declares the *observable* properties its encounter must already
have -- where, when, how far apart, which way the target is facing, what is in
the way, who else is in shot -- plus the telemetry it needs, expressed as
constraints on the participants' real phone classes rather than as a fix to be
backdated afterwards. The selector then goes looking for an encounter that
genuinely has them.

The axis values below are chosen so that the ten *together* satisfy the
required distribution exactly; ``assert_distribution`` checks that, so the
table cannot drift out of agreement with the plan by being edited casually.
"""

from typing import Dict
from typing import List
from typing import NamedTuple
from typing import Optional


class Scenario(NamedTuple):
    id: str
    intended: str            # the truth an admin would record: hit/miss/bystander
    locale_kind: str         # street | park | forecourt
    light: str               # daylight | twilight | dark
    distance: str            # close | mid | distant
    facing: str              # toward | away
    occlusion: Optional[str]  # what is in the way, if anything
    bystanders: bool         # un-kitted passers-by in frame
    compass: str             # accurate | modest | large | miscalibrated
    # What the *fix* must be like at the moment of the shot.
    #
    # ``shooter_fix`` is the important one and is what the plan means by "fresh
    # pos": the shot carries the shooter's own position, and that is the point
    # every candidate's distance is measured from, so it anchors the whole
    # location term. ``target_fix`` is left unconstrained on most scenarios
    # because the target's staleness is the interesting *variable* rather than
    # a precondition -- pinning both was an over-reading that also emptied the
    # pool, since daylight is only twenty-six of the ninety minutes.
    # This is deliberately a property of the reading rather than of the
    # handset: an ordinary phone caught mid-window is genuinely fresh, and a
    # good phone between windows genuinely is not, so constraining the class
    # would both over-restrict the pool and misdescribe what is being tested.
    # The two scenarios where the *class* is the point name it below instead.
    target_fix: Optional[str]
    shooter_fix: Optional[str]
    garments_visible: List[str]   # which channels the photo actually shows
    probes: str              # what this photograph is testing
    note: str                # what makes the picture itself unusual

    # A second kitted player from another team who must genuinely have been
    # in frame. Unlike `bystanders` -- who are strangers, invented at render
    # time and constraining nothing -- this one has to be a real player the
    # world actually put there, because the question the photograph asks is
    # which of two *candidates* the recogniser names.
    needs_extra_kitted: bool = False

    # Required phone class, only where the class itself is what the scenario
    # is about: S8's phone left in a pocket, S9's urban canyon.
    target_phone: Optional[str] = None

    # Constraints on the target's newest fix at the moment of the shot:
    # (min, max) seconds of staleness and (min, max) metres between that fix
    # and where they really are. Expressed here so the selector must *find* an
    # encounter where the phone genuinely behaved this way, rather than
    # backdating a timestamp afterwards.
    target_fix_age_s: Optional[tuple] = None
    target_fix_distance_m: Optional[tuple] = None


# Distance bands in metres, as the plan states them.
DISTANCE_BANDS: Dict[str, tuple] = {
    "close": (3.0, 5.0),
    "mid": (8.0, 15.0),
    "distant": (25.0, 35.0),
}

# Compass error classes applied to the true bearing to make Shot.heading.
# All four appear across the ten, so every position/bearing combination is
# represented rather than only the convenient ones.
COMPASS_ERROR_DEG: Dict[str, tuple] = {
    "accurate": ("normal", 0.0, 5.0),
    "modest": ("normal", 0.0, 25.0),
    "large": ("normal", 0.0, 60.0),
    "miscalibrated": ("offset", 90.0, 5.0),
}

ALL = ["tshirt", "trousers", "hat", "armbands"]

# What "fresh" and "poor" mean, as (max_age_s, max_error_m) and
# (min_age_s, min_error_m) respectively. A reading qualifies as poor if it is
# stale *or* badly out -- either is enough to make the location term unhelpful.
FIX_FRESH = (60.0, 40.0)
FIX_POOR = (300.0, 60.0)

SCENARIOS: List[Scenario] = [
    Scenario(
        "S1", "miss", "street", "daylight", "close", "toward", None, False,
        "modest", None, "fresh", ALL,
        "the false-hit failure mode: a crosshair past the shoulder is not a hit",
        "the aim point sits off the target's shoulder, not on their torso",
    ),
    Scenario(
        "S2", "bystander", "street", "daylight", "close", "toward", None, True,
        "large", "poor", "poor", ALL,
        "bystander versus player: the crosshair is on someone not in the game",
        "an un-kitted passer-by stands under the crosshair; the kitted player is off to one side",
    ),
    Scenario(
        "S3", "hit", "park", "daylight", "close", "toward", "a park bench", False,
        "accurate", None, "fresh", ["tshirt", "hat", "armbands"],
        "partial reading: trousers and one arm are simply not in the picture",
        "seated behind a bench, so the legs and one forearm are hidden",
    ),
    Scenario(
        "S4", "hit", "forecourt", "daylight", "mid", "toward", None, True,
        "miscalibrated", "fresh", None, ALL,
        "Reed-Solomon correcting a single misread channel",
        "the armband photographs as the wrong colour; every other garment is right",
    ),
    Scenario(
        "S5", "hit", "street", "daylight", "mid", "toward", None, True,
        "accurate", None, "fresh", ALL,
        "picking the right one of two kitted players from different teams",
        "two kitted players in frame, from different teams; the crosshair is on one",
        needs_extra_kitted=True,
    ),
    Scenario(
        "S6", "hit", "street", "twilight", "distant", "away", None, False,
        "modest", None, "fresh", ALL,
        "the zoom follow-up: too far to read a colour without going closer",
        "the target is a small figure well down the street",
    ),
    Scenario(
        "S7", "hit", "park", "twilight", "close", "away", "a parked car", False,
        "large", "poor", "poor", ["tshirt", "hat", "armbands"],
        "the weak model should be unconfident here and escalate rather than guess",
        "poor light, target three-quarters away, partly behind a parked car",
    ),
    Scenario(
        "S8", "hit", "street", "twilight", "mid", "away", None, True,
        "modest", None, "fresh", ["tshirt", "trousers"],
        "the headline case: looks like a bystander, and the location term is silent",
        "hat and armband have been taken off; only the tshirt and trousers still read",
        # About twenty minutes stale and a few hundred metres out, so the
        # target's location term contributes nothing (Lambda = 1.0) while a
        # freshly-logged nearby candidate scores in the hundreds. Recovery has
        # to come from the two garments still readable, or not at all.
        target_phone="phone_in_pocket",
        target_fix_age_s=(600, 2400),
        target_fix_distance_m=(200.0, 900.0),
    ),
    Scenario(
        "S9", "hit", "park", "dark", "mid", "away", "a plane tree", False,
        "accurate", None, "fresh", ["tshirt", "hat", "armbands"],
        "three channels, trousers erased entirely",
        "behind a tree trunk: head, shirt and one armband visible, legs gone",
        target_phone="urban_canyon",
    ),
    Scenario(
        "S10", "hit", "street", "dark", "distant", "toward", "a plane tree", False,
        "modest", None, "fresh", ["tshirt", "hat"],
        "two channels only - the roadmap's hardest readable case",
        "behind a tree at distance: hat and shirt only, no armband, no legs",
    ),
]

# Two of the twenty-seven (locale, light, distance) cells are empty in a
# world of this shape -- a forecourt encounter at close range in daylight or
# twilight -- because forecourts are the rarest locale and daylight is only
# twenty-six of the ninety minutes. The assignment below therefore puts the
# single forecourt scene at mid range and moves a street scene in to close,
# which leaves every required total untouched while landing only on cells the
# world can actually supply. ``python -m backend.test_world availability``
# prints the matrix if the clock, the venue or the bands ever change.
REQUIRED_DISTRIBUTION = {
    "locale_kind": {"street": 6, "park": 3, "forecourt": 1},
    "light": {"daylight": 5, "twilight": 3, "dark": 2},
    "distance": {"close": 4, "mid": 4, "distant": 2},
    "facing": {"toward": 6, "away": 4},
}
REQUIRED_OCCLUDED = 4
REQUIRED_TREE_CASES = 2
REQUIRED_BYSTANDER_SCENES = 4


def assert_distribution() -> None:
    """The ten scenarios must jointly satisfy the plan's required spread."""
    from collections import Counter

    problems = []
    for axis, expected in REQUIRED_DISTRIBUTION.items():
        got = Counter(getattr(s, axis) for s in SCENARIOS)
        if dict(got) != expected:
            problems.append(f"{axis}: {dict(got)} != {expected}")

    occluded = [s for s in SCENARIOS if s.occlusion]
    if len(occluded) != REQUIRED_OCCLUDED:
        problems.append(f"occluded: {len(occluded)} != {REQUIRED_OCCLUDED}")
    trees = [s for s in occluded if "tree" in s.occlusion]
    if len(trees) != REQUIRED_TREE_CASES:
        problems.append(f"tree cases: {len(trees)} != {REQUIRED_TREE_CASES}")
    byst = [s for s in SCENARIOS if s.bystanders]
    if len(byst) != REQUIRED_BYSTANDER_SCENES:
        problems.append(f"bystander scenes: {len(byst)} != {REQUIRED_BYSTANDER_SCENES}")

    # Every compass class must appear, or the world only tests the easy ones.
    missing = set(COMPASS_ERROR_DEG) - {s.compass for s in SCENARIOS}
    if missing:
        problems.append(f"compass classes never exercised: {sorted(missing)}")

    if problems:
        raise AssertionError(
            "the ten scenarios do not satisfy the required distribution:\n  "
            + "\n  ".join(problems)
        )


assert_distribution()
