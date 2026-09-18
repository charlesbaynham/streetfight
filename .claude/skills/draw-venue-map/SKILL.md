---
name: draw-venue-map
description: Make a hand-drawn-style map for a new streetfight venue - fix the play area, find the pubs and landmarks inside it, render OpenStreetMap references, hand the user a prompt for Gemini, then check what comes back and wire it into backend/venues.py. Use when the game moves to a new town or area, when a venue needs re-cropping, or whenever someone asks for a new map.
---

# Draw a map for a new venue

The Kingston map is hand-drawn and that is the house style. The output here is
a georeferenced image plus a `Venue` for `backend/venues.py`.

**Render it. Do not ask an image model for the map.** `render_venue_map.py`
draws the OpenStreetMap geometry with a wobbly pen and a handwriting font,
which is exact by construction and free to re-run. The image model is asked
only for the *doodles* — one little pen sketch per pub, on plain white, which
the renderer then places (see "Doodles" below). The whole-map image-model
route is kept at the foot of this file as a record of it failing repeatedly
rather than an opinion — see "Why not an image model".

## The short version

```bash
# once per venue, or whenever the pub list changes
./docs/venue_map_<name>/build.sh          # fetches OSM, writes the bundle
uv run python .claude/skills/draw-venue-map/scripts/render_venue_map.py \
    --bundle docs/venue_map_<name> \
    --out react-ui/src/images/map_<name>.jpg \
    --title <NAME>
```

Then wire it in (below). `build.sh` caches the OSM features in the bundle as
`osm_features.json.gz`, so re-rendering costs nothing and asks Overpass
nothing; `--refetch` forces a new query when the area itself has changed.

The renderer labels **every marker in `meta.json`**, which is every landmark
in the venue. Adding a pub and re-running is the whole change — there is no
step where a human or a model has to redraw anything. (Give the new pub a
line in `doodles.json` and run `doodle_venue_map.py` too, or it is the one
pub on the map without a drawing.)

## Doodles

The cartwheel beside Wheelwrights Arms is the charm of the Kingston map, and
it is the one thing an image model *can* do here: a doodle carries no
geometry to get wrong. `docs/venue_map_<name>/doodles.json` lists a subject
per pub — `{"marker": "Royal Oak", "subject": "an oak tree"}`, or `"at":
[lat, lon]` for a boat on the river — and:

```bash
uv run python .claude/skills/draw-venue-map/scripts/doodle_venue_map.py \
    --bundle docs/venue_map_<name> --dry-run     # what it would ask for
OPENROUTER_API_KEY=... uv run python .claude/skills/draw-venue-map/scripts/doodle_venue_map.py \
    --bundle docs/venue_map_<name>               # ~$0.04 a drawing at Gemini Flash
```

asks `google/gemini-3.1-flash-image` (OpenRouter's Image API) for **black
felt-tip on pure white**, then makes the transparency itself — luminance
becomes alpha, the paper drops out, the ink is recoloured to the map's sepia
— and writes `doodles/<pub>.<hash>.png` into the bundle. It is
content-addressed on the model and the whole prompt, so re-running when
nothing changed spends nothing, and editing one subject redraws one drawing.
The raw answers are cached under `doodles/raw/` (not committed) so
`--reprocess` can re-tune the ink conversion for free. Then re-run
`render_venue_map.py`: it puts each drawing beside its pub, on the far side
from the name, in the emptiest patch of paper within reach — never over a
label, a road, or the point the arrow is aimed at — and says which doodles
are still undrawn or found no room. `"pin": [x, y]` (fractions of the
sheet) overrides that search for one entry and centres it there: for a
drawing that *is* the place, like the Palace of Westminster along its own
riverbank, drawn at `"size": 330`. Neither `size` nor `pin` changes the
drawing's address, so tuning them costs nothing. **The model never sees the map**, so it
cannot move anything on it; that is the whole difference from the route
below.

## Colour

Sepia paper, with the water and the parks coloured in. The four constants at
the top of `render_venue_map.py` are the whole palette:

| | |
| --- | --- |
| `PAPER` `#f2e7d0` | the sheet — **and the road corridors**, which are this rather than white |
| `INK` `#000000` | every line and every word |
| `WATER` `#a9c6d6` | |
| `PARK` `#c9d7ab` | |

Two things about how the colour is laid on:

- **The fill and the ink edge come from one path.** `draw_area` clips the ring
  to the sheet, wobbles it, then fills it *and* inks it. Colouring the survey
  geometry while wobbling the pen separately left the river with a stepped,
  machine-cut edge under a hand-drawn line.
- **Clipping introduces edges that are not banks.** A ring clipped to the
  sheet gains segments running along the border; `edge_runs` drops those
  before inking, or the map gets a box drawn round it.

A multipolygon relation — the Thames here — arrives as member ways, each an
open arc ending where the next begins, so nothing is fillable until they are
chained (`closed_rings`). Closing an arc on itself instead draws a chord
across the map. `build_venue_map.py` recovers the same region by flooding a
bitmap from a seed in midstream, which is what you cannot do to a vector; the
skeleton still does it that way and is fine, because nobody fills a reference
image.

## Three layers, and replacing one

Beside the raster it writes four SVGs — `<name>.svg`, `<name>.map.svg`,
`<name>.doodles.svg` and `<name>.hand.svg`. The drawing is built in three
layers:

| Layer | What is on it |
| --- | --- |
| `map` | roads, water, parks |
| `doodles` | the generated drawings, as embedded PNGs |
| `handwriting` | every word on the sheet, and the arrows that point at things |

Each is a `<g>` in the combined file and the only thing in its own file, so
stacking map, doodles, handwriting reproduces the whole exactly (verified: the
layers composite back to the combined with no difference beyond glyph
antialiasing). The words are real `<text>` in an embedded font rather than
outlines, so they can be edited as text as well as redrawn.

The arrows sit with the handwriting, not the map, because they belong to the
words: where a name goes is decided by what room is left, and the arrow is
what keeps it honest about which pub it means.

**To re-letter the map by hand:**

1. Edit `<name>.hand.svg` — or throw it away and draw your own, in the same
   2000 × 2000 coordinate space.
2. `render_venue_map.py --combine-only` rebuilds `<name>.svg` by stacking the
   two layer files **as they are on disk**. It is pure text; nothing about
   your lettering has to be understood.
3. Rasterise that over `<name>.jpg` yourself — Inkscape, or a browser — since
   that is the file the app and the poster load.

**The renderer will not overwrite lettering.** Every file it writes is signed
with a hash of its own contents; a file that does not match its signature is
somebody's work, and re-rendering refuses and names it. `--force` throws the
edit away deliberately, `--no-svg` refreshes only the raster. The same goes
for the doodles layer: somebody who redraws the pelican by hand in
`<name>.doodles.svg` keeps it.

## The workflow for the references (and the image-model route)

1. **Centre.** Ask the user. It is normally the house the game runs from, and
   it becomes the middle of the map.
2. **Edges.** The user's call, but it is usually forced rather than chosen —
   see *Sizing the play area* below. Put the arithmetic in front of them.
3. **Landmarks and pubs.** Yours. `build_venue_map.py` pulls every pub inside
   the crop from OpenStreetMap and ranks them by distance from the centre; you
   pass the landmarks worth drawing. Then curate: a hand-drawn map carries
   about twenty markers before it turns to soup. If the list is already
   settled — a game is played on the pubs somebody chose, not on the
   nearest N — pass them with `--pub` and skip the search entirely.
4. **Render the references.** `build_venue_map.py` again.
5. **Hand over the prompt.** It writes `prompt.md` for this venue. Give the
   user the prompt *and* the four images.
6. **Get the drawing back** from the user.
7. **Check it,** with `check_venue_map.py`. Then wire it in, or go round again.

## Sizing the play area

The map is always a square, symmetric about its centre, so the size follows
from where the centre is. **Ask first whether the centre has to be a place at
all** — that is the choice that decides how much paper the drawing gets, and
it is easy to miss:

- **Pinned to a place.** Some landmark sits at the dead centre. Then a marker
  *d* metres away forces a half-span of at least *d*, plus enough margin to
  draw it in — about 100 m.
- **Sized to the markers.** Nothing is pinned, so the centre is the middle of
  the markers' bounding box and the half-span is the tightest that fits them.

Westminster shows the difference. Pinned to House Absolute, Big Ben 537 m
north forced 650 m, giving 1300 × 1300 m. Freed, the same nineteen pubs and
four landmarks fit inside 458 m of their own centre, and 575 m — 1150 × 1150 m
— leaves every one of them at least 117 m of drawing room. That is a quarter
less ground for the same sheet of paper.

The Kingston map covers 1153 × 1116 m, which is a good sanity check either
way: much bigger and the drawing gets too sparse to navigate by.

Put the arithmetic in front of the user rather than asking them for a number.
`build_venue_map.py` refuses a landmark outside the crop and tells you the
minimum half-span it needs.

### A centre with nothing on it

Pass `--centre-label ""` when the centre is only a framing point. The skeleton
then gets a thin blue crosshair there instead of a labelled marker, the prompt
tells the model to keep that point at the centre *without drawing or labelling
it*, and `meta.json` leaves it out of the markers — otherwise
`check_venue_map.py` rings a spot with nothing under it and every overlay
looks like a failure.

The framing still matters exactly as much: the venue's reference points are
the crop's corners, so a drawing that re-crops is unusable however good it
looks. Freeing the centre changes which corners those are, so `ref_1` and
`ref_2` in `backend/venues.py` move with the image, not before it.

## Building the references

```bash
uv run python .claude/skills/draw-venue-map/scripts/build_venue_map.py \
    --name westminster \
    --centre 51.4958738,-0.1309233 \
    --half-span 650 \
    --centre-label "House Absolute" \
    --landmark "Big Ben:51.50073,-0.12462" \
    --landmark "Westminster Abbey:51.49940,-0.12764" \
    --max-pubs 10 \
    --out /tmp/venue_westminster
```

Writes into `--out`:

| File | What it is for |
| --- | --- |
| `01_style_reference_kingston.png` | **Style only.** The Kingston map, from `react-ui/src/images/map.png`. |
| `01b_style_reference_detail.png` | **Style only.** A close-up — teaches the line quality and the doodles faster than the whole map. |
| `02_osm_accurate.png` | The real OSM rendering of the crop, markers pinned. Ground truth. |
| `03_road_skeleton.png` | Roads, water, parks and named markers only. **The thing to trace.** |
| `prompt.md` | The prompt, with this venue's pubs and landmarks filled in. |
| `meta.json` | Feeds `check_venue_map.py`. |

It also prints the crop corners, the pubs it kept, the pubs the crop dropped,
and a `Venue` snippet.

`--exclude "Name"` drops a pub by name; `--include-bars` widens the search
beyond `amenity=pub`. Re-run freely — tiles are cached under `.tilecache`.

`--pub "Name:LAT,LON:Street"` gives a pub outright. Any use of it replaces
the OpenStreetMap search, so the markers are exactly the list passed,
numbered in the order given rather than by distance — which is what you want
when the venue already exists and its pub list is the one a game will be
played on. A named pub outside the crop is an error rather than a silent
drop. `docs/venue_map_westminster/build.sh` is a worked example: the
nineteen Westminster pubs, straight out of `backend/venues.py`.

## Handing it to the user

Give them `prompt.md` **and** all four images, and say the images map to
"Image 1–4" in the order above. Do not paraphrase the prompt: the parts that
look like padding ("this is a TRACING task, not an illustration task", "do not
crop, rotate, zoom or re-centre") are the parts doing the work.

## Checking the drawing

`check_venue_map.py` works on a rendered map as well as a generated one, and
is still worth running: it is an end-to-end check that the image, `meta.json`
and the venue's reference points agree.

## Checking what an image model sends back

```bash
uv run python .claude/skills/draw-venue-map/scripts/check_venue_map.py \
    --meta /tmp/venue_westminster/meta.json \
    --drawn ~/Downloads/whatever-they-sent.png
```

Writes `05_check_overlay.png`: the drawing with a ring at every position the
marker *should* occupy. **Look at it.** Every ring should sit on its own
hand-drawn label. Rings landing in open space mean the model composed rather
than traced, and one bad marker means the whole drawing is suspect — they fail
in groups, not singly.

It also prints the `Venue` snippet with the real image size filled in.

## Wiring it in

1. Save the drawing as `react-ui/src/images/map_<name>.jpg`.
2. Add one import and one key to `react-ui/src/mapImages.js`.
3. Paste the snippet into `backend/venues.py`, add it to `VENUES`, and point
   `ACTIVE_VENUE` at it.
4. `uv run pytest tests/test_venues.py` — the tests are parametrized over
   `VENUES`, so they check every landmark is on the map and that the image key
   is one the frontend actually bundles.
5. Run the app (see the `run-mobile-app` skill) with a fake GPS fix at the
   centre. The player's dot should land on the centre point *drawn on the map*.
   That checks the georeferencing against the artwork, which the arithmetic
   cannot.

## Why not an image model

Kept because somebody will suggest it again. Westminster was attempted many
times, across every image model Gemini offers and the whole of OpenRouter's
image-output roster, and the failures were consistent:

- **They do not trace, they resynthesise.** Asked to "draw a map of X" from
  the same references, a model produces something that looks like a map of
  somewhere. On the first Westminster attempt six of ten pubs were wrong,
  three by 500–840 m, and the whole central street grid was shuffled.
- **"Roads in the wrong place" and "wrong scale" are one bug, not two.**
  Nothing in the architecture preserves metric geometry, so each generation
  rolls the dice on both at once. The framing is what the georeferencing
  depends on, so a re-crop is fatal however good the drawing.
- **Never ask a good result to fix small errors.** A four-item correction
  request on the one good Westminster map triggered a full redraw that
  scrambled eight of ten pubs — and misspelled its own title, which is the
  giveaway. A correction is a re-roll with the good result thrown away.
- **A good result was luck, and luck does not repeat.** The same prompt and
  images gave a scrambled map on one model and a near-exact trace on another,
  and then never again. That is what finally motivated the renderer: the
  geometry was always available in the OSM data, and a hand-drawn look is a
  rendering style rather than a creative act.

## Gotchas (learned the hard way)
- **Reference points come from the crop's corners**, never from eyeballing
  landmarks — the corners are exact by construction, so long as the drawing
  keeps the framing. This is why the prompt is so insistent about not cropping.
  If the returned image is not square, the framing changed and the
  georeferencing is gone; regenerate.
- **Landmarks should only be things drawn on the map.** An admin places circles
  by picking a landmark, and a circle somewhere invisible is worse than no
  circle.
- **`corner_width_km` scales with resolution.** Kingston is 0.51 m/px and uses
  0.115. A model's 1024 px output over 1300 m is 1.27 m/px, where 0.115 shows
  ninety pixels of blur — 0.2 is about right. Check it in the running app.
- **Overpass is flaky.** All four endpoints being down at once is normal; the
  script sweeps them three times before giving up. If it does give up, wait and
  re-run — the tile cache means only the queries repeat.
- **OSM tiles are a donation.** The script caches, sleeps between requests and
  sends a real User-Agent. Keep crops modest — a 1300 m box at zoom 17 is about
  56 tiles. Do not loop it.
- **Water is usually a multipolygon** whose members Overpass clips to the
  bounding box, so its rings do not close. Filling them directly floods half
  the map — this happened. The script draws the banks and floods inward from a
  seed, accepting one only if the fill reaches the image edge, since real water
  always leaves the frame.
