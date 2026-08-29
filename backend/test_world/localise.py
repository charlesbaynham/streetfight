"""Where things are in a generated photograph, so Python can crop and measure.

One call per image, to a model that is **not** the one under test. The
recogniser is a Google model, so measuring these pictures with it would make
the measurement circular -- the same reasoning that keeps Google out of the
generation path, in reverse. This model is never asked whether a shot is a
hit, who it shows, or how good it is: only where the pixels are.

Boxes are normalised to 0-1 of width and height, so they survive a resize.
They are cached in ``world.json``: a box costs money once and then never
again, which is the same bargain the image store makes.
"""

from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

LOCALISATION_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"

# The recogniser's family. Localising with it would measure the picture using
# the very model whose reading of that picture we are trying to assess.
FORBIDDEN_LOCALISATION_PREFIXES = ("google/",)

_BOX = {
    "type": ["object", "null"],
    "properties": {
        "x0": {"type": "number"},
        "y0": {"type": "number"},
        "x1": {"type": "number"},
        "y1": {"type": "number"},
    },
    "required": ["x0", "y0", "x1", "y1"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "subject": dict(_BOX, type="object"),
        "hat": _BOX,
        "armband": _BOX,
        "tshirt": _BOX,
        "other_person": _BOX,
    },
    "required": ["subject", "hat", "armband", "tshirt", "other_person"],
    "additionalProperties": False,
}

PROMPT = """You are locating things in a photograph. Do not judge, score or
describe anything: return boxes only.

The photograph shows one person wearing a coloured baseball cap, a coloured
t-shirt and a coloured elasticated armband on each upper arm. Return, as
normalised coordinates between 0 and 1 where (0,0) is the top-left corner:

- subject: a tight box around that person, head to foot.
- hat: a tight box around the fabric of their cap, or null if no cap is
  visible.
- armband: a tight box around ONE armband -- the more clearly visible of the
  two -- covering only the band itself and none of the arm, or null if no
  armband is visible.
- tshirt: a box on the flat of their chest, well inside the garment's edges
  and clear of any strap, jacket, bag or printed detail, or null if the
  t-shirt is not visible.
- other_person: a tight box around the most prominent OTHER person in the
  picture, if there is one, or null if the subject is alone.

Be tight. A box that includes background will be measured as if the
background were the garment."""


def _assert_allowed(model: str) -> None:
    lowered = model.lower()
    for prefix in FORBIDDEN_LOCALISATION_PREFIXES:
        if lowered.startswith(prefix):
            raise ValueError(
                f"refusing to localise with {model!r}: the recogniser under "
                "test is a Google model, so measuring its inputs with one "
                "would make the measurement circular"
            )


# The model sometimes answers with a page of tabs and newlines instead of
# JSON. Retried rather than accepted, the same way ai_shot_review retries an
# off-schema review, because the alternative is a silently missing box.
ATTEMPTS = 3


async def locate(
    image_data_url: str,
    size: Optional[Tuple[int, int]] = None,
    model: str = LOCALISATION_MODEL,
) -> Dict:
    """Boxes for one image. Costs one API call, or a few if it answers badly.

    ``size`` is the image's pixel dimensions, needed only because the model
    sometimes ignores "normalised" and answers in pixels; given it, those
    answers are converted rather than thrown away.
    """
    import os

    from backend.vision_client import OpenRouterVisionClient
    from backend.vision_client import parse_json_reply

    _assert_allowed(model)
    client = OpenRouterVisionClient(
        api_key=os.environ["OPENROUTER_API_KEY"], model=model
    )
    turns = [{"role": "user", "text": PROMPT, "image_data_url": image_data_url}]

    last_error = None
    for _ in range(ATTEMPTS):
        try:
            reply = await client.complete(turns, SCHEMA)
            if isinstance(reply, str):
                reply = parse_json_reply(reply)
            boxes = {key: _clean(reply.get(key), size) for key in SCHEMA["properties"]}
        except Exception as e:  # noqa: BLE001 - retried, then reported
            last_error = e
            continue
        # A reply with no subject in it is a failed reading, not a picture
        # with nobody in it: every one of these images has a person.
        if boxes["subject"]:
            return boxes
        last_error = ValueError("no subject box in the reply")

    raise last_error or ValueError("localisation failed")


def _clean(
    box: Optional[Dict], size: Optional[Tuple[int, int]] = None
) -> Optional[Dict]:
    """Keep a box only if it is a real, ordered, in-frame rectangle."""
    if not isinstance(box, dict):
        return None
    try:
        values = {k: float(box[k]) for k in ("x0", "y0", "x1", "y1")}
    except (KeyError, TypeError, ValueError):
        return None

    # Answered in pixels rather than in fractions: convert instead of
    # clamping every coordinate to 1.0 and calling the box malformed.
    if size and max(values.values()) > 1.0:
        width, height = size
        values = {
            "x0": values["x0"] / width,
            "x1": values["x1"] / width,
            "y0": values["y0"] / height,
            "y1": values["y1"] / height,
        }

    values = {k: min(1.0, max(0.0, v)) for k, v in values.items()}
    if values["x1"] <= values["x0"] or values["y1"] <= values["y0"]:
        return None
    return values


def centre(box: Dict) -> List[float]:
    return [(box["x0"] + box["x1"]) / 2, (box["y0"] + box["y1"]) / 2]
