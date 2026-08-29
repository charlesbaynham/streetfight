"""``kit_swatches.png``: the palette as exact hex patches, for the model.

Passed as an input image on every generation alongside the prompt. The prompt
names a colour *and* its hex, but a name drifts and a hex in prose is easy to
approximate; a patch of the actual pixel value is not. Deterministic, free,
and rebuilt from ``PALETTE_HEX`` so it can never fall out of step with the
palette the game scores against.
"""

from pathlib import Path

from PIL import Image
from PIL import ImageDraw

from backend.identity.config import default_scheme
from backend.identity.config import hex_for

SWATCH = 120
GAP = 8
LABEL_H = 34
LEFT = 190


def render(path: Path) -> Path:
    scheme = default_scheme()
    channels = list(scheme.channels.names)
    width = (
        LEFT
        + max(len(scheme.channels.by_name(c).labels) for c in channels) * (SWATCH + GAP)
        + GAP
    )
    height = GAP + len(channels) * (SWATCH + LABEL_H + GAP)

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    for row, channel in enumerate(channels):
        top = GAP + row * (SWATCH + LABEL_H + GAP)
        draw.text((GAP, top + SWATCH // 2), channel.upper(), fill="black")
        for col, colour in enumerate(scheme.channels.by_name(channel).labels):
            left = LEFT + col * (SWATCH + GAP)
            value = hex_for(channel, colour)
            draw.rectangle(
                [left, top, left + SWATCH, top + SWATCH], fill=value, outline="black"
            )
            draw.text((left, top + SWATCH + 4), f"{colour}", fill="black")
            draw.text((left, top + SWATCH + 18), value, fill="black")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
