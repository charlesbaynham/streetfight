"""Turn a square generation into the photograph a phone would have taken.

Two jobs, both deterministic given the image and the boxes:

**Put the aim point at the centre.** ``image_processing.draw_aim_marker``
draws the crosshair through the exact middle of the frame, so where the shot
"landed" is decided entirely by how the picture is cropped -- on the target's
torso for a hit, off their shoulder for a near miss, on the bystander for the
bystander case.

**Separate the distance bands.** The generator renders every subject at
roughly the same size however firmly the prompt argues (see
``prompts._street_led_opening``), so the crop is what makes a close shot close
and leaves a distant one distant: crop tight and enlarge for close, less for
mid, not at all for distant. Enlarging afterwards is what a phone's digital
zoom does too, softness included, so the result is honest rather than a
cheat.
"""

from pathlib import Path
from typing import Dict
from typing import Optional
from typing import Tuple

# What a real shot looks like: MyWebcam asks the camera for 2048x1080, and
# tests/fixtures/shot_replay carries exactly that, both ways up.
LONG_EDGE = 2048
SHORT_EDGE = 1080

# How much of the source each band keeps before being enlarged back to size.
# Chosen so the ordering close > mid > distant survives a generator that
# renders every subject at about a third of the frame.
BAND_ZOOM = {"close": 0.55, "mid": 0.78, "distant": 1.0}

# How far off the shoulder a near miss lands, as a fraction of frame width.
# The plan's 8-10%: far enough to be a miss, close enough to be a plausible
# aim rather than a photograph of the pavement.
MISS_OFFSET = 0.09


def aim_point(scene: Dict, boxes: Dict) -> Tuple[float, float]:
    """Where the crosshair must fall, normalised, for this scene's verdict."""
    subject = boxes.get("subject")
    if not subject:
        raise ValueError("no subject box: this shot has not been localised")
    height = subject["y1"] - subject["y0"]
    middle = (subject["x0"] + subject["x1"]) / 2

    if scene["intended_result"] == "bystander":
        other = boxes.get("other_person")
        if other:
            return (
                (other["x0"] + other["x1"]) / 2,
                other["y0"] + 0.35 * (other["y1"] - other["y0"]),
            )
        # No second person was rendered, so the scene cannot mean what it
        # says. Aim off the target rather than silently on them.
        return _past_the_shoulder(subject, middle, height)

    if scene["intended_result"] == "miss":
        return _past_the_shoulder(subject, middle, height)

    # A hit: the middle of the chest, which is also where the garments are.
    return middle, subject["y0"] + 0.35 * height


def _past_the_shoulder(subject, middle, height):
    """Just outside the wider side, at shoulder height."""
    room_left = subject["x0"]
    room_right = 1.0 - subject["x1"]
    shoulder = subject["y0"] + 0.22 * height
    if room_right >= room_left:
        return min(1.0, subject["x1"] + MISS_OFFSET), shoulder
    return max(0.0, subject["x0"] - MISS_OFFSET), shoulder


def crop_box(
    size: Tuple[int, int], aim: Tuple[float, float], band: str, portrait: bool
) -> Tuple[int, int, int, int]:
    """The pixel rectangle to cut, centred on the aim point where it can be.

    Clamped to the image, so an aim point near an edge slides the rectangle
    rather than shrinking it -- the crosshair then sits off-centre, which is
    what the caller checks and reports rather than something to hide.
    """
    source_width, source_height = size
    zoom = BAND_ZOOM[band]
    ratio = (SHORT_EDGE / LONG_EDGE) if portrait else (LONG_EDGE / SHORT_EDGE)

    height = source_height * zoom
    width = height * ratio
    if width > source_width:
        width = source_width * zoom
        height = width / ratio

    # A crop is where the phone was pointed, so it has to be able to point
    # there. A subject near an edge leaves less room than the band would like,
    # and taking the band's width anyway puts the crosshair on the pavement
    # beside them -- which stops the fixture testing what it says it tests.
    # Zooming in instead is what somebody aiming at them would really do.
    room_x = 2 * min(aim[0], 1 - aim[0]) * source_width
    room_y = 2 * min(aim[1], 1 - aim[1]) * source_height
    if room_x < width or room_y < height:
        scale = min(room_x / width, room_y / height)
        width, height = width * scale, height * scale

    left = aim[0] * source_width - width / 2
    top = aim[1] * source_height - height / 2
    left = max(0, min(source_width - width, left))
    top = max(0, min(source_height - height, top))
    return (round(left), round(top), round(left + width), round(top + height))


def render(
    source: Path, out: Path, scene: Dict, boxes: Dict, quality: int = 88
) -> Dict:
    """Write the cropped photograph, and say what the crop actually did."""
    from PIL import Image

    # A distant shot is a picture of a street and a near one is a picture of a
    # person, so they are held the way somebody would really hold the phone.
    portrait = scene["distance_band"] != "distant"

    with Image.open(source) as image:
        image = image.convert("RGB")
        source_size = image.size
        aim = aim_point(scene, boxes)
        box = crop_box(source_size, aim, scene["distance_band"], portrait)
        cropped = image.crop(box)
        target = (SHORT_EDGE, LONG_EDGE) if portrait else (LONG_EDGE, SHORT_EDGE)
        cropped = cropped.resize(target, Image.LANCZOS)
        out.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(out, "JPEG", quality=quality)

    kept = (box[3] - box[1]) / source_size[1]
    return {
        "aim_point": [round(aim[0], 4), round(aim[1], 4)],
        "crop_box": list(box),
        "size": list(target),
        # How much of the source's height survived, against what the band
        # asked for. A subject near an edge forces a tighter crop than the
        # band wanted, and that is worth seeing rather than inferring.
        "kept_height": round(kept, 3),
        "band_wanted": BAND_ZOOM[scene["distance_band"]],
        "crosshair_offset": _offset(box, aim, source_size),
    }


def _offset(box, aim, size) -> Optional[float]:
    """How far the crosshair ended up from the aim point, in frame widths.

    Zero unless the rectangle had to be slid away from an edge. Recorded,
    never corrected: an aim point the crop could not centre is a fact about
    the picture.
    """
    width, height = size
    centre_x = (box[0] + box[2]) / 2 / width
    centre_y = (box[1] + box[3]) / 2 / height
    return round(((centre_x - aim[0]) ** 2 + (centre_y - aim[1]) ** 2) ** 0.5, 4)
