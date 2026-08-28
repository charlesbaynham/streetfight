"""Check a drawn venue map against the crop it was supposed to trace.

An image model asked to redraw a map will sometimes trace it and sometimes
quietly compose a plausible-looking one instead. The difference is not obvious
by eye on an unfamiliar city, and it is the difference between a map players
can navigate by and a decoration.

This overlays the marker positions the drawing *should* have on the drawing it
actually has, so the two can be compared directly, and prints the venue snippet
with the real image size filled in.

    uv run python check_venue_map.py --meta OUT/meta.json --drawn drawn.png

Writes `OUT/05_check_overlay.png`: the drawing, dimmed, with a ring and a label
at every expected position. Every ring should land on the matching hand-drawn
label. A ring in open space with its name drawn somewhere else means that
marker moved, and the whole drawing is suspect - a model that moved one usually
moved several.
"""

import argparse
import json
import os

from PIL import Image
from PIL import ImageDraw
from PIL import ImageEnhance
from PIL import ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
COLOURS = {"centre": (0, 90, 220), "landmark": (140, 40, 200), "pub": (220, 20, 20)}


def venue_snippet(meta, width_px):
    b = meta["bounds"]

    def key(s):
        out = "".join(c if c.isalnum() else "_" for c in s.upper())
        return "_".join(x for x in out.split("_") if x)

    lines = [
        f'        "{key(m["name"])}": ({m["lat"]}, {m["lon"]}),'
        for m in meta["markers"]
    ]
    name = meta["name"]
    return f"""{name.upper()} = Venue(
    name="{name.replace("_", " ").title()}",
    map=VenueMap(
        image="{name}",
        width_px={width_px},
        height_px={width_px},
        ref_1=MapReferencePoint(
            x=0, y=0, lat={b["north"]:.6f}, long={b["west"]:.6f}
        ),
        ref_2=MapReferencePoint(
            x={width_px}, y={width_px}, lat={b["south"]:.6f}, long={b["east"]:.6f}
        ),
        corner_width_km={0.115 if width_px >= 2000 else 0.2},
    ),
    landmarks={{
{chr(10).join(lines)}
    }},
)"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--meta", required=True, help="meta.json from build_venue_map.py")
    ap.add_argument("--drawn", required=True, help="the image the model returned")
    ap.add_argument("--out", help="overlay path (default: beside meta.json)")
    args = ap.parse_args()

    meta = json.load(open(args.meta))
    drawn = Image.open(args.drawn).convert("RGB")
    if drawn.width != drawn.height:
        print(
            f"WARNING: {drawn.width}x{drawn.height} is not square. The crop is, "
            "so the model has changed the framing and the georeferencing no "
            "longer holds. Regenerate rather than trusting it."
        )

    side = max(drawn.size)
    canvas = ImageEnhance.Brightness(drawn.resize((side, side))).enhance(1.25)
    d = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(FONT, max(12, side // 70))
    r = max(10, side // 70)

    for m in meta["markers"]:
        x, y = m["x_frac"] * side, m["y_frac"] * side
        c = COLOURS.get(m["kind"], (0, 0, 0))
        d.ellipse([x - r, y - r, x + r, y + r], outline=c, width=max(2, side // 400))
        d.line([(x - r * 1.8, y), (x - r * 0.6, y)], fill=c, width=max(2, side // 500))
        d.line([(x + r * 0.6, y), (x + r * 1.8, y)], fill=c, width=max(2, side // 500))
        tx, ty = x + r * 2.1, y
        anchor = "lm"
        if tx > side * 0.8:
            tx, anchor = x - r * 2.1, "rm"
        bb = d.textbbox((tx, ty), m["name"], font=font, anchor=anchor)
        d.rectangle([bb[0] - 3, bb[1] - 2, bb[2] + 3, bb[3] + 2], fill="white")
        d.text((tx, ty), m["name"], font=font, fill=c, anchor=anchor)

    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.meta)), "05_check_overlay.png"
    )
    canvas.save(out, optimize=True)

    span = 2 * meta["half_span_m"]
    print(f"wrote {out}")
    print(
        f"\ndrawing is {drawn.width}x{drawn.height} for {span:.0f} m "
        f"= {span/drawn.width:.2f} m/px"
    )
    print(
        f"{len(meta['markers'])} rings drawn. Open the overlay: every ring "
        "should sit on\nits own hand-drawn label. If several do not, the model "
        "composed rather\nthan traced - regenerate, do not try to correct it.\n"
    )
    print(venue_snippet(meta, drawn.width))


if __name__ == "__main__":
    main()
