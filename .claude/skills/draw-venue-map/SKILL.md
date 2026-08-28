---
name: draw-venue-map
description: Make a hand-drawn-style map for a new streetfight venue - fix the play area, find the pubs and landmarks inside it, render OpenStreetMap references, hand the user a prompt for Gemini, then check what comes back and wire it into backend/venues.py. Use when the game moves to a new town or area, when a venue needs re-cropping, or whenever someone asks for a new map.
---

# Draw a map for a new venue

The Kingston map is hand-drawn and that is the house style. Until someone draws
the new one by hand, an image model can produce a passable stand-in — but only
if it is made to **trace** an accurate reference rather than illustrate a place
it half-remembers. Everything below exists to force that.

The output is a georeferenced image plus a `Venue` for `backend/venues.py`.

## The workflow

1. **Centre.** Ask the user. It is normally the house the game runs from, and
   it becomes the middle of the map.
2. **Edges.** The user's call, but it is usually forced rather than chosen —
   see *Sizing the play area* below. Put the arithmetic in front of them.
3. **Landmarks and pubs.** Yours. `build_venue_map.py` pulls every pub inside
   the crop from OpenStreetMap and ranks them by distance from the centre; you
   pass the landmarks worth drawing. Then curate: a hand-drawn map carries
   about twenty markers before it turns to soup.
4. **Render the references.** `build_venue_map.py` again.
5. **Hand over the prompt.** It writes `prompt.md` for this venue. Give the
   user the prompt *and* the four images.
6. **Get the drawing back** from the user.
7. **Check it,** with `check_venue_map.py`. Then wire it in, or go round again.

## Sizing the play area

Three constraints usually pin the size down, and it is worth showing the user
that rather than asking them to pick a number:

- the centre is at the middle of the map,
- the map is symmetric about it,
- some landmark must be in frame.

A landmark *d* metres from the centre therefore forces a half-span of at least
*d*, plus enough margin to draw it in — about 100 m. For Westminster, Big Ben
is 537 m north of the house, so 650 m was the smallest half-span that worked,
giving 1300 × 1300 m. The Kingston map covers 1153 × 1116 m, which is a good
sanity check: much bigger and the drawing gets too sparse to navigate by.

`build_venue_map.py` refuses a landmark outside the crop and tells you the
minimum half-span it needs.

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

## Handing it to the user

Give them `prompt.md` **and** all four images, and say the images map to
"Image 1–4" in the order above. Do not paraphrase the prompt: the parts that
look like padding ("this is a TRACING task, not an illustration task", "do not
crop, rotate, zoom or re-centre") are the parts doing the work.

## Checking what comes back

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

## Gotchas (learned the hard way)

- **Tracing, not illustration.** Asked to "draw a map of X" from the same
  references, a model produces something that looks like a map of somewhere.
  On the first Westminster attempt six of ten pubs were wrong, three by
  500–840 m, and the whole central street grid was shuffled. The attempt told
  to trace the skeleton put every pub within about 20 m.
- **Never ask a good result to fix small errors.** A four-item correction
  request on the good Westminster map triggered a full redraw that scrambled
  eight of ten pubs — and misspelled its own title, which is the giveaway. If
  something is wrong, either live with it or regenerate from scratch.
  Corrections are not cheap here, they are a re-roll.
- **The model matters more than the prompt.** The same prompt and images gave a
  scrambled map on one model and a near-exact trace on another. If the first
  attempt composes, try a different model before rewriting anything.
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
