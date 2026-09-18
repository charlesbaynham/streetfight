"""The doodles on a venue map: turning the model's ink into transparency, and
where the renderer puts each one.

The scripts live with the `draw-venue-map` skill rather than in `backend/`,
because they are tooling for making a map and not part of the app - but the
placement rules are what stop a drawing landing on a pub's name, so they get
a test.
"""

import os
import sys

import pytest
from PIL import Image
from PIL import ImageDraw

SCRIPTS = os.path.join(
    os.path.dirname(__file__), "..", ".claude", "skills", "draw-venue-map", "scripts"
)
sys.path.insert(0, os.path.abspath(SCRIPTS))

import doodle_venue_map as doodle  # noqa: E402
import render_venue_map as render  # noqa: E402


def _overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_ink_to_alpha_drops_the_paper_and_recolours_the_ink():
    sheet = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(sheet).line([(20, 20), (180, 180)], fill="black", width=10)

    out = doodle.ink_to_alpha(sheet)

    assert out.mode == "RGBA"
    # Trimmed to the stroke, not the sheet.
    assert out.width <= 172 and out.height <= 172
    r, g, b, a = out.getpixel((out.width // 2, out.height // 2))
    assert (r, g, b) == (0x2F, 0x24, 0x18) and a == 255
    # The paper in the corners is gone entirely, not left white.
    assert out.getpixel((out.width - 1, 0))[3] == 0


def test_ink_to_alpha_refuses_a_blank_sheet():
    with pytest.raises(doodle.DoodleError):
        doodle.ink_to_alpha(Image.new("RGB", (50, 50), "white"))


def test_doodle_is_addressed_by_subject_and_model():
    oak = {"marker": "Royal Oak", "subject": "an oak tree"}
    elm = {"marker": "Royal Oak", "subject": "an elm tree"}
    assert doodle.doodle_id(oak) != doodle.doodle_id(elm)
    assert doodle.doodle_id(oak) != doodle.doodle_id(oak, model="other/model")
    assert doodle.doodle_path("b", oak).startswith(
        os.path.join("b", "doodles", "royal_oak.")
    )


def _sheet_with_a_road(size=600, x=300):
    sheet = render.Sheet(size)
    sheet.rect(render.LAYER_MAP, (0, 0, size, size), render.PAPER)
    sheet.line(render.LAYER_MAP, [(x, 0), (x, size)], 12, render.INK)
    return sheet


def test_doodle_lands_beside_the_pub_off_the_road_and_away_from_the_name():
    sheet = _sheet_with_a_road()
    pub = (300, 300)
    label = (330, 290, 480, 310)  # the name, written to the right of the pub
    taken = [label]
    doodler = render.Doodler(sheet, 600, taken=taken)
    drawing = Image.new("RGBA", (100, 100), (0, 0, 0, 255))

    box = doodler.put(*pub, drawing, b"png", px=80, away_from=label)

    assert box is not None
    assert not _overlaps(box, label)
    assert not (box[0] <= pub[0] <= box[2] and box[1] <= pub[1] <= box[3])
    assert box[2] < 294 or box[0] > 306, "the drawing is across the road"
    assert box[2] <= pub[0], "the drawing should flank the pub opposite its name"
    assert box in taken, "the next doodle must know this one is there"
    assert sheet.ops[render.LAYER_DOODLE][0][0] == "image"


def test_doodle_is_left_off_rather_than_put_over_a_name():
    sheet = _sheet_with_a_road()
    everywhere = [(0, 0, 600, 600)]
    doodler = render.Doodler(sheet, 600, taken=everywhere)

    assert doodler.put(300, 300, Image.new("RGBA", (10, 10)), b"png") is None
    assert sheet.ops[render.LAYER_DOODLE] == []


def test_both_emitters_draw_the_image_primitive():
    sheet = render.Sheet(100)
    sheet.rect(render.LAYER_MAP, (0, 0, 100, 100), render.PAPER)
    drawing = Image.new("RGBA", (10, 10), (0x2F, 0x24, 0x18, 255))
    sheet.image(render.LAYER_DOODLE, (40, 40, 60, 60), drawing, b"\x89PNG")

    raster = render.to_pil(sheet, ss=1)
    assert raster.getpixel((50, 50)) == (0x2F, 0x24, 0x18)
    assert raster.getpixel((10, 10)) == render._rgb(render.PAPER)

    svg = render.to_svg(sheet)
    assert '<image x="40.0" y="40.0" width="20.0" height="20.0"' in svg
    assert 'href="data:image/png;base64,' in svg
