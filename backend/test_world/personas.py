"""Thirty different people, drawn to an exactly locked mix.

Every attribute is dealt from a list built to the locked counts and then
shuffled, rather than sampled per person and checked afterwards. Sampling
would make the counts a distribution; dealing makes them a guarantee, and the
seed is left to decide only *who* gets what.

Nothing here touches the database or the identity scheme. A persona is what a
person looks like; what they are wearing is decided later, by the real picking
code (see ``cast.py``).
"""

import random
from typing import Dict
from typing import List

from backend.test_world import spec


def _deal(counts: Dict[str, int], rng: random.Random) -> List[str]:
    """One label per player, in the locked proportions, shuffled."""
    pool: List[str] = []
    for label, n in counts.items():
        pool.extend([label] * n)
    rng.shuffle(pool)
    return pool


# Deliberately mundane. These people are meant to look like a Tuesday evening
# in Westminster, not like a casting call: the recogniser's job is hard because
# ordinary people in ordinary clothes look alike, and a cast of memorable
# individuals would quietly make the benchmark easier than the real thing.
BUILDS = ["slight", "slim", "average", "average", "stocky", "broad", "tall and lean"]
HAIR_COLOURS = [
    "dark brown",
    "brown",
    "black",
    "light brown",
    "blonde",
    "auburn",
    "grey",
]
HAIR_STYLES_LONG = ["long straight", "long wavy", "shoulder-length", "long curly"]
HAIR_STYLES_SHORT = ["short", "cropped", "buzzed", "short and tousled", "tied back"]
DISTINGUISHING = [
    "a lanyard still round their neck from work",
    "bright white trainers",
    "a tote bag over one shoulder",
    "a watch with a chunky metal strap",
    "headphones round the neck",
    "a pint glass still in hand",
    "rolled-up sleeves",
    "a bike helmet clipped to their bag",
    "sunglasses pushed up onto their head",
    "a scarf loose round the neck",
    "muddy boots",
    "a phone held out in front of them",
    "a plaster on one knuckle",
    "a beanie stuffed in a pocket",
    "a camera slung across the body",
    "a folded newspaper under one arm",
    "keys carabinered to a belt loop",
    "a takeaway coffee cup",
    "a club wristband from the weekend",
    "paint-flecked hands",
    "a gym bag at their feet",
    "a cycling cap under one arm",
    "a plaster across the bridge of the nose",
    "a cardigan knotted round the waist",
    "an umbrella hooked on a forearm",
    "a laptop bag worn crossbody",
    "hi-vis strips on their trainers",
    "a pen behind one ear",
    "a hair clip holding a fringe back",
    "a canvas bucket hat in one hand",
]

FIRST_NAMES_M = [
    "Tom",
    "Ali",
    "James",
    "Dan",
    "Rob",
    "Sam",
    "Josh",
    "Marcus",
    "Ben",
    "Nick",
    "Owen",
    "Chris",
    "Adam",
    "Luke",
    "Ravi",
]
FIRST_NAMES_F = [
    "Ellie",
    "Priya",
    "Hannah",
    "Kate",
    "Sophie",
    "Amy",
    "Nadia",
    "Jess",
    "Laura",
    "Beth",
    "Rachel",
    "Zoe",
    "Chloe",
    "Maya",
    "Fran",
]
SURNAMES = [
    "Ashby",
    "Bell",
    "Coyle",
    "Doran",
    "Ellis",
    "Fenn",
    "Gale",
    "Hart",
    "Irwin",
    "Judd",
    "Kerr",
    "Lowe",
    "Mace",
    "Nash",
    "Ogden",
    "Pryce",
    "Quill",
    "Rand",
    "Sayer",
    "Tate",
    "Usher",
    "Vaughn",
    "Ward",
    "Yates",
    "Zane",
    "Abbott",
    "Brody",
    "Chase",
    "Dunn",
    "Frost",
]


def build_cast(seed: int) -> List[dict]:
    """The thirty personas, team-assigned, satisfying every locked count.

    Teams are filled in order, so ``pimlico-1`` .. ``pimlico-5`` are the
    Pimlico five; the shuffled attribute deals mean that ordering carries no
    other information.
    """
    rng = random.Random(f"{seed}:cast")

    sexes = _deal(spec.SEX_MIX, rng)
    ages = _deal(spec.AGE_MIX, rng)
    ethnicities = _deal(spec.ETHNICITY_MIX, rng)
    pickings = _deal(spec.PICKING_MIX, rng)
    phones = _deal(spec.PHONE_MIX, rng)

    male_names = FIRST_NAMES_M[:]
    female_names = FIRST_NAMES_F[:]
    rng.shuffle(male_names)
    rng.shuffle(female_names)
    surnames = SURNAMES[:]
    rng.shuffle(surnames)
    distinguishing = DISTINGUISHING[:]
    rng.shuffle(distinguishing)

    cast: List[dict] = []
    for index in range(spec.N_PLAYERS):
        team_name = spec.TEAM_NAMES[index // spec.TEAM_SIZE]
        team_slug = team_name.lower().replace(" ", "-")
        member_no = index % spec.TEAM_SIZE + 1
        sex = sexes[index]
        first = (male_names if sex == "male" else female_names).pop()
        age_band = ages[index]
        low, high = (int(part) for part in age_band.split("-"))
        cast.append(
            {
                "slug": f"{team_slug}-{member_no}",
                "team": team_name,
                "team_slug": team_slug,
                "name": f"{first} {surnames[index]}",
                "sex": sex,
                "age_band": age_band,
                "age": rng.randint(low, high),
                "ethnicity": ethnicities[index],
                "picking": pickings[index],
                "phone_class": phones[index],
                "build": rng.choice(BUILDS),
                "hair_colour": rng.choice(HAIR_COLOURS),
                "distinguishing": distinguishing[index],
                "hard_features": [],
            }
        )

    # Hard features are dealt per feature, not per person: each is given to
    # exactly its locked number of distinct players, drawn independently of
    # every other feature, so overlaps happen naturally.
    for feature, n in spec.HARD_FEATURE_COUNTS.items():
        for person in rng.sample(cast, n):
            person["hard_features"].append(feature)

    # Hair style has to agree with the features: whoever was dealt hair falling
    # over an armband needs hair long enough to do it.
    for person in cast:
        if "long_hair_over_armband" in person["hard_features"]:
            person["hair_style"] = rng.choice(HAIR_STYLES_LONG)
        else:
            person["hair_style"] = rng.choice(HAIR_STYLES_SHORT + HAIR_STYLES_LONG[:2])
        person["hard_features"].sort()

    spec.assert_locked_mix(cast)
    return cast
