"""Build the reference bundle for a new venue map.

Given a centre and a half-span, this works out the crop, pulls the roads,
water and pubs inside it from OpenStreetMap, and writes everything needed to
have an image model redraw it in the Kingston style:

    01_style_reference_kingston.png   the existing hand-drawn map (style only)
    01b_style_reference_detail.png    a close-up of it (style only)
    02_osm_accurate.png               the real OSM map of the crop, pins on
    03_road_skeleton.png              roads, river and named markers only
    prompt.md                         the prompt, with this venue filled in
    meta.json                         for check_venue_map.py afterwards

Usage:

    uv run python build_venue_map.py \\
        --name westminster \\
        --centre 51.4958738,-0.1309233 \\
        --half-span 650 \\
        --centre-label "House Absolute" \\
        --landmark "Big Ben:51.50073,-0.12462" \\
        --landmark "Westminster Abbey:51.49940,-0.12764" \\
        --out /tmp/venue_westminster

Everything outside the crop is dropped and listed on stdout, so the crop is
what defines the pub list rather than the other way round.
"""

import argparse
import io
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

TILE = 256
OUT_PX = 2000
SS = 4  # supersample: PIL does not antialias lines, so draw big and shrink
UA = {"User-Agent": "streetfight-venue-builder/1.0 (personal hobby project)"}

# Tried in order. overpass-api.de is the canonical one and is often busy or
# down; the rest are public mirrors. The last is Russian-hosted - it serves
# plain OSM data and takes no credentials, but the query does carry the
# venue's coordinates, so drop it from the list if that matters to you.
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Road classes worth drawing. Anything smaller is mews and service yards, and
# the hand-drawn style is far sparser than a real street map anyway.
WIDTHS = {
    "motorway": 11,
    "trunk": 11,
    "primary": 10,
    "secondary": 8,
    "tertiary": 7,
    "residential": 4,
    "unclassified": 4,
}
MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary"}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

PUB_RED = (200, 20, 20)
LANDMARK_PURPLE = (90, 40, 150)
CENTRE_BLUE = (0, 80, 200)


# --------------------------------------------------------------------------
# Web mercator
# --------------------------------------------------------------------------


def lon_to_px(lon, z):
    return (lon + 180.0) / 360.0 * TILE * 2**z


def lat_to_px(lat, z):
    s = math.sin(math.radians(lat))
    return (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * TILE * 2**z


def px_to_lon(px, z):
    return px / (TILE * 2**z) * 360.0 - 180.0


def px_to_lat(px, z):
    y = 0.5 - px / (TILE * 2**z)
    return math.degrees(2 * math.atan(math.exp(2 * math.pi * y)) - math.pi / 2)


def haversine(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


class Box:
    """The crop: a square of ground, symmetric about the centre.

    Symmetric in degrees rather than metres, because that is what `VenueMap`
    assumes when it interpolates between the two reference points.
    """

    def __init__(self, lat, lon, half_m):
        self.centre = (lat, lon)
        self.half_m = half_m
        self.north = lat + half_m / 110574.0
        self.south = lat - half_m / 110574.0
        dlon = half_m / (111320.0 * math.cos(math.radians(lat)))
        self.east = lon + dlon
        self.west = lon - dlon

    def frac(self, lat, lon):
        return (
            (lon - self.west) / (self.east - self.west),
            (self.north - lat) / (self.north - self.south),
        )

    def project(self, lat, lon, size):
        fx, fy = self.frac(lat, lon)
        return fx * size, fy * size

    def inside(self, lat, lon, margin=0.03):
        fx, fy = self.frac(lat, lon)
        return margin <= fx <= 1 - margin and margin <= fy <= 1 - margin

    def zoom(self):
        """Tile zoom that renders this crop at roughly OUT_PX across."""
        want = 2 * self.half_m / OUT_PX
        z = math.log2(156543.03392 * math.cos(math.radians(self.centre[0])) / want)
        return max(14, min(19, round(z)))


# --------------------------------------------------------------------------
# OpenStreetMap
# --------------------------------------------------------------------------


def overpass(query, attempts=3):
    """Ask every endpoint in turn, then go round again.

    These are free public services: at any moment several of them are busy,
    rate-limiting or down, and the same query that just 500'd will often
    succeed a minute later. Failing the whole build on the first sweep is
    almost always premature.
    """
    last = None
    for attempt in range(attempts):
        for url in OVERPASS:
            try:
                req = urllib.request.Request(url, data=query.encode(), headers=UA)
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.load(r)
            except Exception as exc:  # noqa: BLE001 - try the next endpoint
                print(f"  {url.split('/')[2]}: {exc}", file=sys.stderr)
                last = exc
        if attempt + 1 < attempts:
            wait = 10 * (attempt + 1)
            print(f"  all endpoints failed; retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(
        f"every Overpass endpoint failed {attempts} times; last error: {last}.\n"
        "These are free services and are often all busy at once - wait a few "
        "minutes and re-run; the tile cache means only the query is repeated."
    )


def fetch_features(box):
    pad = 0.15 * (box.north - box.south)
    bbox = f"{box.south - pad},{box.west - pad}," f"{box.north + pad},{box.east + pad}"
    classes = "|".join(WIDTHS)
    return overpass(f"""
[out:json][timeout:120];
(
  way["highway"~"^({classes})$"]({bbox});
  way["waterway"="riverbank"]({bbox});
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});
  way["leisure"="park"]({bbox});
);
out geom;
""")["elements"]


def fetch_pubs(box, include_bars):
    kinds = "pub|bar" if include_bars else "pub"
    bbox = f"{box.south},{box.west},{box.north},{box.east}"
    els = overpass(f"""
[out:json][timeout:90];
(
  node["amenity"~"^({kinds})$"]({bbox});
  way["amenity"~"^({kinds})$"]({bbox});
);
out center tags;
""")["elements"]
    found = {}
    for e in els:
        t = e.get("tags", {})
        name = t.get("name")
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if not name or lat is None or name in found:
            continue
        addr = " ".join(
            x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x
        )
        found[name] = dict(
            name=name,
            lat=lat,
            lon=lon,
            street=addr,
            dist=haversine(box.centre, (lat, lon)),
        )
    return sorted(found.values(), key=lambda p: p["dist"])


def fetch_tiles(box, cache):
    """Stitch whole tiles and crop to the box exactly."""
    z = box.zoom()
    os.makedirs(cache, exist_ok=True)
    left, right = lon_to_px(box.west, z), lon_to_px(box.east, z)
    top, bottom = lat_to_px(box.north, z), lat_to_px(box.south, z)
    tx0, tx1 = int(left // TILE), int(right // TILE)
    ty0, ty1 = int(top // TILE), int(bottom // TILE)
    n = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    print(f"  zoom {z}, {n} tiles")

    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            path = os.path.join(cache, f"{z}_{tx}_{ty}.png")
            if os.path.exists(path):
                tile = Image.open(path).convert("RGB")
            else:
                url = f"https://tile.openstreetmap.org/{z}/{tx}/{ty}.png"
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers=UA), timeout=30
                ) as r:
                    data = r.read()
                open(path, "wb").write(data)
                time.sleep(0.12)  # be kind: the tile server is a donation
                tile = Image.open(io.BytesIO(data)).convert("RGB")
            canvas.paste(tile, ((tx - tx0) * TILE, (ty - ty0) * TILE))

    ox, oy = tx0 * TILE, ty0 * TILE
    crop = canvas.crop(
        (round(left - ox), round(top - oy), round(right - ox), round(bottom - oy))
    )
    return crop.resize((OUT_PX, OUT_PX), Image.LANCZOS)


def rings(el):
    """Outer rings of a way or multipolygon relation, as lat/lon lists."""
    if el["type"] == "way" and el.get("geometry"):
        return [el["geometry"]]
    if el["type"] == "relation":
        return [
            m["geometry"]
            for m in el.get("members", [])
            if m.get("role") == "outer" and m.get("geometry")
        ]
    return []


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


class Labeller:
    """Places labels without letting them overlap.

    Two markers whose names collide is worse than a label sitting slightly off
    its dot, so a colliding label is nudged vertically and given a leader line
    back to the thing it belongs to.
    """

    def __init__(self, draw, size, scale):
        self.d, self.size, self.s = draw, size, scale
        self.font = ImageFont.truetype(FONT, int(27 * scale))
        self.placed = []

    def _hits(self, a):
        return any(
            not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
            for b in self.placed
        )

    def put(self, x, y, text, colour, radius):
        left = x > self.size * 0.55
        anchor = "rm" if left else "lm"
        tx = x - radius - 8 * self.s if left else x + radius + 8 * self.s
        step = 32 * self.s
        dy = 0
        for dy in [0] + [sg * k for k in range(1, 9) for sg in (-step, step)]:
            box = self.d.textbbox((tx, y + dy), text, font=self.font, anchor=anchor)
            box = (
                box[0] - 5 * self.s,
                box[1] - 3 * self.s,
                box[2] + 5 * self.s,
                box[3] + 3 * self.s,
            )
            if not self._hits(box):
                break
        self.placed.append(box)
        self.d.rectangle(list(box), fill="white")
        if dy:
            self.d.line(
                [(x, y), (tx, y + dy)], fill=colour, width=max(1, int(2 * self.s))
            )
        self.d.text((tx, y + dy), text, font=self.font, fill=colour, anchor=anchor)


def draw_markers(d, box, size, scale, pubs, landmarks, centre_label, names):
    r = int(19 * scale)
    num_font = ImageFont.truetype(FONT, int(24 * scale))
    lab = Labeller(d, size, scale) if names else None

    def marker(lat, lon, colour, text=None, square=False):
        x, y = box.project(lat, lon, size)
        if lab and text:
            lab.put(x, y, text, colour, r)
        if square:
            d.rectangle(
                [x - r, y - r, x + r, y + r],
                fill=colour,
                outline="white",
                width=max(2, int(3 * scale)),
            )
        else:
            d.ellipse(
                [x - r, y - r, x + r, y + r],
                fill=colour,
                outline="white",
                width=max(2, int(3 * scale)),
            )
        return x, y

    marker(*box.centre, CENTRE_BLUE, centre_label, square=True)
    for lm in landmarks:
        marker(lm["lat"], lm["lon"], LANDMARK_PURPLE, lm["name"])
    for i, p in enumerate(pubs, 1):
        x, y = marker(p["lat"], p["lon"], PUB_RED, p["name"])
        d.text((x, y), str(i), font=num_font, fill="white", anchor="mm")


def _flood_water(img, els, box, size, WATER):
    """Fill the river between its banks, without flooding the whole map.

    The banks are already drawn, so this only needs a seed in midstream. The
    centroid of the water geometry is the obvious guess but lands on dry ground
    wherever the river bends, so fall back to a grid, preferring points near
    the water. A candidate is only accepted if its fill reaches the edge of the
    image - real water always leaves the frame, whereas a seed that slipped
    into a courtyard fills that courtyard and stops.
    """
    pts = [
        box.project(q["lat"], q["lon"], size)
        for el in els
        if el.get("tags", {}).get("natural") == "water"
        or el.get("tags", {}).get("waterway") == "riverbank"
        for ring in rings(el)
        for q in ring
    ]
    pts = [(x, y) for x, y in pts if 0 <= x < size and 0 <= y < size]
    if not pts:
        return

    candidates = [
        (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))
    ]
    grid = [size * (i + 0.5) / 12 for i in range(12)]
    near = sorted(
        ((gx, gy) for gx in grid for gy in grid),
        key=lambda g: min((g[0] - x) ** 2 + (g[1] - y) ** 2 for x, y in pts),
    )
    candidates += near

    limit = size * size * 0.35
    edge = size - 1
    for cx, cy in candidates:
        cx, cy = int(cx), int(cy)
        if not (0 <= cx < size and 0 <= cy < size):
            continue
        if img.getpixel((cx, cy)) != (255, 255, 255):
            continue
        trial = img.copy()
        ImageDraw.floodfill(trial, (cx, cy), WATER, thresh=10)
        counts = trial.getcolors(maxcolors=1 << 24) or []
        filled = next((n for n, col in counts if col == WATER), 0)
        if not filled or filled > limit:
            continue
        touches = any(
            trial.getpixel(p) == WATER
            for p in [(0, cy), (edge, cy), (cx, 0), (cx, edge)]
        )
        if touches:
            img.paste(trial)
            print(
                f"  water flooded from ({cx * 1.0 / size:.2f}, "
                f"{cy * 1.0 / size:.2f}), {100 * filled / (size * size):.1f}% "
                "of the map"
            )
            return
    print("  no usable water seed; banks drawn as lines only")


def build_skeleton(els, box, pubs, landmarks, centre_label, out):
    size = OUT_PX * SS
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)
    WATER = (188, 218, 240)

    for el in els:
        if el.get("tags", {}).get("leisure") != "park":
            continue
        for ring in rings(el):
            p = [box.project(q["lat"], q["lon"], size) for q in ring]
            if len(p) >= 3:
                d.polygon(p, fill=(226, 240, 224))

    # A river is usually a multipolygon whose members Overpass clips to the
    # bbox, so its rings do not close and filling them directly floods the
    # whole map. Draw the banks and flood the water in from midstream instead.
    for el in els:
        t = el.get("tags", {})
        if t.get("natural") == "water" or t.get("waterway") == "riverbank":
            for ring in rings(el):
                p = [box.project(q["lat"], q["lon"], size) for q in ring]
                if len(p) > 1:
                    d.line(p, fill=WATER, width=3 * SS, joint="curve")

    _flood_water(img, els, box, size, WATER)
    d = ImageDraw.Draw(img)

    roads = [
        e
        for e in els
        if e.get("tags", {}).get("highway") in WIDTHS and e.get("geometry")
    ]
    roads.sort(key=lambda e: WIDTHS[e["tags"]["highway"]])
    for el in roads:
        p = [box.project(q["lat"], q["lon"], size) for q in el["geometry"]]
        if len(p) > 1:
            d.line(
                p,
                fill=(15, 15, 15),
                width=WIDTHS[el["tags"]["highway"]] * SS,
                joint="curve",
            )

    best = {}
    for el in roads:
        t = el["tags"]
        if t.get("highway") not in MAJOR or not t.get("name"):
            continue
        g = el["geometry"]
        span = abs(g[0]["lat"] - g[-1]["lat"]) + abs(g[0]["lon"] - g[-1]["lon"])
        if span > best.get(t["name"], (0, None))[0]:
            best[t["name"]] = (span, g)
    font = ImageFont.truetype(FONT, 26 * SS)
    for name, (_, g) in best.items():
        mid = g[len(g) // 2]
        x, y = box.project(mid["lat"], mid["lon"], size)
        if not (60 * SS < x < size - 60 * SS and 30 * SS < y < size - 30 * SS):
            continue
        bb = d.textbbox((x, y), name, font=font, anchor="mm")
        d.rectangle(
            [bb[0] - 6 * SS, bb[1] - 3 * SS, bb[2] + 6 * SS, bb[3] + 3 * SS],
            fill="white",
        )
        d.text((x, y), name, font=font, fill=(70, 70, 70), anchor="mm")

    draw_markers(d, box, size, SS, pubs, landmarks, centre_label, names=True)
    img.resize((OUT_PX, OUT_PX), Image.LANCZOS).save(out, optimize=True)


def build_style_refs(repo_root, out_dir):
    """The Kingston map is the style reference, and it lives in the repo."""
    src = os.path.join(repo_root, "react-ui", "src", "images", "map.png")
    if not os.path.exists(src):
        print(f"  no Kingston map at {src}; skipping style references")
        return []
    im = Image.open(src)
    flat = Image.new("RGB", im.size, "white")
    flat.paste(im, mask=im.split()[3] if im.mode == "RGBA" else None)
    a = os.path.join(out_dir, "01_style_reference_kingston.png")
    b = os.path.join(out_dir, "01b_style_reference_detail.png")
    flat.save(a, optimize=True)
    # A close-up teaches the line quality and the doodles faster than the whole.
    w, h = flat.size
    flat.crop((int(w * 0.46), int(h * 0.48), int(w * 0.93), int(h * 0.88))).save(
        b, optimize=True
    )
    return [a, b]


# --------------------------------------------------------------------------

PROMPT = """# Task: redraw the {title} map in the Kingston hand-drawn style

You are redrawing an existing street map in a different visual style. This is
a TRACING task, not an illustration task. The geometry must come from the
reference images - do not draw a street layout from memory or invent one that
merely looks plausible.

## The reference images

- `01_style_reference_kingston.png` - **STYLE ONLY.** A hand-drawn map of
  Kingston upon Thames. Copy its drawing style. Ignore its geography
  completely: none of its roads, its river or its pubs appear in your output.
- `01b_style_reference_detail.png` - **STYLE ONLY.** A close-up of the same
  map, showing the line quality, the handwriting and the little doodles.
- `02_osm_accurate.png` - an accurate OpenStreetMap rendering of the area.
  GROUND TRUTH for where things are.
- `03_road_skeleton.png` - the same area stripped back to the major roads, the
  water, the parks and labelled markers. Red = pubs, purple = landmarks, blue =
  {centre_label}. **This is the layout to trace.**

## Task

Redraw the area shown in `02_osm_accurate.png` and `03_road_skeleton.png` in
the hand-drawn style of the two Kingston images. Same square extent, same
framing, north up. Do not crop, rotate, zoom or re-centre: {centre_label} is at
the exact centre of `03_road_skeleton.png` and must be at the exact centre of
your output.

## What must be accurate - this matters more than the styling

1. **Road layout.** Every road you draw must be a real road from
   `03_road_skeleton.png`, in the right place, running in the right direction,
   meeting the same roads at the same junctions.
2. **Marker positions.** Each labelled marker must sit on the correct side of
   the correct street, within about a block of where it is in
   `03_road_skeleton.png`. Use the same names.
3. **Nothing invented.** Do not add roads, bridges, parks or water that are not
   in `03_road_skeleton.png`. Fewer roads is fine and expected. Wrong roads is
   not.

You may SIMPLIFY heavily. Drop minor streets, mews and cul-de-sacs. Keep every
road a pub sits on. Aim for roughly the density of road detail in the Kingston
map - much sparser than a real street map, and that is the point.

## Style to copy from the Kingston images

- Black ink line drawing on plain white. No colour anywhere, no grey fills, no
  shading, no hatching, no texture, no paper grain, no photographic effects.
- Loose, wobbly freehand pen lines of a single thin weight, as if drawn with a
  fine liner by hand. Lines should waver and not be perfectly straight or
  parallel. Slightly scruffy is correct.
- Roads are drawn as their two EDGES: a pair of roughly parallel wobbly lines
  forming an empty white corridor, not a solid black stroke. The blocks between
  roads are left completely empty and white.
- Water is drawn as long wobbly outlines, white inside, with at most a couple
  of small squiggles to suggest it.
- Label the pubs and landmarks in small, casual, handwritten-looking script,
  each with a short curved arrow pointing to its exact spot. Label a handful of
  the main streets in the same hand, written along the line of the road.
- Next to most pubs, draw a tiny naive cartoon doodle punning on its name, in
  the same scratchy pen, the way the Kingston map has a cartwheel for
  Wheelwrights Arms, a swan for The Swan and a mill wheel for The Mill. Keep
  them small, crude and charming, not polished illustrations.
- Write the title "{title_upper}" across the top in large hand-drawn outlined
  block capitals, in the style of "KINGSTON" in the Kingston map.
- Leave plenty of white space. The Kingston map is mostly empty paper.

## The pubs, and the street each is on

Cross-check every one against `03_road_skeleton.png`.

{pub_table}
{landmark_block}
## Output

A single square image, black ink on white, no border or frame, no legend, no
compass rose, no scale bar.

Before you finish, check your drawing against `03_road_skeleton.png` once
more: is {centre_label} still at the exact centre, is every pub on the right
street, and does every road you drew exist in the reference?
"""


def write_prompt(path, name, box, pubs, landmarks, centre_label):
    rows = ["| # | Pub | Street |", "|---|-----|--------|"]
    for i, p in enumerate(pubs, 1):
        rows.append(f"| {i} | {p['name']} | {p['street'] or 'see the skeleton'} |")
    lm = ""
    if landmarks:
        lm = (
            "\n## Also mark\n\n"
            + "".join(f"- **{x['name']}**\n" for x in landmarks)
            + f"- **{centre_label}** - at the dead centre of the map.\n"
        )
    title = name.replace("_", " ").replace("-", " ").title()
    open(path, "w").write(
        PROMPT.format(
            title=title,
            title_upper=title.upper(),
            centre_label=centre_label,
            pub_table="\n".join(rows),
            landmark_block=lm,
        )
    )


def venue_snippet(name, box, pubs, landmarks, centre_label, width_px):
    def key(s):
        out = "".join(c if c.isalnum() else "_" for c in s.upper())
        return "_".join(x for x in out.split("_") if x)

    lines = [f'        "{key(centre_label)}": ' f"({box.centre[0]}, {box.centre[1]}),"]
    for x in landmarks + pubs:
        lines.append(f'        "{key(x["name"])}": ({x["lat"]}, {x["lon"]}),')
    return f"""{name.upper()} = Venue(
    name="{name.replace("_", " ").title()}",
    map=VenueMap(
        image="{name}",
        width_px={width_px},
        height_px={width_px},
        ref_1=MapReferencePoint(
            x=0, y=0, lat={box.north:.6f}, long={box.west:.6f}
        ),
        ref_2=MapReferencePoint(
            x={width_px}, y={width_px}, lat={box.south:.6f}, long={box.east:.6f}
        ),
        corner_width_km=0.2,
    ),
    landmarks={{
{chr(10).join(lines)}
    }},
)"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True, help="venue key, e.g. westminster")
    ap.add_argument("--centre", required=True, help="LAT,LON of the map centre")
    ap.add_argument(
        "--half-span",
        type=float,
        required=True,
        help="metres from centre to edge; the map is 2x this square",
    )
    ap.add_argument(
        "--centre-label",
        default="Home",
        help="what to call the centre point on the map",
    )
    ap.add_argument(
        "--landmark",
        action="append",
        default=[],
        metavar="NAME:LAT,LON",
        help="repeatable",
    )
    ap.add_argument(
        "--max-pubs",
        type=int,
        default=14,
        help="keep this many nearest to the centre (default 14)",
    )
    ap.add_argument(
        "--exclude", action="append", default=[], help="pub name to drop; repeatable"
    )
    ap.add_argument("--include-bars", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    lat, lon = (float(x) for x in args.centre.split(","))
    box = Box(lat, lon, args.half_span)
    os.makedirs(args.out, exist_ok=True)

    landmarks = []
    for spec in args.landmark:
        nm, coords = spec.rsplit(":", 1)
        la, lo = (float(x) for x in coords.split(","))
        if not box.inside(la, lo):
            raise SystemExit(
                f"landmark {nm!r} is outside the crop. Widen --half-span: it "
                f"needs at least {haversine((lat, lon), (la, lo)):.0f} m plus "
                f"room to draw."
            )
        landmarks.append(dict(name=nm, lat=la, lon=lo))

    print("fetching pubs...")
    pubs = fetch_pubs(box, args.include_bars)
    dropped = [p for p in pubs if not box.inside(p["lat"], p["lon"])]
    pubs = [
        p
        for p in pubs
        if box.inside(p["lat"], p["lon"]) and p["name"] not in args.exclude
    ][: args.max_pubs]

    print("fetching roads and water...")
    els = fetch_features(box)

    print("stitching tiles...")
    osm = fetch_tiles(box, os.path.join(args.out, ".tilecache"))
    d = ImageDraw.Draw(osm)
    draw_markers(d, box, OUT_PX, 1, pubs, landmarks, args.centre_label, names=False)
    p_osm = os.path.join(args.out, "02_osm_accurate.png")
    osm.save(p_osm, optimize=True)

    print("rendering skeleton...")
    p_skel = os.path.join(args.out, "03_road_skeleton.png")
    build_skeleton(els, box, pubs, landmarks, args.centre_label, p_skel)

    repo = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )
    refs = build_style_refs(repo, args.out)

    p_prompt = os.path.join(args.out, "prompt.md")
    write_prompt(p_prompt, args.name, box, pubs, landmarks, args.centre_label)

    meta = dict(
        name=args.name,
        centre=[lat, lon],
        half_span_m=args.half_span,
        centre_label=args.centre_label,
        size_px=OUT_PX,
        bounds=dict(north=box.north, south=box.south, east=box.east, west=box.west),
        markers=[dict(name=args.centre_label, lat=lat, lon=lon, kind="centre")]
        + [dict(kind="landmark", **x) for x in landmarks]
        + [dict(name=p["name"], lat=p["lat"], lon=p["lon"], kind="pub") for p in pubs],
    )
    for m in meta["markers"]:
        m["x_frac"], m["y_frac"] = box.frac(m["lat"], m["lon"])
    p_meta = os.path.join(args.out, "meta.json")
    json.dump(meta, open(p_meta, "w"), indent=1)

    side = 2 * args.half_span
    print(f"\nwrote {args.out}/")
    for f in refs + [p_osm, p_skel, p_prompt, p_meta]:
        print(f"  {os.path.basename(f)}")
    print(f"\ncrop {side:.0f} x {side:.0f} m, {side/OUT_PX:.2f} m/px at {OUT_PX}px")
    print(f"  NW (0,0)  lat={box.north:.6f} long={box.west:.6f}")
    print(f"  SE (w,h)  lat={box.south:.6f} long={box.east:.6f}")
    print(f"\n{len(pubs)} pubs on the map:")
    for i, p in enumerate(pubs, 1):
        print(f"  {i:2}. {p['name']}  ({p['dist']:.0f} m)  {p['street']}")
    if dropped:
        print(f"\n{len(dropped)} outside the crop, dropped:")
        for p in dropped:
            print(f"      {p['name']}  ({p['dist']:.0f} m)")
    print(
        "\nvenue snippet once you have the drawing (width_px is a placeholder,\n"
        "check_venue_map.py prints it with the real size):\n"
    )
    print(venue_snippet(args.name, box, pubs, landmarks, args.centre_label, OUT_PX))


if __name__ == "__main__":
    main()
