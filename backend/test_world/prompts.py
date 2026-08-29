"""Turn a selected encounter into a scene description, and that into a prompt.

The image model is told what to render and decides nothing. Whether a shot is
a night scene, a park scene, a close-up or a distant figure is already settled
by the encounter that was selected -- by the world clock, the locale the pair
were standing in, and how far apart they actually were. The prompt only says
so in words.

Every garment colour is named *and* given its hex, and the same hexes are
rendered into ``kit_swatches.png`` and passed alongside as an input image, so
"salmon" cannot drift into whatever the model imagines salmon to be.
"""

import random
from typing import Dict
from typing import List

from backend.identity.config import buckets_for_channel
from backend.identity.config import hex_for
from backend.test_world import locales as locales_mod
from backend.test_world import scenarios as scen
from backend.test_world import spec

# One evening, so one weather. Drawn from the seed rather than chosen, but
# fixed across all ten scenes: a world where it rains for scene 3 and not
# scene 4 is not an evening, it is a mood board.
WEATHER = [
    "dry, high thin cloud, no wind",
    "dry and clear, a light breeze",
    "dry after earlier rain, damp pavements reflecting the light",
    "overcast and still, flat grey light",
]

LIGHT_WORDS = {
    "daylight": (
        "low early-evening sun, still bright, long shadows across the ground, "
        "warm side light"
    ),
    "twilight": (
        "after sunset, the sky still pale blue-grey but the ground in soft "
        "shadow, street lights just coming on and not yet dominant"
    ),
    "dark": (
        "full darkness, lit only by street lighting and shop windows - pools "
        "of warm sodium and cold LED with genuinely dark gaps between them"
    ),
}

# Distance, how the phone is held, and -- the part the model actually obeys --
# how much of the frame the subject fills. Told only the distance in metres it
# frames every shot like a portrait whatever the scene says, because that is
# what a photograph of a person usually looks like. A fraction of the frame
# height is a thing it can check itself against, and it is what the distance
# means anyway: a figure 30 m off is a small shape in a wide street, not a
# person photographed from further away.
CAMERA = {
    "close": (
        "3-5 metres",
        "chest height, phone held up in both hands",
        "head to foot, filling about half the frame height, with the street "
        "visible all around them",
    ),
    "mid": (
        "8-15 metres",
        "chest height, phone held up in one hand",
        "about a quarter of the frame height - a whole person with a lot of "
        "street around them, not a portrait",
    ),
    "distant": (
        "25-35 metres",
        "chest height, phone held up and slightly zoomed",
        "no more than about one tenth of the frame height - a small,"
        " recognisable figure a long way down the street, with the buildings,"
        " road and pavement taking up most of the picture. Their face should"
        " be too small to make out",
    ),
}

# A shot is conditioned on its target's reference photo so that it is the same
# person -- but left at that, the model reproduces the reference *exactly*:
# same stance, same expression, same camera angle, transplanted onto a street.
# That would hand the escalation model a pixel match instead of the
# recognition problem this fixture exists to pose, so the pose is drawn here
# and stated, and the prompt says outright which parts of the reference to
# take and which to throw away.
POSES = {
    "toward": [
        "walking towards the camera mid-stride, weight on one leg, one arm swinging",
        "stopped mid-step and looking up, as if they have just noticed the phone",
        "standing side-on to the camera with their head turned towards it, "
        "caught mid-sentence",
        "half-turned towards the camera with one hand raised, about to wave "
        "somebody off",
        "leaning against a wall looking straight down the lens, one hand in a pocket",
    ],
    "away": [
        "walking away from the camera and glancing back over one shoulder",
        "three-quarters turned away, looking off down the street at something "
        "out of frame",
        "crouched with their back mostly to the camera, retying a shoelace",
        "half-turned away with a phone held up to one ear",
        "striding across the frame in profile, not looking at the camera at all",
    ],
}


def person_sentence(person: dict) -> str:
    """One person, described the way a witness would describe them."""
    ethnicity = (
        "white" if person["ethnicity"] == "white" else "of another ethnic background"
    )
    who = f"{person['age']}-year-old {ethnicity} {person['sex']}"
    features = []
    if "glasses" in person["hard_features"]:
        features.append("wearing glasses")
    if "beard" in person["hard_features"]:
        features.append("with a short beard")
    if "long_hair_over_armband" in person["hard_features"]:
        features.append("with long hair falling loose over the upper arms")
    if "rucksack_strap_across_chest" in person["hard_features"]:
        features.append("a rucksack strap running diagonally across the chest")
    if "open_jacket_over_tshirt" in person["hard_features"]:
        # Worded so it stays a *hard* case without becoming a contradiction:
        # on several scenes the t-shirt is one of the few channels that still
        # reads, and a jacket that covered it would quietly change what the
        # photograph tests.
        features.append(
            "an unzipped jacket hanging open, with a clear vertical strip of "
            "the t-shirt visible between its front edges"
        )
    if "hood_bunched_at_neck" in person["hard_features"]:
        features.append("a hood pushed back and bunched at the neck")
    tail = ", ".join(features)
    return (
        f"{who}, {person['build']} build, {person['hair_style']} "
        f"{person['hair_colour']} hair, {person['distinguishing']}"
        + (f", {tail}" if tail else "")
    )


def garment_sentence(appearance: Dict[str, str], visible: List[str]) -> str:
    """What the player is wearing, colour-named and hex-pinned, per garment."""
    # Only the armband phrase puts the colour first, so it is the only one
    # whose article depends on the colour; the others are always "a plain".
    words = {
        "tshirt": "a plain {colour} t-shirt",
        "trousers": "plain {colour} trousers",
        "hat": "a plain {colour} baseball cap",
        "armbands": "{an} {colour} elasticated armband on each upper arm",
    }
    parts = []
    for channel in ("tshirt", "trousers", "hat", "armbands"):
        if channel not in visible:
            continue
        colour = appearance[channel]
        note = buckets_for_channel(channel).get(colour)
        # "a orange armband" reads as a mistake and invites the model to
        # treat the whole line as sloppy; the colour names are the one thing
        # in this prompt that must be taken literally.
        described = words[channel].format(
            colour=colour, an="an" if colour[0] in "aeiou" else "a"
        )
        parts.append(
            f"{described} in exactly {hex_for(channel, colour)}"
            + (f" ({note})" if note else "")
        )
    return "; ".join(parts)


def scene_description(world, chosen, scenario, extra_kitted) -> dict:
    """The full, human-reviewable description of one photograph."""
    cast_by_slug = {p["slug"]: p for p in world["cast"]}
    players = world["identity"]["players"]
    event = chosen["event"]
    target = cast_by_slug[chosen["target"]]
    shooter = cast_by_slug[chosen["shooter"]]
    locale = next(loc for loc in locales_mod.LOCALES if loc.name == event["locale"])

    rng = random.Random(f"{world['seed']}:scene:{scenario.id}")
    distance_words, camera_height, framing = CAMERA[scenario.distance]

    facing = (
        "facing the camera, looking towards it"
        if scenario.facing == "toward"
        else "turned three-quarters away from the camera, looking off to one side"
    )
    pose = rng.choice(POSES[scenario.facing])

    return {
        "scenario": scenario.id,
        "intended_result": scenario.intended,
        "probes": scenario.probes,
        "encounter_id": event["id"],
        "tick": chosen["tick"],
        "time_local": _tick_time(chosen["tick"]),
        "light": scenario.light,
        "weather": WEATHER[rng.randrange(len(WEATHER))],
        "locale": locale.name,
        "locale_kind": locale.kind,
        "setting": locale.description,
        "separation_m": chosen["separation_m"],
        "distance_band": scenario.distance,
        "camera": {
            "distance": distance_words,
            "height": camera_height,
            "framing": framing,
        },
        "target": {
            "slug": target["slug"],
            "team": target["team"],
            "persona": person_sentence(target),
            "facing": facing,
            "pose": pose,
            "appearance": players[target["slug"]]["appearance"],
            "garments_visible": list(scenario.garments_visible),
            "garments": garment_sentence(
                players[target["slug"]]["appearance"], scenario.garments_visible
            ),
        },
        "shooter": {"slug": shooter["slug"], "team": shooter["team"]},
        "occlusion": scenario.occlusion,
        "bystanders": scenario.bystanders,
        "other_kitted_in_frame": [
            {
                "slug": o["slug"],
                "team": o["team"],
                "distance_m": o["distance_m"],
                "persona": person_sentence(cast_by_slug[o["slug"]]),
                "garments": garment_sentence(
                    players[o["slug"]]["appearance"], scen.ALL
                ),
            }
            for o in extra_kitted
        ],
        "note": scenario.note,
    }


def _tick_time(tick: int) -> str:
    import datetime

    return (spec.START_LOCAL + datetime.timedelta(seconds=int(tick))).strftime("%H:%M")


def _street_led_opening(scene: dict) -> List[str]:
    """The opening of a distant shot: a photograph *of a street*.

    Told "25-35 metres from the subject" the model renders a portrait anyway,
    and adding a fraction of the frame height only moved it from about half to
    about a third. It frames whatever the sentence is *about* -- so for the
    distant band the sentence is about the street, and the player is an
    incidental detail in it. Measured while wiring up Gate E: this reliably
    fills the frame with road, cars and buildings, though the figure still
    lands nearer a third of the frame height than the tenth it asks for. The
    rest of the way is the aim-point crop's job, not the prompt's.
    """
    return [
        f"A wide photograph of {scene['locale']}, Westminster, London, taken "
        "on a mobile phone by somebody standing on the pavement. The subject "
        "of the picture is the street itself.",
        "",
        f"THE STREET: {scene['setting']}. It fills the frame - road, "
        "pavement, buildings, parked cars, the sky above.",
        f"TIME AND LIGHT: {scene['time_local']}, {LIGHT_WORDS[scene['light']]}. "
        f"Weather: {scene['weather']}.",
        "",
        "SOMEWHERE IN IT, ONE PERSON: a long way down the street, about "
        f"{scene['camera']['distance']} from the camera, there is one person, "
        "standing on the pavement in the middle distance. They are a small "
        "figure in a big picture, their face too small to make out. Do not "
        "walk closer to them, do not zoom in, and do not compose the "
        "photograph around them - they are incidental. Their whole body from "
        "cap to shoes must be inside the frame.",
    ]


def shot_prompt(scene: dict) -> str:
    """The generation prompt for one shot photograph."""
    if scene["distance_band"] == "distant":
        lines = _street_led_opening(scene)
    else:
        lines = [
            "A candid photograph taken on a mobile phone by someone playing a "
            "street game, held up quickly and not carefully composed.",
            "",
            f"SETTING: {scene['locale']}, Westminster, London - "
            f"{scene['setting']}.",
            f"TIME AND LIGHT: {scene['time_local']}, "
            f"{LIGHT_WORDS[scene['light']]}. Weather: {scene['weather']}.",
            f"CAMERA: {scene['camera']['distance']} from the subject, "
            f"{scene['camera']['height']}.",
            f"HOW BIG IN FRAME: the subject appears "
            f"{scene['camera']['framing']}. This is the size they really are "
            f"at that distance, and it matters more than making a nice "
            f"picture of them - the photograph is cropped afterwards, so "
            f"leave room on all sides.",
        ]

    lines += [
        "",
        "THE SAME PERSON: the attached indoor photograph is a posed reference "
        "shot of this person, taken standing still against a wall before the "
        "game started. Take from it only who they are - face, hair, build - "
        "and the exact colours of their kit. Everything else must be "
        "different: this is a candid photograph of them out in the street "
        "later that evening. Do not reproduce the reference's pose, "
        "expression, camera angle, framing or lighting.",
        "",
        f"SUBJECT: {scene['target']['persona']}. "
        f"{scene['target']['facing'][0].upper()}{scene['target']['facing'][1:]}, "
        f"{scene['target']['pose']}.",
        f"WEARING: {scene['target']['garments']}.",
    ]

    hidden = [c for c in scen.ALL if c not in scene["target"]["garments_visible"]]
    if hidden:
        lines.append(
            "NOT VISIBLE: the subject's "
            + ", ".join(hidden)
            + " must not be visible in the photograph at all."
        )
    if scene["occlusion"]:
        lines.append(f"IN THE WAY: {scene['occlusion']} partly obscures the subject.")

    if scene["other_kitted_in_frame"]:
        lines.append("")
        for other in scene["other_kitted_in_frame"]:
            lines.append(
                f"ALSO IN FRAME (a second player, clearly visible, further from "
                f"the camera): {other['persona']}, wearing {other['garments']}."
            )
    if scene["bystanders"]:
        lines.append("")
        lines.append(
            "ALSO IN FRAME: two or three ordinary passers-by in ordinary "
            "street clothes, wearing no caps and no armbands of any kind. They "
            "are not part of the game."
        )

    garment_words = {
        "tshirt": "t-shirt",
        "trousers": "trousers",
        "hat": "cap",
        "armbands": "armbands",
    }
    named = [
        garment_words[c] for c in scen.ALL if c in scene["target"]["garments_visible"]
    ]
    listed = ", ".join(named[:-1]) + (" and " + named[-1] if len(named) > 1 else "")

    lines += [
        "",
        "STYLE: an ordinary phone snapshot - slightly noisy in low light, "
        "natural colours, no filter, no artistic grading, no text or "
        f"watermark. The colours of the {listed} must match the named hex "
        "values exactly; they are the point of the photograph. Refer to the "
        "attached colour swatch card.",
    ]
    return "\n".join(lines)


def reference_prompt(person: dict, appearance: Dict[str, str]) -> str:
    """The generation prompt for one player's reference photo at the door."""
    return "\n".join(
        [
            "A full-length reference photograph of one person, taken on a "
            "mobile phone indoors by an organiser before a game begins.",
            "",
            "SETTING: the attached photograph of a living room. Place the "
            "person standing in THAT room, in front of the bookcase and the "
            "doorway, on the wooden floor. Do not invent a different room: "
            "use the room in the attached image, with its furniture, plants "
            "and lighting as they are.",
            "",
            f"SUBJECT: {person_sentence(person)}. Standing squarely facing the "
            "camera, arms relaxed at their sides so both upper arms are "
            "clearly visible, a neutral expression.",
            f"WEARING: {garment_sentence(appearance, scen.ALL)}.",
            "",
            "STYLE: an ordinary indoor phone snapshot, full length with the "
            "whole body from cap to shoes in frame, natural indoor lighting, "
            "no filter, no text or watermark. The colours of the cap, "
            "armbands, t-shirt and trousers must match the named hex values "
            "exactly. Refer to the attached colour swatch card.",
        ]
    )


BACKGROUND_PROMPT = "\n".join(
    [
        "A photograph of an empty domestic living room, taken on a mobile "
        "phone, with nobody in it.",
        "",
        "A small British living room: a wooden bookcase of paperbacks against "
        "one wall, trailing pothos plants along the tops of the walls, a "
        "wooden internal door standing open onto a hallway, laminate wood "
        "flooring, a patterned red runner rug, a wall-mounted television, "
        "and a wooden cabinet. Warm domestic lighting from a table lamp, "
        "daylight from out of frame.",
        "",
        "STYLE: an ordinary phone snapshot, natural colours, no filter, no "
        "people, no text or watermark. Framed from about chest height looking "
        "along the room towards the open door.",
    ]
)
