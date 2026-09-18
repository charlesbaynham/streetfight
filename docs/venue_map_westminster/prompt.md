# Task: redraw the Westminster map in the Kingston hand-drawn style

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
  the centre crosshair. **This is the layout to trace.**

## Task

Redraw the area shown in `02_osm_accurate.png` and `03_road_skeleton.png` in
the hand-drawn style of the two Kingston images. Same square extent, same
framing, north up. Do not crop, rotate, zoom or re-centre: the thin blue crosshair on `03_road_skeleton.png` marks the exact centre of the frame, and that same point must fall at the exact centre of your output. It is a framing guide, not a place: nothing stands there, so do not draw the crosshair and do not label it.

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
- Write the title "WESTMINSTER" across the top in large hand-drawn outlined
  block capitals, in the style of "KINGSTON" in the Kingston map.
- Leave plenty of white space. The Kingston map is mostly empty paper.

## The pubs, and the street each is on

Cross-check every one against `03_road_skeleton.png`.

| # | Pub | Street |
|---|-----|--------|
| 1 | Royal Oak | 2 Regency Street |
| 2 | The Loose Box | 51 Horseferry Road |
| 3 | White Horse | 86 Horseferry Road |
| 4 | Barley Mow | 104 Horseferry Road |
| 5 | Marquis of Granby | 41 Romney Street |
| 6 | Windsor Castle | 23 Francis Street |
| 7 | The Greencoat Boy | Greencoat Place |
| 8 | The Speaker | 46 Great Peter Street |
| 9 | Grafton Arms | 2 Strutton Ground |
| 10 | Munich Cricket Club | 1 Abbey Orchard Street |
| 11 | Buckingham Arms | 62 Petty France |
| 12 | The Feathers | 18-20 Broadway |
| 13 | Adam and Eve | 81 Petty France |
| 14 | Sanctuary House | 33 Tothill Street |
| 15 | Blue Boar | 41-47 Tothill Street |
| 16 | The Old Star | 66 Broadway |
| 17 | Westminster Arms | 9 Storey's Gate |
| 18 | Two Chairmen | 39 Dartmouth Street |
| 19 | St Stephen's Tavern | 10 Bridge Street |

## Also mark

- **House Absolute**
- **Big Ben**
- **Westminster Abbey**
- **Parliament**

## Output

A single square image, black ink on white, no border or frame, no legend, no
compass rose, no scale bar.

Before you finish, check your drawing against `03_road_skeleton.png` once
more: does the point under the blue crosshair still sit at the exact centre, is every pub on the right street, and does every road
you drew exist in the reference?
