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

## Three layers

The drawing is built in three layers, which stack to make the whole map:

    map            roads, water, parks - and a dot at every pub
    doodles        the little drawings beside the pubs (see below)
    handwriting    every word on the sheet, and the arrows that point at things

They are written out separately as SVG so any one can be replaced without
touching the others: re-letter the `.hand.svg`, keep the `.map.svg` as it is,
and the two still line up because all three are drawn in one coordinate
space. Each layer is a `<g>` in the combined file and the only thing in its
own file, so stacking map, doodles, handwriting reproduces the whole exactly.
The groups carry Inkscape's layer attributes, so the combined file opens
there as three layers, and inside them the things somebody would move are
groups with ids: `pubs` (one `pub-<name>` circle each) on the map layer,
and one `doodle-<name>` group per drawing. The pub dots are on the *map*
layer rather than with the arrows because the arrows are what gets redrawn,
and whoever redraws them needs the sheet to still say where each pub is.

## The doodles

The cartwheel beside Wheelwrights Arms is the charm of the Kingston map, and
it is the one thing here an image model *can* do: a doodle carries no
geometry to get wrong. `doodle_venue_map.py` asks Gemini for one small pen
sketch per pub - the subject is written in the bundle's `doodles.json` - on
plain white, and turns the white into transparency. This file then decides
where each goes: beside its pub, on the far side from the name, in the
emptiest patch of paper within reach, never over a label and never over the
point the arrow is aimed at - unless the manifest pins it, which is for a
drawing that *is* the place (the Palace along its own riverbank). The model
never sees the map, so it cannot move anything on it.

The arrows live with the handwriting rather than the map because they belong
to the words: where a name goes is decided by what room is left, and the
arrow is what keeps it honest about which pub it means. Re-letter the layer
and the arrows are yours to redraw with it.

The words are real `<text>` in a real font - embedded in the file, so it
renders the same anywhere - rather than outlines, so they can be edited as
text too.

## Why a display list

Everything is drawn into `Sheet`, a list of primitives in output-pixel
coordinates, and only then emitted: to PIL for the raster the app and the
poster need, and to SVG for the layers. One set of drawing code and two
backends, so the raster and the vector cannot disagree about where anything
is.

Usage:

    uv run python render_venue_map.py \
        --bundle docs/venue_map_westminster \
        --out react-ui/src/images/map_westminster.jpg \
        --title WESTMINSTER

writes the raster at `--out` and, beside it, `map_westminster.svg`,
`map_westminster.map.svg`, `map_westminster.doodles.svg` and
`map_westminster.hand.svg`. `--no-svg` skips those.

Reads `meta.json` and `osm_features.json.gz` from the bundle, so it needs no
network and costs nothing to re-run. Both are written by `build_venue_map.py`.
The doodles come from the bundle too (`doodles.json` and the `doodles/`
directory `doodle_venue_map.py` fills); a listed doodle that has not been
drawn yet is named and left off, and a bundle with no `doodles.json` renders
as it always did.
"""

import argparse
import base64
import gzip
import hashlib
import json
import math
import os
import random
import re
import sys
from xml.sax.saxutils import escape

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_venue_map import MAJOR  # noqa: E402
from build_venue_map import WIDTHS  # noqa: E402
from build_venue_map import Box  # noqa: E402
from build_venue_map import rings  # noqa: E402
from doodle_venue_map import DOODLE_PX  # noqa: E402
from doodle_venue_map import doodle_name  # noqa: E402
from doodle_venue_map import doodle_path  # noqa: E402
from doodle_venue_map import load_manifest  # noqa: E402
from doodle_venue_map import slug  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "fonts")

# One face for the whole sheet, titles included. A second, heavier face for
# the title would be a computer font sitting on a hand-drawn map, and it would
# be embedded in every SVG: DejaVu Sans Bold is 709 KB against this one's 57.
FACE = os.path.join(FONTS, "PatrickHand-Regular.ttf")
FAMILY = "VenueHand"

LAYER_MAP = "map"
LAYER_DOODLE = "doodles"
LAYER_HAND = "handwriting"
LAYERS = (LAYER_MAP, LAYER_DOODLE, LAYER_HAND)

OUT_PX = 2000
SS = 3  # supersample: PIL does not antialias lines, so draw big and shrink

# Sepia ink rather than black, to sit on the paper rather than on top of it.
# 12.3:1 against PAPER, so it is still well past AAA on a phone in the dark
# and at A3 - which is the constraint, not the look.
INK = "#2f2418"
PAPER = "#f2e7d0"  # aged paper; the road corridors are this too, not white
WATER = "#a9c6d6"
PARK = "#c9d7ab"

# All in output pixels.
PEN = 1.7  # one nib width - the whole map is drawn at this weight
WOBBLE_STEP = 7.0  # resample spacing along a line before displacing it
WOBBLE_AMP = 3.2  # how far the hand strays from true, in pixels

LABEL_PX = 30
STREET_PX = 24
TITLE_PX = 150


def _font(px):
    return ImageFont.truetype(FACE, max(1, int(round(px))))


def _measure():
    return ImageDraw.Draw(Image.new("L", (1, 1)))


# --------------------------------------------------------------------------
# The display list
# --------------------------------------------------------------------------


class Sheet:
    """Primitives in output-pixel coordinates, tagged by layer.

    Held rather than drawn, so one list can go to two backends. Nothing here
    knows about supersampling or about SVG; the emitters do.
    """

    def __init__(self, size):
        self.size = size
        self.ops = {name: [] for name in LAYERS}

    def line(self, layer, pts, width, colour=INK):
        if len(pts) > 1:
            self.ops[layer].append(("line", list(pts), float(width), colour))

    def rect(self, layer, box, fill):
        self.ops[layer].append(("rect", tuple(box), fill))

    def poly(self, layer, pts, fill):
        """A filled area, with no outline - the wobbly pen draws that after.

        Keeping the two apart is what makes the colour look laid on by hand:
        the fill follows the true edge and the line wobbles about it, so the
        ink does not quite stay inside the colour.
        """
        if len(pts) > 2:
            self.ops[layer].append(("poly", list(pts), fill))

    def dot(self, layer, x, y, r, colour=INK):
        self.ops[layer].append(("dot", float(x), float(y), float(r), colour))

    def image(self, layer, box, img, png):
        """A transparent drawing fitted inside `box`, aspect kept.

        Carries both the decoded image (for the raster) and the PNG bytes it
        came from (for the SVG, which embeds them as they are).
        """
        self.ops[layer].append(("image", tuple(box), img, png))

    def group(self, layer, name, ops):
        """Primitives that belong together, named so an editor can grab them.

        Drawn exactly as if they were listed in place; only the SVG shows the
        grouping, as a `<g id="name">`.
        """
        self.ops[layer].append(("group", name, list(ops)))

    def grouped(self, layer, name):
        """Draw into a group: `with sheet.grouped(layer, "pubs"): sheet.dot(...)`."""
        return _Grouped(self, layer, name)

    def text(
        self,
        layer,
        x,
        y,
        text,
        px=LABEL_PX,
        anchor="lm",
        fill=INK,
        stroke=None,
        stroke_width=0.0,
        rotate=0.0,
    ):
        self.ops[layer].append(
            (
                "text",
                float(x),
                float(y),
                text,
                float(px),
                anchor,
                fill,
                stroke,
                float(stroke_width),
                float(rotate),
            )
        )


class _Grouped:
    def __init__(self, sheet, layer, name):
        self.sheet, self.layer, self.name = sheet, layer, name

    def __enter__(self):
        self.mark = len(self.sheet.ops[self.layer])

    def __exit__(self, *exc):
        ops, mark = self.sheet.ops[self.layer], self.mark
        self.sheet.ops[self.layer] = ops[:mark]
        self.sheet.group(self.layer, self.name, ops[mark:])


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


def freehand(pts, seed, amp=WOBBLE_AMP, step=WOBBLE_STEP):
    """Displace a polyline sideways by smooth noise, as an unsteady hand does.

    The ends are pinned: a road whose end has wandered no longer meets the one
    it joins, and open junctions are most of what makes the drawing readable.
    """
    pts = resample(pts, step)
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
        off = noise[i] * amp * taper
        out.append((x - dy / length * off, y + dx / length * off))
    return out


# --------------------------------------------------------------------------
# Areas
# --------------------------------------------------------------------------


def _same(a, b, eps=1e-9):
    return abs(a["lat"] - b["lat"]) < eps and abs(a["lon"] - b["lon"]) < eps


def closed_rings(el):
    """Rings that can actually be filled.

    Every way Overpass returns here is already closed, but a multipolygon
    relation arrives as its member ways, each an open arc that ends where the
    next begins - so `rings()` alone yields nothing fillable, and closing an
    arc by joining its own two ends draws a chord across the map. The Thames
    is one ring split over about thirty members; chained head-to-tail it
    closes on itself, and the part outside the crop is clipped off afterwards.

    (`build_venue_map.py` gets the same result by flooding a bitmap from a
    seed in midstream. That cannot be done to a vector, and it does not need
    to be: this is the geometry the flood was recovering.)
    """
    parts = [list(r) for r in rings(el) if len(r) > 1]
    if el["type"] != "relation":
        return parts

    out, pending = [], parts
    while pending:
        ring = pending.pop(0)
        joined = True
        while joined and not _same(ring[0], ring[-1]):
            joined = False
            for i, part in enumerate(pending):
                if _same(ring[-1], part[0]):
                    ring = ring + part[1:]
                elif _same(ring[-1], part[-1]):
                    ring = ring + part[-2::-1]
                elif _same(ring[0], part[-1]):
                    ring = part[:-1] + ring
                elif _same(ring[0], part[0]):
                    ring = part[:0:-1] + ring
                else:
                    continue
                pending.pop(i)
                joined = True
                break
        out.append(ring)
    return out


def clip_to_box(poly, size):
    """Sutherland-Hodgman against the sheet.

    The Thames ring runs miles past the crop in both directions. Clipping it
    keeps the SVG to the part anybody can see, rather than carrying thousands
    of points off the page.
    """

    def inside(p, edge):
        return (p[0] >= 0, p[0] <= size, p[1] >= 0, p[1] <= size)[edge]

    def cut(a, b, edge):
        if edge < 2:
            xe = 0.0 if edge == 0 else float(size)
            t = (xe - a[0]) / (b[0] - a[0])
            return (xe, a[1] + (b[1] - a[1]) * t)
        ye = 0.0 if edge == 2 else float(size)
        t = (ye - a[1]) / (b[1] - a[1])
        return (a[0] + (b[0] - a[0]) * t, ye)

    out = list(poly)
    for edge in range(4):
        if not out:
            return []
        clipped, out = out, []
        for i, cur in enumerate(clipped):
            prev = clipped[i - 1]
            if inside(cur, edge):
                if not inside(prev, edge):
                    out.append(cut(prev, cur, edge))
                out.append(cur)
            elif inside(prev, edge):
                out.append(cut(prev, cur, edge))
    return out


def edge_runs(poly, size, eps=0.75):
    """Split a clipped ring into the runs that are real edges, not the frame.

    Clipping introduces segments that run along the sheet's border. They bound
    the colour but they are not banks or railings, and inking them draws a box
    round the map.
    """

    def on_frame(p):
        return (
            p[0] <= eps,
            p[0] >= size - eps,
            p[1] <= eps,
            p[1] >= size - eps,
        )

    runs, run = [], []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if any(x and y for x, y in zip(on_frame(a), on_frame(b))):
            if len(run) > 1:
                runs.append(run)
            run = []
        else:
            run = (run or [a]) + [b]
    if len(run) > 1:
        runs.append(run)
    return runs


def _area(poly):
    total = 0.0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2


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

    def __init__(self, sheet, size, taken=()):
        self.sheet, self.size = sheet, size
        self.font = _font(LABEL_PX)
        self.measure = _measure()
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
        b = self.measure.textbbox((x, y), text, font=self.font, anchor=anchor)
        pad = 5
        return (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)

    def put(self, x, y, text):
        """Place `text` near (x, y), then draw an arrow from it to the point."""
        # The gap has to clear the arrowhead, or the arrow is all head and
        # reads as a stray caret beside the name. The knockout box's own
        # padding comes off it too, so the shaft is `gap` minus that.
        gap, step, margin = 40, 34, 14
        best = None
        for ring in range(0, 9):
            for side in ("r", "l"):
                for sign in (0, -1, 1) if ring else (0,):
                    anchor = "lm" if side == "r" else "rm"
                    tx = x + gap if side == "r" else x - gap
                    ty = y + sign * ring * step
                    box = self._box_at(tx, ty, text, anchor)
                    inside = (
                        margin < box[0]
                        and box[2] < self.size - margin
                        and margin < box[1]
                        and box[3] < self.size - margin
                    )
                    if inside and self._free(box):
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
        self.sheet.rect(LAYER_HAND, box, PAPER)
        self.sheet.text(LAYER_HAND, tx, ty, text, px=LABEL_PX, anchor=anchor)

        start = (box[0], ty) if anchor == "lm" else (box[2], ty)
        self._arrow(start, (x, y))
        return box

    def _arrow(self, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        dist = math.hypot(dx, dy)
        if dist < 6:
            return
        # Stop just short, so the nib does not sit on top of the thing.
        back = min(6, dist * 0.2)
        end = (end[0] - dx / dist * back, end[1] - dy / dist * back)
        dx, dy = end[0] - start[0], end[1] - start[1]
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        bow = 0.22
        ctrl = (mid[0] - dy * bow, mid[1] + dx * bow)
        curve = bezier(start, ctrl, end)
        self.sheet.line(LAYER_HAND, curve, PEN)

        # A two-stroke head, angled off the direction the curve arrives from,
        # and sized to the arrow: a fixed head on a short arrow swallows the
        # shaft, which is what made these read as carets rather than arrows.
        angle = math.atan2(end[1] - curve[-2][1], end[0] - curve[-2][0])
        size = max(5.0, min(10.0, dist * 0.3))
        for turn in (2.5, -2.5):
            self.sheet.line(
                LAYER_HAND,
                [
                    end,
                    (
                        end[0] + size * math.cos(angle + turn),
                        end[1] + size * math.sin(angle + turn),
                    ),
                ],
                PEN,
            )


# --------------------------------------------------------------------------
# Doodles
# --------------------------------------------------------------------------

DOODLE_INK_OK = (
    0.015  # fraction of a box that may already be inked before it counts as busy
)
DOODLE_REACH = 7  # rings of candidate positions to try outward from the pub
DOODLE_FAR = (
    0.006  # per ring: a clean patch two roads away loses to a grazed one next door
)


class Doodler:
    """Puts each drawing beside its pub, in the emptiest paper within reach.

    The names went down first and are not moved: a doodle is decoration and
    a name is navigation. What is left is searched in rings outward from the
    pub, each ring tried from the side away from the label first, so the
    drawing and the name flank the pub rather than crowd one side of it. A
    candidate is measured against a raster of the map layer - roads, banks,
    park edges - and the first one that is nearly clean wins; failing that,
    the least inked. A box never covers the pub itself, because that is the
    point the arrow is aimed at, and never overlaps anything already placed.
    """

    def __init__(self, sheet, size, taken):
        self.sheet, self.size = sheet, size
        self.placed = taken  # shared with Hand: what it placed, plus ours
        # Ink only, not colour: a doodle on a park or on the river is fine,
        # a doodle across a road is not.
        self.ink = (
            to_pil(sheet, ss=1, layers=(LAYER_MAP,))
            .convert("L")
            .point(lambda v: 255 if v < 128 else 0)
        )

    def _inked(self, box):
        crop = self.ink.crop(tuple(int(round(v)) for v in box))
        return sum(crop.histogram()[128:]) / max(1, crop.width * crop.height)

    def _free(self, box, pad=6):
        b = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
        return not any(
            b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3]
            for o in self.placed
        )

    def pin(self, fx, fy, img, png, px=DOODLE_PX, name="doodle"):
        """Put a drawing exactly where the manifest says, search be damned.

        For the ones that are a picture of the place itself - the Palace of
        Westminster along its own riverbank - where "beside the label, off
        the roads" is the wrong rule. It still goes on the taken list, so the
        searched doodles route round it; it is only clamped to the sheet.
        """
        w, h = img.size
        scale = px / max(w, h)
        w, h = w * scale, h * scale
        margin = 14
        cx = min(max(fx * self.size, margin + w / 2), self.size - margin - w / 2)
        cy = min(max(fy * self.size, margin + h / 2), self.size - margin - h / 2)
        box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        self.placed.append(box)
        with self.sheet.grouped(LAYER_DOODLE, f"doodle-{name}"):
            self.sheet.image(LAYER_DOODLE, box, img, png)
        return box

    def put(self, x, y, img, png, px=DOODLE_PX, away_from=None, name="doodle"):
        w, h = img.size
        scale = px / max(w, h)
        w, h = w * scale, h * scale
        margin, step, gap = 14, 26, 22

        # Candidate directions, nearest to "away from the label" first.
        if away_from is not None:
            lx, ly = (away_from[0] + away_from[2]) / 2, (
                away_from[1] + away_from[3]
            ) / 2
            prefer = math.atan2(y - ly, x - lx)
        else:
            prefer = -math.pi / 2
        angles = sorted(
            (prefer + k * math.tau / 12 for k in range(12)),
            key=lambda a: abs((a - prefer + math.pi) % math.tau - math.pi),
        )

        best, best_score = None, None
        for ring in range(DOODLE_REACH):
            reach = max(w, h) / 2 + gap + ring * step
            for a in angles:
                cx, cy = x + reach * math.cos(a), y + reach * math.sin(a)
                box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
                if not (
                    margin < box[0]
                    and box[2] < self.size - margin
                    and margin < box[1]
                    and box[3] < self.size - margin
                ):
                    continue
                if box[0] - 8 < x < box[2] + 8 and box[1] - 8 < y < box[3] + 8:
                    continue
                if not self._free(box):
                    continue
                inked = self._inked(box)
                score = inked + DOODLE_FAR * ring
                if best_score is None or score < best_score:
                    best, best_score = box, score
                if inked < DOODLE_INK_OK:
                    break
            else:
                continue
            break

        if best is None:
            return None
        self.placed.append(best)
        with self.sheet.grouped(LAYER_DOODLE, f"doodle-{name}"):
            self.sheet.image(LAYER_DOODLE, best, img, png)
        return best


def load_doodles(bundle, meta):
    """The bundle's doodles, with their positions resolved and files loaded.

    Returns `(ready, missing)`: what can be drawn, and the entries whose
    drawing has not been made yet, so the caller can say so by name.
    """
    by_name = {m["name"]: m for m in meta["markers"]}
    ready, missing = [], []
    for entry in load_manifest(bundle):
        path = doodle_path(bundle, entry)
        if not os.path.exists(path):
            missing.append(entry)
            continue
        if "marker" in entry:
            marker = by_name.get(entry["marker"])
            if marker is None:
                raise SystemExit(
                    f"doodles.json names {entry['marker']!r}, which is not a marker in meta.json"
                )
            lat, lon = marker["lat"], marker["lon"]
        else:
            lat, lon = entry["at"]
        if "pin" in entry and not (
            len(entry["pin"]) == 2 and all(0 <= v <= 1 for v in entry["pin"])
        ):
            raise SystemExit(
                f"doodles.json: 'pin' is the doodle's centre as fractions of the "
                f"sheet, [x, y] in 0..1, not {entry['pin']!r}"
            )
        png = open(path, "rb").read()
        img = Image.open(path).convert("RGBA")
        ready.append(dict(entry, lat=lat, lon=lon, img=img, png=png))
    return ready, missing


# --------------------------------------------------------------------------
# The drawing
# --------------------------------------------------------------------------


def draw_roads(sheet, els, box, size):
    """Roads as a pair of wobbly edges with white between them.

    Drawn as a casing rather than two offset polylines: stroke every road
    black at corridor + 2 nibs, then stroke every road white at corridor. The
    second pass clears the first's edges wherever roads meet, so junctions
    come out open the way a hand draws them, with no junction geometry to get
    wrong. Both passes therefore have to stay in this order, and in this
    layer: split them and neither half is a map.
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
        prepared.append((freehand(pts, el.get("id", 0)), WIDTHS[el["tags"]["highway"]]))
    for pts, width in prepared:
        sheet.line(LAYER_MAP, pts, width + 2 * PEN, INK)
    for pts, width in prepared:
        sheet.line(LAYER_MAP, pts, width, PAPER)
    return roads


def draw_area(sheet, el, box, size, colour, amp, limit=1.0):
    """Colour a ring in and ink its edge, from one path.

    The wobble is applied after clipping and then clamped back inside, so the
    ink and the colour follow the same hand rather than the colour following
    the survey exactly while the pen wanders - which left the river with a
    stepped, machine-cut edge under a hand-drawn line.
    """
    drawn = []
    for ring in closed_rings(el):
        poly = clip_to_box([box.project(q["lat"], q["lon"], size) for q in ring], size)
        if len(poly) < 3:
            continue
        poly = [
            (min(max(x, 0.0), float(size)), min(max(y, 0.0), float(size)))
            for x, y in freehand(poly + poly[:1], el.get("id", 0), amp=amp)
        ]
        if _area(poly) > limit * size * size:
            continue
        sheet.poly(LAYER_MAP, poly, colour)
        for run in edge_runs(poly, size):
            sheet.line(LAYER_MAP, run, PEN)
            drawn.append(run)
    return drawn


def draw_water(sheet, els, box, size):
    """Coloured in, banks inked over the top, and a few squiggles."""
    banks = []
    for el in els:
        tags = el.get("tags", {})
        if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
            # Water is the minority of a town crop, so a fill covering most of
            # the sheet means the ring closed the wrong way round - the same
            # sanity limit build_venue_map.py puts on its flood.
            banks += draw_area(sheet, el, box, size, WATER, amp=2.6, limit=0.35)
    if not banks:
        return
    longest = max(banks, key=len)
    rnd = random.Random(7)
    for i in range(len(longest) // 9, len(longest), max(9, len(longest) // 7)):
        x, y = longest[i]
        run = 26 * rnd.uniform(0.6, 1.2)
        sheet.line(
            LAYER_MAP,
            [(x + run * t / 6, y + 4 * math.sin(t * 1.6)) for t in range(7)],
            PEN,
        )


def draw_parks(sheet, els, box, size):
    for el in els:
        if el.get("tags", {}).get("leisure") == "park":
            draw_area(sheet, el, box, size, PARK, amp=2.2)


PUB_DOT = 3.5  # radius of the mark at each pub, in output pixels


def draw_pubs(sheet, meta, box, size):
    """A dot at every marker, on the map layer, in a `pubs` group.

    The arrows point at these, but the arrows live with the handwriting and
    the handwriting is the layer that gets redrawn by hand - so the pub's
    position has to be on the sheet somewhere else, or re-lettering it means
    guessing where the pubs were. One circle per marker, with an id.
    """
    with sheet.grouped(LAYER_MAP, "pubs"):
        for marker in meta["markers"]:
            x, y = box.project(marker["lat"], marker["lon"], size)
            sheet.group(
                LAYER_MAP, f"pub-{slug(marker['name'])}", [("dot", x, y, PUB_DOT, INK)]
            )


def draw_street_names(sheet, roads, box, size, limit=14):
    """Name a handful of the main roads, written along the road.

    Longest first, and a name that would land on one already written is
    dropped: two street names on top of each other is worse than one.
    """
    font = _font(STREET_PX)
    measure = _measure()
    best = {}
    for el in roads:
        tags = el["tags"]
        if tags.get("highway") not in MAJOR or not tags.get("name"):
            continue
        geom = el["geometry"]
        span = abs(geom[0]["lat"] - geom[-1]["lat"]) + abs(
            geom[0]["lon"] - geom[-1]["lon"]
        )
        if span > best.get(tags["name"], (0, None))[0]:
            best[tags["name"]] = (span, geom)

    edge = 110
    written = []
    for name, (_, geom) in sorted(best.items(), key=lambda kv: -kv[1][0]):
        if len(written) >= limit:
            break
        i = len(geom) // 2
        x, y = box.project(geom[i]["lat"], geom[i]["lon"], size)
        if not (edge < x < size - edge and edge < y < size - edge):
            continue
        j, k = max(0, i - 2), min(len(geom) - 1, i + 2)
        x0, y0 = box.project(geom[j]["lat"], geom[j]["lon"], size)
        x1, y1 = box.project(geom[k]["lat"], geom[k]["lon"], size)

        half = measure.textlength(name, font=font) / 2
        here = (x - half - 8, y - STREET_PX * 0.7, x + half + 8, y + STREET_PX * 0.7)
        if any(
            here[0] < b[2] and b[0] < here[2] and here[1] < b[3] and b[1] < here[3]
            for b in written
        ):
            continue

        deg = -math.degrees(math.atan2(y1 - y0, x1 - x0))
        if deg > 90 or deg < -90:  # never write upside down
            deg += 180
        # A wide paper stroke under the ink clears room for the words without
        # a knockout box, which on a rotated label would show its corners.
        sheet.text(
            LAYER_HAND,
            x,
            y,
            name,
            px=STREET_PX,
            anchor="mm",
            rotate=deg,
            stroke=PAPER,
            stroke_width=5,
        )
        written.append(here)
    return written


def draw_title(sheet, text, size):
    """Outlined capitals across the top, each letter set slightly askew.

    Same hand as the rest of the sheet, hollow and much larger. The paper
    stroke under each letter is what stops the roads running through the word.
    """
    font = _font(TITLE_PX)
    widths = [_measure().textlength(ch, font=font) for ch in text]
    gap = 10
    x = (size - sum(widths) - gap * (len(text) - 1)) / 2
    y = 120
    rnd = random.Random(11)
    extent = None
    for ch, width in zip(text, widths):
        cx, cy = x + width / 2, y + rnd.uniform(-7, 7)
        spin = rnd.uniform(-3.0, 3.0)
        sheet.text(
            LAYER_HAND,
            cx,
            cy,
            ch,
            px=TITLE_PX,
            anchor="mm",
            fill=PAPER,
            stroke=PAPER,
            stroke_width=5 * PEN,
            rotate=spin,
        )
        sheet.text(
            LAYER_HAND,
            cx,
            cy,
            ch,
            px=TITLE_PX,
            anchor="mm",
            fill=PAPER,
            stroke=INK,
            stroke_width=PEN,
            rotate=spin,
        )
        here = (
            cx - width / 2 - 6,
            cy - TITLE_PX * 0.6,
            cx + width / 2 + 6,
            cy + TITLE_PX * 0.4,
        )
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
        x += width + gap
    return extent


def compose(meta, els, size=OUT_PX, title=None, doodles=()):
    """Build the whole drawing as a display list.

    Returns the sheet and the doodles that found no room, by entry.
    """
    box = Box(meta["centre"][0], meta["centre"][1], meta["half_span_m"])
    sheet = Sheet(size)

    sheet.rect(LAYER_MAP, (0, 0, size, size), PAPER)
    draw_parks(sheet, els, box, size)
    draw_water(sheet, els, box, size)
    roads = draw_roads(sheet, els, box, size)
    draw_pubs(sheet, meta, box, size)
    taken = draw_street_names(sheet, roads, box, size)
    if title:
        taken.append(draw_title(sheet, title, size))

    hand = Hand(sheet, size, taken=taken)
    labels = {}
    # Landmarks first: they are the things everyone navigates by, so they get
    # the good positions when the pubs crowd them.
    for marker in sorted(meta["markers"], key=lambda m: m["kind"] != "landmark"):
        x, y = box.project(marker["lat"], marker["lon"], size)
        labels[marker["name"]] = hand.put(x, y, marker["name"])

    # Doodles last, into whatever paper the names left: decoration gives way
    # to navigation, never the other way round.
    crowded = []
    if doodles:
        doodler = Doodler(sheet, size, taken=hand.placed)
        # Pinned ones first, so the searched ones know to route round them.
        for entry in doodles:
            if "pin" in entry:
                doodler.pin(
                    *entry["pin"],
                    entry["img"],
                    entry["png"],
                    px=entry.get("size", DOODLE_PX),
                    name=doodle_name(entry),
                )
        for entry in doodles:
            if "pin" in entry:
                continue
            x, y = box.project(entry["lat"], entry["lon"], size)
            placed = doodler.put(
                x,
                y,
                entry["img"],
                entry["png"],
                px=entry.get("size", DOODLE_PX),
                away_from=labels.get(entry.get("marker")),
                name=doodle_name(entry),
            )
            if placed is None:
                crowded.append(entry)
    return sheet, crowded


# --------------------------------------------------------------------------
# Emitters
# --------------------------------------------------------------------------


def _rgb(colour):
    """'#rrggbb' -> (r, g, b). The display list speaks CSS; PIL does not."""
    value = int(colour[1:], 16)
    return (value >> 16, (value >> 8) & 0xFF, value & 0xFF)


def _pil_text(img, op, ss):
    _, x, y, text, px, anchor, fill, stroke, stroke_w, rotate = op
    font = _font(px * ss)
    fill_v = _rgb(fill)
    stroke_v = None if stroke is None else _rgb(stroke)
    width = int(round(stroke_w * ss))

    if abs(rotate) < 0.01:
        ImageDraw.Draw(img).text(
            (x * ss, y * ss),
            text,
            font=font,
            fill=fill_v,
            anchor=anchor,
            stroke_width=width,
            stroke_fill=stroke_v,
        )
        return

    # PIL cannot rotate text, so set it in a strip and turn the strip. Carry a
    # mask of the strip's own area: rotating grows the bounding box, and the
    # corners it grows into are not part of the label - pasting them put white
    # triangles across the roads either side.
    pad = width + 8 * ss
    bb = _measure().textbbox((0, 0), text, font=font)
    w, h = int(bb[2] - bb[0] + 2 * pad), int(bb[3] - bb[1] + 2 * pad)
    where = (pad - bb[0], pad - bb[1])
    body = dict(font=font, stroke_width=width)

    strip = Image.new("RGB", (w, h), _rgb(PAPER))
    ImageDraw.Draw(strip).text(where, text, fill=fill_v, stroke_fill=stroke_v, **body)
    # Mask to the glyphs and their stroke rather than the strip, so a rotated
    # label lays its own paper only where it is written. Pasting the strip
    # itself would knock a tilted rectangle out of the water and the parks.
    cover = Image.new("L", (w, h), 0)
    ImageDraw.Draw(cover).text(
        where, text, fill=255, stroke_fill=255 if stroke_v else None, **body
    )
    spin = dict(expand=True, resample=Image.BICUBIC)
    strip = strip.rotate(rotate, fillcolor=_rgb(PAPER), **spin)
    cover = cover.rotate(rotate, fillcolor=0, **spin)
    img.paste(
        strip, (int(x * ss - strip.width / 2), int(y * ss - strip.height / 2)), cover
    )


def to_pil(sheet, ss=SS, layers=LAYERS):
    """The raster the app and the poster need."""
    side = int(sheet.size * ss)
    img = Image.new("RGB", (side, side), _rgb(PAPER))
    for layer in layers:
        _pil_ops(img, sheet.ops[layer], ss)
    return img.resize((sheet.size, sheet.size), Image.LANCZOS)


def _pil_ops(img, ops, ss):
    draw = ImageDraw.Draw(img)
    for op in ops:
        if op[0] == "line":
            _, pts, width, colour = op
            draw.line(
                [(x * ss, y * ss) for x, y in pts],
                fill=_rgb(colour),
                width=max(1, int(round(width * ss))),
                joint="curve",
            )
        elif op[0] == "rect":
            _, b, fill = op
            draw.rectangle(
                [b[0] * ss, b[1] * ss, b[2] * ss, b[3] * ss], fill=_rgb(fill)
            )
        elif op[0] == "poly":
            _, pts, fill = op
            draw.polygon([(x * ss, y * ss) for x, y in pts], fill=_rgb(fill))
        elif op[0] == "dot":
            _, x, y, r, colour = op
            draw.ellipse(
                [(x - r) * ss, (y - r) * ss, (x + r) * ss, (y + r) * ss],
                fill=_rgb(colour),
            )
        elif op[0] == "image":
            _, b, doodle, _png = op
            fitted = _fit(doodle, b, ss)
            img.paste(fitted[0], fitted[1], fitted[0])
        elif op[0] == "group":
            _pil_ops(img, op[2], ss)
        else:
            _pil_text(img, op, ss)


def _fit(doodle, box, ss):
    """Scale a drawing into `box` keeping its aspect; returns it and where it goes."""
    bw, bh = (box[2] - box[0]) * ss, (box[3] - box[1]) * ss
    scale = min(bw / doodle.width, bh / doodle.height)
    w, h = max(1, int(round(doodle.width * scale))), max(
        1, int(round(doodle.height * scale))
    )
    fitted = doodle.resize((w, h), Image.LANCZOS)
    at = (
        int(round(box[0] * ss + (bw - w) / 2)),
        int(round(box[1] * ss + (bh - h) / 2)),
    )
    return fitted, at


_SVG_ANCHOR = {"lm": "start", "rm": "end", "mm": "middle"}


def _face_css():
    data = base64.b64encode(open(FACE, "rb").read()).decode()
    return (
        f"@font-face{{font-family:'{FAMILY}';"
        f"src:url(data:font/ttf;base64,{data}) format('truetype');}}"
    )


def _svg_ops(ops):
    out = []
    for op in ops:
        if op[0] == "line":
            _, pts, width, colour = op
            path = " ".join(
                ("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}"
                for i, (x, y) in enumerate(pts)
            )
            out.append(
                f'<path d="{path}" fill="none" stroke="{colour}" '
                f'stroke-width="{width:.2f}"/>'
            )
        elif op[0] == "rect":
            _, b, fill = op
            out.append(
                f'<rect x="{b[0]:.1f}" y="{b[1]:.1f}" width="{b[2] - b[0]:.1f}" '
                f'height="{b[3] - b[1]:.1f}" fill="{fill}"/>'
            )
        elif op[0] == "poly":
            _, pts, fill = op
            pt = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            out.append(f'<polygon points="{pt}" fill="{fill}"/>')
        elif op[0] == "dot":
            _, x, y, r, colour = op
            out.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{colour}"/>'
            )
        elif op[0] == "group":
            _, name, ops_ = op
            out.append(f'<g id="{escape(name)}">')
            out.extend(_svg_ops(ops_))
            out.append("</g>")
        elif op[0] == "image":
            _, b, _img, png = op
            data = base64.b64encode(png).decode()
            out.append(
                f'<image x="{b[0]:.1f}" y="{b[1]:.1f}" width="{b[2] - b[0]:.1f}" '
                f'height="{b[3] - b[1]:.1f}" preserveAspectRatio="xMidYMid meet" '
                f'href="data:image/png;base64,{data}"/>'
            )
        else:
            _, x, y, text, px, anchor, fill, stroke, stroke_w, rotate = op
            attrs = (
                f'x="{x:.1f}" y="{y:.1f}" font-size="{px:.1f}" '
                f'text-anchor="{_SVG_ANCHOR[anchor]}" fill="{fill}"'
            )
            if stroke and stroke_w:
                # paint-order puts the stroke behind the fill, so a paper
                # stroke clears room instead of eating into the letters.
                attrs += (
                    f' stroke="{stroke}" stroke-width="{stroke_w:.2f}"'
                    ' paint-order="stroke fill"'
                )
            if abs(rotate) >= 0.01:
                # SVG turns clockwise; the display list turns the other way.
                attrs += f' transform="rotate({-rotate:.2f} {x:.1f} {y:.1f})"'
            out.append(f"<text {attrs}>{escape(text)}</text>")
    return out


def to_svg(sheet, layers=LAYERS):
    """One `<g>` per layer, so a layer can be pulled out or replaced whole.

    The paper is the map layer's own first primitive rather than a backdrop
    here, so the map on its own looks like the map, the handwriting on its own
    stays transparent and stackable, and the combined file gets the paper once
    and in the right order.
    """
    size = sheet.size
    body = [_svg_open(size), f"<style>{_face_css()}</style>"]
    for layer in layers:
        body.append(
            f'<g id="{layer}" {_inkscape_layer(layer)} font-family="{FAMILY}" '
            'dominant-baseline="central" stroke-linecap="round" stroke-linejoin="round">'
        )
        body.extend(_svg_ops(sheet.ops[layer]))
        body.append("</g>")
    body.append("</svg>")
    return "\n".join(body)


INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"


def _svg_open(size):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="{INKSCAPE_NS}" '
        f'width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
    )


def _inkscape_layer(name):
    """Mark a `<g>` as a layer, so Inkscape's Layers panel lists it as one.

    Other renderers ignore the attributes. Without them a hand-editor opens
    one flat drawing and has to select the roads out from under the words.
    """
    return f'inkscape:groupmode="layer" inkscape:label="{name}"'


def svg_paths(out_path):
    """`x/map.jpg` -> the combined, map-only and handwriting-only SVGs."""
    stem = os.path.splitext(out_path)[0]
    return [
        (None, f"{stem}.svg"),
        (LAYER_MAP, f"{stem}.map.svg"),
        (LAYER_DOODLE, f"{stem}.doodles.svg"),
        (LAYER_HAND, f"{stem}.hand.svg"),
    ]


# --------------------------------------------------------------------------
# Not overwriting somebody's lettering
# --------------------------------------------------------------------------

STAMP = "render_venue_map-sha256"
_STAMP_RE = re.compile(rf"<!--{STAMP}:([0-9a-f]{{64}})-->\s*$")


def _stamped(svg):
    """Sign a generated file, so a hand-edited one can be told apart."""
    digest = hashlib.sha256(svg.encode()).hexdigest()
    return f"{svg}\n<!--{STAMP}:{digest}-->\n"


def edited_by_hand(path):
    """True if `path` exists and is not byte-for-byte something we wrote.

    The whole point of the layers is that the handwriting gets replaced, so
    the renderer must not be the thing that destroys the replacement. An
    unsigned or altered file is somebody's work.
    """
    if not os.path.exists(path):
        return False
    try:
        body = open(path).read()
    except UnicodeDecodeError:
        return True
    match = _STAMP_RE.search(body)
    if not match:
        return True
    return hashlib.sha256(body[: match.start()].rstrip("\n").encode()).hexdigest() != (
        match.group(1)
    )


def layer_group(svg, layer):
    """Pull one `<g id="...">...</g>` out of an SVG, as text."""
    start = svg.find(f'<g id="{layer}"')
    if start < 0:
        raise SystemExit(f"no layer {layer!r} in that SVG")
    depth, i = 0, start
    while i < len(svg):
        if svg.startswith("<g", i):
            depth += 1
        elif svg.startswith("</g>", i):
            depth -= 1
            if depth == 0:
                end = i + 4
                return svg[start:end]
        i += 1
    raise SystemExit(f"layer {layer!r} is not closed in that SVG")


def combine_layers(out_path, size):
    """Rebuild the combined SVG from the two layer files as they are on disk.

    This is the other half of being able to re-letter a layer: edit
    `*.hand.svg`, run this, and the combined file agrees with it again. It is
    pure text - the layers are stacked, not re-derived - so nothing about a
    redrawn layer has to be understood.
    """
    paths = dict(svg_paths(out_path))
    groups = [layer_group(open(paths[layer]).read(), layer) for layer in LAYERS]
    body = [_svg_open(size), f"<style>{_face_css()}</style>", *groups, "</svg>"]
    return "\n".join(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", required=True, help="the build_venue_map.py out dir")
    ap.add_argument("--out", required=True, help="raster image to write")
    ap.add_argument("--title", default=None, help="title across the top")
    ap.add_argument("--size", type=int, default=OUT_PX)
    ap.add_argument("--supersample", type=int, default=SS)
    ap.add_argument("--no-svg", action="store_true", help="skip the layer files")
    ap.add_argument(
        "--force",
        action="store_true",
        help="overwrite layer SVGs that have been edited by hand",
    )
    ap.add_argument(
        "--combine-only",
        action="store_true",
        help="rebuild the combined SVG from the layer files on disk and stop; "
        "this is what to run after re-lettering the handwriting layer",
    )
    args = ap.parse_args()

    if args.combine_only:
        combined = svg_paths(args.out)[0][1]
        open(combined).close()  # fail early and clearly if it is not there
        open(combined, "w").write(_stamped(combine_layers(args.out, args.size)))
        print(f"wrote {combined} from the layer files on disk")
        print("  rasterise it over the .jpg yourself to put it in the app")
        return

    meta = json.load(open(os.path.join(args.bundle, "meta.json")))
    feat = os.path.join(args.bundle, "osm_features.json.gz")
    if not os.path.exists(feat):
        raise SystemExit(
            f"{feat} is missing - run build_venue_map.py for this venue first; "
            "it caches the OSM features this draws from."
        )
    with gzip.open(feat, "rt") as fh:
        els = json.load(fh)

    # Refuse before drawing anything, so a refusal costs nothing and leaves
    # the raster agreeing with the SVGs beside it.
    if not args.no_svg and not args.force:
        touched = [p for _, p in svg_paths(args.out) if edited_by_hand(p)]
        if touched:
            raise SystemExit(
                "these have been edited since they were generated:\n  "
                + "\n  ".join(touched)
                + "\n\nRe-rendering would overwrite that lettering. Either keep it "
                "(--combine-only rebuilds the combined SVG from the layers on "
                "disk), or say --force to throw it away, or --no-svg to "
                "refresh only the raster."
            )

    doodles, undrawn = load_doodles(args.bundle, meta)
    sheet, crowded = compose(
        meta, els, size=args.size, title=args.title, doodles=doodles
    )
    to_pil(sheet, ss=args.supersample).convert("RGB").save(
        args.out, quality=92, optimize=True
    )
    written = [args.out]

    if not args.no_svg:
        for layer, path in svg_paths(args.out):
            open(path, "w").write(
                _stamped(to_svg(sheet, layers=LAYERS if layer is None else (layer,)))
            )
            written.append(path)

    for path in written:
        print(f"wrote {path}")
    counts = ", ".join(f"{k} {len(v)}" for k, v in sheet.ops.items())
    print(f"  {args.size} x {args.size}; primitives: {counts}")
    print(f"  {len(meta['markers'])} labelled markers, {len(els)} OSM features")
    if doodles or undrawn:
        print(f"  {len(doodles) - len(crowded)} doodles placed")
    for entry in crowded:
        print(
            f"  no room for the {entry['subject']} doodle near {entry.get('marker', entry.get('at'))}"
        )
    if undrawn:
        print(
            f"  {len(undrawn)} doodles in doodles.json have not been drawn yet - "
            "run doodle_venue_map.py --bundle for them:"
        )
        for entry in undrawn:
            print(f"    {entry.get('marker') or entry.get('at')}: {entry['subject']}")
    print(
        "  the venue's reference points are this crop's corners:\n"
        f"    ref_1 x=0 y=0        lat={meta['bounds']['north']:.6f} "
        f"long={meta['bounds']['west']:.6f}\n"
        f"    ref_2 x={args.size} y={args.size}  lat={meta['bounds']['south']:.6f} "
        f"long={meta['bounds']['east']:.6f}"
    )


if __name__ == "__main__":
    main()
