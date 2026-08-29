"""The world's fixed dimensions: what is locked, and what the seed may vary.

Every count here is a hard integer. The seed decides *who* gets what; it can
never change *how many*. ``assert_locked_mix`` is run at the end of casting
against the cast that was actually built, so a seed that cannot satisfy the
mix is a bug rather than a soft outcome.
"""

import datetime
from typing import Dict
from typing import List
from typing import NamedTuple

# --------------------------------------------------------------------------
# The clock
# --------------------------------------------------------------------------
# The real game date. Sunset in London that evening is 19:06 and civil dusk
# 19:40, so an 18:40-20:10 window spans low bright sun -> sunset -> twilight ->
# full dark under street lighting. The lighting variation the photographs need
# therefore falls out of the world clock instead of being imposed on it: a
# scene is a night scene because of when its encounter happened.
GAME_DATE = datetime.date(2026, 9, 19)
START_LOCAL = datetime.datetime(2026, 9, 19, 18, 40)
END_LOCAL = datetime.datetime(2026, 9, 19, 20, 10)
SUNSET_LOCAL = datetime.datetime(2026, 9, 19, 19, 6)
CIVIL_DUSK_LOCAL = datetime.datetime(2026, 9, 19, 19, 40)

# BST: one hour ahead of UTC on this date.
UTC_OFFSET_HOURS = 1

TICK_SECONDS = 1
DURATION_S = int((END_LOCAL - START_LOCAL).total_seconds())
N_TICKS = DURATION_S // TICK_SECONDS


def light_band(t_local: datetime.datetime) -> str:
    """Which of the three light bands a moment falls in.

    Named for what a photograph taken then looks like, because that is what
    the scene description has to say. The boundaries are the real solar ones
    above, not a guess.
    """
    if t_local < SUNSET_LOCAL:
        return "daylight"
    if t_local < CIVIL_DUSK_LOCAL:
        return "twilight"
    return "dark"


# --------------------------------------------------------------------------
# The cast
# --------------------------------------------------------------------------
N_TEAMS = 6
TEAM_SIZE = 5
N_PLAYERS = N_TEAMS * TEAM_SIZE

# Named for Westminster places. Never a colour word: the identity scheme
# already spends a whole channel on team colour, and a team called "Red Team"
# whose hat colour is burgundy is actively misleading -- which is exactly what
# today's sample game does.
TEAM_NAMES: List[str] = [
    "Pimlico",
    "Millbank",
    "Horseferry",
    "Victoria",
    "Vauxhall",
    "Smith Square",
]

SEX_MIX: Dict[str, int] = {"male": 15, "female": 15}
AGE_MIX: Dict[str, int] = {"25-40": 21, "18-24": 5, "41-55": 4}
ETHNICITY_MIX: Dict[str, int] = {"white": 27, "other": 3}

# How a player came by their outfit. "canonical" took the codeword the scheme
# offered; "constrained" declared a narrow wardrobe, so outfit_options could
# only offer something needing overrides; "late_patch" picked normally and was
# then altered at the door with set_identity.
PICKING_MIX: Dict[str, int] = {"canonical": 23, "constrained": 5, "late_patch": 2}

# Which garment a late patch changes. The armband, because it is the one we
# hand out at the door -- so "we ran out of lime, wear the red one" is the
# realistic reason an admin overrides somebody who has already picked.
LATE_PATCH_CHANNEL = "armbands"

# Features that make recognition hard, assigned deliberately because they are
# what the pipeline actually meets. Drawn independently of each other, so
# overlaps are allowed and expected -- a bearded man in glasses with a rucksack
# strap is a normal person, not a special case.
HARD_FEATURE_COUNTS: Dict[str, int] = {
    "long_hair_over_armband": 4,
    "glasses": 6,
    "open_jacket_over_tshirt": 5,
    "rucksack_strap_across_chest": 4,
    "beard": 5,
    "hood_bunched_at_neck": 3,
}


# Phone classes, per player. The accuracy range is what the browser reports as
# `coords.accuracy`; the staleness is how old the newest fix tends to be by the
# time somebody photographs this player.
#
# A note on window shape, because it is where the specification had to be
# pinned down. Readings are 10 s apart *inside* a window and there is nothing
# at all between windows, so how stale a player's newest fix typically is, is
# decided almost entirely by what fraction of the hour their app is open. A
# uniform "1-4 windows of 40 s to 8 minutes" caps that fraction at about a
# third, which would leave even a good phone a median of ~8 minutes stale and
# collapse its likelihood ratio from the ~350 the plan computes to under 4 --
# taking with it every scenario that needs a fresh position. So the window
# shape varies per class, chosen to land on the staleness each class is
# defined by. Someone actively hunting keeps the page open for twenty minutes
# at a stretch; someone who checks the map now and then does not. The
# staleness column is the specification, and the windows are how it is met.
class PhoneClass(NamedTuple):
    name: str
    count: int
    accuracy_m: tuple  # (low, high) metres
    windows: tuple  # (low, high) app-open windows across the hour
    window_length_s: tuple  # (low, high) seconds per window
    note: str


PHONE_CLASSES: List[PhoneClass] = [
    PhoneClass(
        "good",
        12,
        (5.0, 15.0),
        (3, 5),
        (600, 1500),
        "playing actively, app open most of the time: newest fix usually under 20s",
    ),
    PhoneClass(
        "ordinary",
        9,
        (8.0, 25.0),
        (6, 9),
        (250, 700),
        "checks the map now and then: newest fix typically 60-300s old",
    ),
    PhoneClass(
        "urban_canyon",
        4,
        (40.0, 120.0),
        (3, 5),
        (500, 1200),
        "fresh but spatially wrong - tall buildings bouncing the signal",
    ),
    PhoneClass(
        "phone_in_pocket",
        5,
        (10.0, 30.0),
        (1, 1),
        (60, 480),
        "one early window, then nothing: newest fix 10-40 min old mid-game",
    ),
]

PHONE_MIX: Dict[str, int] = {p.name: p.count for p in PHONE_CLASSES}

# A window is one stretch with the page actually open; between windows the
# phone reports nothing at all. Lengths are per class, above.
READING_INTERVAL_S = 10

# Most players open the app within the first few minutes of the game starting;
# the rest do not, so the early game has both fresh and stale phones in it.
OPENING_WINDOW_S = 240
OPENING_CHECKIN_FRACTION = 0.65

# --------------------------------------------------------------------------
# Movement
# --------------------------------------------------------------------------
# Isotropic per-axis spread of a team's members about their centroid. 55 m puts
# a five-person team across one or two Westminster blocks -- the actual street
# scale -- while sitting well above a fresh fix's effective sigma of ~21 m, so
# intra-team separations are resolvable by the location term rather than being
# swamped by fix noise. That is what makes "did it pick the right teammate" a
# real question. Uniform over the play area would be sigma ~375 m, which is a
# different and much easier problem.
TEAM_SPREAD_SIGMA_M = 55.0
TEAM_SPREAD_TRUNCATE_SIGMA = 2.5

WALK_SPEED_MS = (0.3, 1.1)
# How hard a member is pulled back toward their team's centroid each tick.
#
# Not a guess: this is *tuned* so that the motion above actually produces the
# TEAM_SPREAD_SIGMA_M spread specified, which is what the plan's whole argument
# about resolvability rests on. Walking ballistically at WALK_SPEED_MS, the
# equilibrium excursion is roughly speed/k, so the spread is quite sensitive to
# it: 0.0040 gives sigma 79 m and pins a quarter of all samples against the
# 2.5-sigma truncation (a pile-up that would distort every separation measured
# off this track), 0.0080 gives 54 m, 0.0078 gives ~55 m with essentially
# nothing reaching the clamp. Re-tune if WALK_SPEED_MS or the sigma changes.
CENTROID_RESTORE_PER_S = 0.0078

# Which pub each team starts at, chosen to force the inter-team proximity the
# photographs need. Distances measured from backend/venues.py:
#   Pimlico/Victoria      QUEENS_ARMS <-> WARWICK          42 m
#   Millbank/Horseferry   WHITE_HORSE <-> BARLEY_MOW       58 m
#   Vauxhall              MUNICH_CRICKET_CLUB       140 m from Grafton Arms
#   Smith Square          GREENCOAT_BOY             the isolated one
# The two close pairs interleave completely, deliberately: their members are
# nearer to the other team's players than the location term can separate.
TEAM_START_LANDMARKS: Dict[str, str] = {
    "Pimlico": "QUEENS_ARMS",
    "Victoria": "WARWICK",
    "Millbank": "WHITE_HORSE",
    "Horseferry": "BARLEY_MOW",
    "Vauxhall": "MUNICH_CRICKET_CLUB",
    "Smith Square": "GREENCOAT_BOY",
}

# Centroids walk between pubs on a seeded waypoint route rather than sitting
# still, so the world contains both "these two teams met" and "this fix is
# stale because they have walked on since".
CENTROID_SPEED_MS = (0.35, 0.75)
WAYPOINT_PAUSE_S = (120, 420)

# --------------------------------------------------------------------------
# Encounters
# --------------------------------------------------------------------------
# Every tick, every cross-team pair within this range is an encounter sample.
ENCOUNTER_RADIUS_M = 40.0
# Contiguous samples collapse into one event; a gap longer than this starts a
# new one rather than bridging it.
ENCOUNTER_GAP_S = 30
# An event shorter than this is two people passing through each other's
# neighbourhood, not an encounter worth photographing.
ENCOUNTER_MIN_DURATION_S = 5
# Anyone this close to the pair is "also in frame" and has to be rendered.
IN_FRAME_RADIUS_M = 25.0


def assert_locked_mix(cast: List[dict]) -> None:
    """Fail loudly if the cast does not match the locked counts exactly."""
    from collections import Counter

    checks = [
        ("sex", SEX_MIX),
        ("age_band", AGE_MIX),
        ("ethnicity", ETHNICITY_MIX),
        ("picking", PICKING_MIX),
        ("phone_class", PHONE_MIX),
    ]
    problems = []
    if len(cast) != N_PLAYERS:
        problems.append(f"cast size {len(cast)} != {N_PLAYERS}")
    for key, expected in checks:
        got = Counter(person[key] for person in cast)
        if dict(got) != expected:
            problems.append(f"{key}: got {dict(got)}, locked mix is {expected}")
    for feature, expected_n in HARD_FEATURE_COUNTS.items():
        got_n = sum(1 for person in cast if feature in person["hard_features"])
        if got_n != expected_n:
            problems.append(f"{feature}: got {got_n}, locked mix is {expected_n}")
    if problems:
        raise AssertionError(
            "cast does not satisfy the locked mix:\n  " + "\n  ".join(problems)
        )
