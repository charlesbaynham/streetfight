"""Draw a venue's map in the Kingston hand-drawn style, from OSM geometry.

The image models could not do this. Asked to trace, they resynthesise: every
attempt got either the roads or the scale wrong, and the one good Westminster
map was luck that could not be repeated or corrected. Nothing in that kind of
model preserves metric geometry, so it was never going to be a question of
finding a better one.

So don't ask. `build_venue_map.py` already computes every road polyline, the
water, the parks and each marker's position in image space - that is what
draws the skeleton - and a hand-drawn look is a rendering style rather than a
creative act. This draws the same geometry with a wobbly pen and a
handwriting font, which is exact by construction and reproducible: rerun it
when the pub list changes and the map follows.

What it cannot give you is the doodles. The cartwheel beside Wheelwrights
Arms is the charm of the Kingston map and no renderer will invent one; ink
them onto a printed copy if you want them.

Usage:

    uv run python render_venue_map.py \\
        --bundle docs/venue_map_westminster \\
        --out react-ui/src/images/map_westminster.jpg \\
        --title WESTMINSTER

Reads `meta.json` and `osm_features.json.gz` from the bundle, so it needs no
network and costs nothing to re-run. Both are written by `build_venue_map.py`.
"""

import argparse
import gzip
import json
import math
import os
import random
import sys

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFilter
from PIL import ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_venue_map import MAJOR  # noqa: E402
from build_venue_map import WIDTHS  # noqa: E402
from build_venue_map import Box  # noqa: E402
from build_venue_map import rings  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "fonts")
HAND = os.path.join(FONTS, "PatrickHand-Regular.ttf")
# The title is "block capitals", so a bold sans outlined, not a script face:
# Caveat's capitals are lovely in a sentence and unreadable at 130px apart.
TITLE_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

OUT_PX = 2000
SS = 3  # supersample: PIL does not antialias lines, so draw big and shrink

INK = 0
PAPER = 255

# All in output pixels; multiplied by SS when drawing.
PEN = 1.7  # one nib width - the whole map is drawn at this weight
WOBBLE_STEP = 7.0  # resample spacing along a line before displacing it
WOBBLE_AMP = 3.2  # how far the hand strays from true, in pixels


# --------------------------------------------------------------------------
# A wobbly pen
# --------------------------------------------------------------------------


def _noise(seed, n, octaves=3):
    """Smooth 1-D noise in roughly [-1, 1], deterministic in `seed`.

    Sines rather than a random walk: a walk drifts, and a road that drifts is
    a road in the wrong place. This stays near zero, so the line wanders about
    its true course without leaving it.
    """
    rnd = random.Random(seed)
    waves = [(rnd.uniform(0, math.tau), rnd.uniform(0.6, 1.4)) for _ in range(octaves)]
    out = []
    for i in range(n):
        v = 0.0
        for k, (phase, scale) in enumerate(waves):
            v += math.sin(phase + i * 0.3 * (k + 1) * scale) / (k + 1)
        out.append(v / 1.6)
    return out


def resample(pts, step):
    """Walk a polyline, emitting a point every `step` pixels."""
    if len(pts) < 2:
        return list(pts)
    out = [pts[0]]
    carry = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-9:
            continue
        t = step - carry
        while t <= seg:
            out.append((x0 + (x1 - x0) * t / seg, y0 + (y1 - y0) * t / seg))
            t += step
        carry = (carry + seg) % step
    out.append(pts[-1])
    return out


def freehand(pts, seed, amp=WOBBLE_AMP, step=WOBBLE_STEP, ss=SS):
    """Displace a polyline sideways by smooth noise, as an unsteady hand does.

    The ends are pinned: a road whose end has wandered no longer meets the one
    it joins, and open junctions are most of what makes the drawing readable.
    """
    pts = resample(pts, step * ss)
    n = len(pts)
    if n < 3:
        return pts
    noise = _noise(seed, n)
    out = []
    for i, (x, y) in enumerate(pts):
        if i == 0:
            dx, dy = pts[1][0] - x, pts[1][1] - y
        elif i == n - 1:
            dx, dy = x - pts[-2][0], y - pts[-2][1]
        else:
            dx = pts[i + 1][0] - pts[i - 1][0]
            dy = pts[i + 1][1] - pts[i - 1][1]
        length = math.hypot(dx, dy) or 1.0
        # Fade the wobble in and out so the endpoints stay put.
        taper = min(1.0, 4.0 * min(i, n - 1 - i) / max(1, n - 1))
        off = noise[i] * amp * ss * taper
        out.append((x - dy / length * off, y + dx / length * off))
    return out


# --------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------


def bezier(p0, p1, p2, n=24):
    return [
        (
            (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1],
        )
        for t in (i / n for i in range(n + 1))
    ]


class Hand:
    """Writes names on the map and points at what they belong to.

    Kingston's labels sit in white space with a curved arrow reaching back to
    the pub, which is what lets nineteen of them share one sheet: the name
    goes wherever there is room and the arrow keeps it honest.
    """

    def __init__(self, draw, size, ss, pen, taken=()):
        self.d, self.size, self.ss, self.pen = draw, size, ss, pen
        self.font = ImageFont.truetype(HAND, int(30 * ss))
        # Whatever is already written on the map - the street names, the title
        # - counts as occupied. A name's knockout box is opaque, so a label
        # placed over one does not overlap it, it deletes the middle of it.
        self.placed = list(taken)

    def _free(self, box):
        return not any(
            box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3]
            for b in self.placed
        )

    def _box_at(self, x, y, text, anchor):
        b = self.d.textbbox((x, y), text, font=self.font, anchor=anchor)
        pad = 5 * self.ss
        return (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)

    def put(self, x, y, text):
        """Place `text` near (x, y), then draw an arrow from it to the point."""
        gap, step = 18 * self.ss, 34 * self.ss
        margin = 14 * self.ss
        best = None
        for ring in range(0, 9):
            for side in ("r", "l"):
                for sign in (0, -1, 1) if ring else (0,):
                    anchor = "lm" if side == "r" else "rm"
                    tx = x + gap if side == "r" else x - gap
                    ty = y + sign * ring * step
                    box = self._box_at(tx, ty, text, anchor)
                    if not (
                        margin < box[0]
                        and box[2] < self.size - margin
                        and margin < box[1]
                        and box[3] < self.size - margin
                    ):
                        continue
                    if self._free(box):
                        best = (tx, ty, anchor, box)
                        break
                if best:
                    break
            if best:
                break
        if not best:  # give up gracefully rather than drop the name
            best = (x + gap, y, "lm", self._box_at(x + gap, y, text, "lm"))

        tx, ty, anchor, box = best
        self.placed.append(box)
        # Knock the paper out behind the words so roads do not run through
        # them, then write on top.
        self.d.rectangle(list(box), fill=PAPER)
        self.d.text((tx, ty), text, font=self.font, fill=INK, anchor=anchor)

        start = (box[0], ty) if anchor == "lm" else (box[2], ty)
        self._arrow(start, (x, y))

    def _arrow(self, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        dist = math.hypot(dx, dy)
        if dist < 6 * self.ss:
            return
        # Stop just short, so the nib does not sit on top of the thing.
        back = min(9 * self.ss, dist * 0.3)
        end = (end[0] - dx / dist * back, end[1] - dy / dist * back)
        dx, dy = end[0] - start[0], end[1] - start[1]
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        bow = 0.22
        ctrl = (mid[0] - dy * bow, mid[1] + dx * bow)
        curve = bezier(start, ctrl, end)
        w = max(1, int(self.pen * self.ss))
        self.d.line(curve, fill=INK, width=w, joint="curve")

        # A two-stroke head, angled off the direction the curve arrives from.
        ax, ay = end[0] - curve[-2][0], end[1] - curve[-2][1]
        a = math.atan2(ay, ax)
        size = 11 * self.ss
        for turn in (2.5, -2.5):
            self.d.line(
                [
                    end,
                    (
                        end[0] + size * math.cos(a + turn),
                        end[1] + size * math.sin(a + turn),
                    ),
                ],
                fill=INK,
                width=w,
            )


def text_along(img, x, y, angle, text, font, ss):
    """Write a street name along the line of its road.

    Rotating a strip grows its bounding box, and the corners it grows into are
    not part of the label. Carry a mask of the strip's own area so the paste
    knocks the paper out under the words alone - pasting the whole rotated box
    put white triangles across the roads either side.
    """
    tmp = Image.new("L", (1, 1))
    box = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    pad = 6 * ss
    w, h = int(box[2] - box[0] + 2 * pad), int(box[3] - box[1] + 2 * pad)
    strip = Image.new("L", (w, h), PAPER)
    ImageDraw.Draw(strip).text((pad - box[0], pad - box[1]), text, font=font, fill=INK)
    area = Image.new("L", (w, h), 255)
    deg = -math.degrees(angle)
    if deg > 90 or deg < -90:  # never write upside down
        deg += 180
    spin = dict(expand=True, resample=Image.BICUBIC)
    strip = strip.rotate(deg, fillcolor=PAPER, **spin)
    area = area.rotate(deg, fillcolor=0, **spin)
    pos = (int(x - strip.width / 2), int(y - strip.height / 2))
    img.paste(strip, pos, area)
    return (pos[0], pos[1], pos[0] + strip.width, pos[1] + strip.height)


# --------------------------------------------------------------------------
# The drawing
# --------------------------------------------------------------------------


def draw_roads(d, els, box, size, ss):
    """Roads as a pair of wobbly edges with white between them.

    Drawn as a casing rather than two offset polylines: stroke every road
    black at corridor+2 nibs, then stroke every road white at corridor. The
    second pass clears the first's edges wherever roads meet, so junctions
    come out open the way a hand draws them, with no junction geometry to get
    wrong.
    """
    roads = [
        e
        for e in els
        if e.get("tags", {}).get("highway") in WIDTHS and e.get("geometry")
    ]
    prepared = []
    for el in roads:
        pts = [box.project(q["lat"], q["lon"], size) for q in el["geometry"]]
        if len(pts) < 2:
            continue
        prepared.append(
            (freehand(pts, el.get("id", 0), ss=ss), WIDTHS[el["tags"]["highway"]] * ss)
        )
    nib = max(1, int(PEN * ss))
    for pts, w in prepared:
        d.line(pts, fill=INK, width=int(w + 2 * nib), joint="curve")
    for pts, w in prepared:
        d.line(pts, fill=PAPER, width=int(w), joint="curve")
    return roads


def draw_water(d, els, box, size, ss):
    """Banks only, white inside, with a couple of squiggles to say it is water."""
    nib = max(1, int(PEN * ss))
    banks = []
    for el in els:
        t = el.get("tags", {})
        if t.get("natural") == "water" or t.get("waterway") == "riverbank":
            for ring in rings(el):
                pts = [box.project(q["lat"], q["lon"], size) for q in ring]
                if len(pts) > 1:
                    bank = freehand(pts, el.get("id", 1), amp=2.6, ss=ss)
                    d.line(bank, fill=INK, width=nib, joint="curve")
                    banks.append(bank)
    if not banks:
        return
    longest = max(banks, key=len)
    rnd = random.Random(7)
    for i in range(len(longest) // 9, len(longest), max(9, len(longest) // 7)):
        x, y = longest[i]
        run = 26 * ss * rnd.uniform(0.6, 1.2)
        wig = [(x + run * t / 6, y + 4 * ss * math.sin(t * 1.6)) for t in range(7)]
        d.line(wig, fill=INK, width=nib, joint="curve")


def draw_parks(d, els, box, size, ss):
    nib = max(1, int(PEN * ss))
    for el in els:
        if el.get("tags", {}).get("leisure") != "park":
            continue
        for ring in rings(el):
            pts = [box.project(q["lat"], q["lon"], size) for q in ring]
            if len(pts) >= 3:
                d.line(
                    freehand(pts + [pts[0]], el.get("id", 2), amp=2.2, ss=ss),
                    fill=INK,
                    width=nib,
                    joint="curve",
                )


def draw_street_names(img, roads, box, size, ss, limit=14):
    """Name a handful of the main roads, written along the road.

    Longest first, and a name that would land on one already written is
    dropped: two street names on top of each other is worse than one.
    """
    font = ImageFont.truetype(HAND, int(24 * ss))
    best = {}
    for el in roads:
        t = el["tags"]
        if t.get("highway") not in MAJOR or not t.get("name"):
            continue
        g = el["geometry"]
        span = abs(g[0]["lat"] - g[-1]["lat"]) + abs(g[0]["lon"] - g[-1]["lon"])
        if span > best.get(t["name"], (0, None))[0]:
            best[t["name"]] = (span, g)
    edge = 110 * ss
    written = []
    for name, (_, g) in sorted(best.items(), key=lambda kv: -kv[1][0]):
        if len(written) >= limit:
            break
        i = len(g) // 2
        x, y = box.project(g[i]["lat"], g[i]["lon"], size)
        if not (edge < x < size - edge and edge < y < size - edge):
            continue
        j = max(0, i - 2)
        k = min(len(g) - 1, i + 2)
        x0, y0 = box.project(g[j]["lat"], g[j]["lon"], size)
        x1, y1 = box.project(g[k]["lat"], g[k]["lon"], size)
        guess = (x - 90 * ss, y - 24 * ss, x + 90 * ss, y + 24 * ss)
        if any(
            guess[0] < b[2] and b[0] < guess[2] and guess[1] < b[3] and b[1] < guess[3]
            for b in written
        ):
            continue
        written.append(
            text_along(img, x, y, math.atan2(y1 - y0, x1 - x0), name, font, ss)
        )
    return written


def draw_title(img, text, size, ss):
    """Outlined block capitals across the top, each letter set slightly askew.

    Each letter is drawn into its own cell so it can be tilted, and the cell
    is pasted through a mask of its own ink. Pasting the cell itself instead
    would be wrong twice over: a cell wide enough to hold a tilted glyph is
    wider than the glyph advances, so every letter would rub out the one
    before it, and the paper inside an outlined letter would rub out whatever
    the title is sitting on.
    """
    font = ImageFont.truetype(TITLE_FONT, int(132 * ss))
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    nib = max(1, int(PEN * ss))
    widths = [tmp.textlength(ch, font=font) for ch in text]
    gap = 10 * ss
    total = sum(widths) + gap * (len(text) - 1)
    x = (size - total) / 2
    pad = 26 * ss
    halo = 1 + 2 * max(1, int(2 * ss))  # MaxFilter wants an odd window
    extent = None
    rnd = random.Random(11)
    for ch, w in zip(text, widths):
        cell = Image.new("L", (int(w + 2 * pad), int(190 * ss)), PAPER)
        ImageDraw.Draw(cell).text(
            (pad, pad),
            ch,
            font=font,
            fill=PAPER,
            stroke_width=nib,
            stroke_fill=INK,
        )
        cell = cell.rotate(
            rnd.uniform(-3.0, 3.0),
            expand=True,
            fillcolor=PAPER,
            resample=Image.BICUBIC,
        )
        # Ink is dark, paper is light: invert to get "where to draw".
        ink = cell.point(lambda v: 255 - v)
        pos = (int(x - pad), int(46 * ss + rnd.uniform(-7, 7) * ss))
        # Clear a little paper around each letter first, so the roads stop at
        # the title rather than running through the words, then lay the ink in.
        img.paste(PAPER, pos, ink.filter(ImageFilter.MaxFilter(halo)))
        img.paste(INK, pos, ink)
        here = (pos[0], pos[1], pos[0] + cell.width, pos[1] + cell.height)
        extent = (
            here
            if extent is None
            else (
                min(extent[0], here[0]),
                min(extent[1], here[1]),
                max(extent[2], here[2]),
                max(extent[3], here[3]),
            )
        )
        x += w + gap
    return extent


def render(meta, els, out_path, size=OUT_PX, ss=SS, title=None):
    box = Box(meta["centre"][0], meta["centre"][1], meta["half_span_m"])
    S = size * ss
    img = Image.new("L", (S, S), PAPER)
    d = ImageDraw.Draw(img)

    draw_parks(d, els, box, S, ss)
    draw_water(d, els, box, S, ss)
    roads = draw_roads(d, els, box, S, ss)
    taken = draw_street_names(img, roads, box, S, ss)

    if title:
        taken.append(draw_title(img, title, S, ss))

    d = ImageDraw.Draw(img)
    hand = Hand(d, S, ss, PEN, taken=taken)
    # Landmarks first: they are the things everyone navigates by, so they get
    # the good positions when the pubs crowd them.
    markers = sorted(meta["markers"], key=lambda m: m["kind"] != "landmark")
    for m in markers:
        x, y = box.project(m["lat"], m["lon"], S)
        hand.put(x, y, m["name"])

    img.resize((size, size), Image.LANCZOS).convert("RGB").save(
        out_path, quality=92, optimize=True
    )
    return size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", required=True, help="the build_venue_map.py out dir")
    ap.add_argument("--out", required=True, help="image to write")
    ap.add_argument("--title", default=None, help="title across the top")
    ap.add_argument("--size", type=int, default=OUT_PX)
    ap.add_argument("--supersample", type=int, default=SS)
    args = ap.parse_args()

    meta = json.load(open(os.path.join(args.bundle, "meta.json")))
    feat = os.path.join(args.bundle, "osm_features.json.gz")
    if not os.path.exists(feat):
        raise SystemExit(
            f"{feat} is missing - run build_venue_map.py for this venue first; "
            "it caches the OSM features this draws from."
        )
    with gzip.open(feat, "rt") as fh:
        els = json.load(fh)

    size = render(
        meta,
        els,
        args.out,
        size=args.size,
        ss=args.supersample,
        title=args.title,
    )
    print(f"wrote {args.out}  {size} x {size}")
    print(f"  {len(meta['markers'])} labelled markers, {len(els)} OSM features")
    print(
        "  the venue's reference points are this crop's corners:\n"
        f"    ref_1 x=0 y=0        lat={meta['bounds']['north']:.6f} "
        f"long={meta['bounds']['west']:.6f}\n"
        f"    ref_2 x={size} y={size}  lat={meta['bounds']['south']:.6f} "
        f"long={meta['bounds']['east']:.6f}"
    )


if __name__ == "__main__":
    main()
