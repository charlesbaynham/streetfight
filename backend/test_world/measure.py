"""Measure the pictures. Record, never correct.

Nothing here regenerates anything, and nothing here decides anything. A
measurement is reported at a gate and written into ``world.json``; wanting a
different picture means editing the scene description, which changes the
prompt, which changes the hash. That is the only path there is.

The colour maths is CIEDE2000, hand-rolled in about sixty lines rather than
pulled in as a dependency: ``pyproject.toml`` carries no colour-science
library, and one function does not justify adding one.
"""

import math
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from backend.identity.config import hex_for

# Sample the middle of a located garment, not its edges: a box that is a
# little loose still gives a clean reading from its heart.
SAMPLE_INSET = 0.3


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # noqa: E203


def _srgb_to_lab(rgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
    def linear(channel):
        channel /= 255.0
        return (
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )

    r, g, b = (linear(float(c)) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def ciede2000(one: Tuple[int, int, int], two: Tuple[int, int, int]) -> float:
    """Perceptual distance between two sRGB colours."""
    l1, a1, b1 = _srgb_to_lab(one)
    l2, a2, b2 = _srgb_to_lab(two)

    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7))) if c_bar else 0.5
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hue(ap, bp):
        return math.degrees(math.atan2(bp, ap)) % 360 if (ap or bp) else 0.0

    h1p, h2p = hue(a1p, b1), hue(a2p, b2)

    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2)

    lp_bar = (l1 + l2) / 2
    cp_bar = (c1p + c2p) / 2
    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hp_bar = (h1p + h2p + 360) / 2
    else:
        hp_bar = (h1p + h2p - 360) / 2

    t = (
        1
        - 0.17 * math.cos(math.radians(hp_bar - 30))
        + 0.24 * math.cos(math.radians(2 * hp_bar))
        + 0.32 * math.cos(math.radians(3 * hp_bar + 6))
        - 0.20 * math.cos(math.radians(4 * hp_bar - 63))
    )
    d_theta = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cp_bar**7 / (cp_bar**7 + 25**7)) if cp_bar else 0
    sl = 1 + (0.015 * (lp_bar - 50) ** 2) / math.sqrt(20 + (lp_bar - 50) ** 2)
    sc = 1 + 0.045 * cp_bar
    sh = 1 + 0.015 * cp_bar * t
    rt = -rc * math.sin(2 * math.radians(d_theta))

    return math.sqrt(
        (dlp / sl) ** 2
        + (dcp / sc) ** 2
        + (dHp / sh) ** 2
        + rt * (dcp / sc) * (dHp / sh)
    )


def sample(path: Path, box: Dict) -> Optional[Tuple[int, int, int]]:
    """The median colour of the middle of a box, as sRGB."""
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        width, height = image.size
        x0 = box["x0"] + SAMPLE_INSET * (box["x1"] - box["x0"]) / 2
        x1 = box["x1"] - SAMPLE_INSET * (box["x1"] - box["x0"]) / 2
        y0 = box["y0"] + SAMPLE_INSET * (box["y1"] - box["y0"]) / 2
        y1 = box["y1"] - SAMPLE_INSET * (box["y1"] - box["y0"]) / 2
        region = image.crop(
            (
                round(x0 * width),
                round(y0 * height),
                max(round(x1 * width), round(x0 * width) + 1),
                max(round(y1 * height), round(y0 * height) + 1),
            )
        )
        pixels = list(region.getdata())

    if not pixels:
        return None
    # Median per channel: robust to a stray highlight or a shadowed edge in a
    # way that a mean is not.
    return tuple(
        sorted(channel)[len(channel) // 2]
        for channel in zip(*pixels)  # noqa: B905 - py3.9 compatible
    )


def kit_colours(path: Path, boxes: Dict, appearance: Dict) -> List[Dict]:
    """How far each located garment is from the hex it was asked for."""
    readings = []
    for channel, key in (("hat", "hat"), ("armbands", "armband"), ("tshirt", "tshirt")):
        box = boxes.get(key)
        if not box:
            continue
        colour = appearance.get(channel)
        if not colour:
            continue
        got = sample(path, box)
        if got is None:
            continue
        wanted = hex_to_rgb(hex_for(channel, colour))
        readings.append(
            {
                "channel": channel,
                "colour": colour,
                "wanted_hex": hex_for(channel, colour),
                "measured_hex": "#%02X%02X%02X" % got,
                "delta_e": round(ciede2000(got, wanted), 1),
            }
        )
    return readings


def wardrobe_variance(readings: List[Dict]) -> List[Dict]:
    """Players sharing a colour *label* must not share a pixel value.

    The brief is explicit that hats and armbands are ours -- mass-produced, so
    identical on everyone -- while t-shirts are the player's own and vary
    inside the colour's definition. So a spread of zero is a fault on the
    t-shirt and a virtue on the other two, and this reports the spread rather
    than judging it.
    """
    from collections import defaultdict

    groups = defaultdict(list)
    for reading in readings:
        groups[(reading["channel"], reading["colour"])].append(reading)

    out = []
    for (channel, colour), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        colours = [hex_to_rgb(r["measured_hex"]) for r in rows]
        spread = [
            ciede2000(colours[i], colours[j])
            for i in range(len(colours))
            for j in range(i + 1, len(colours))
        ]
        out.append(
            {
                "channel": channel,
                "colour": colour,
                "worn_by": len(rows),
                "mean_pairwise_delta_e": round(sum(spread) / len(spread), 1),
                "max_pairwise_delta_e": round(max(spread), 1),
            }
        )
    return out
