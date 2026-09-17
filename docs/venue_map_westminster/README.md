# The Westminster map redraw — what to do with this folder

Milestone M0.6, roadmap #12's outstanding half. The map in the app was traced
when the pub list was ten pubs long; the list is now nineteen, and eleven of
them have no marker on the drawing. This folder is the bundle for asking an
image model to trace it again against the real list. **It needs one human
step: running the prompt.**

## The one step

Open a new chat with an image-capable model (Gemini was what worked last
time), attach **all four images** in this order, and paste **the whole of
`prompt.md`**:

| Attach as | File |
| --- | --- |
| Image 1 | `01_style_reference_kingston.png` |
| Image 2 | `01b_style_reference_detail.png` |
| Image 3 | `02_osm_accurate.png` |
| Image 4 | `03_road_skeleton.png` |

Do not paraphrase the prompt. The parts that read like padding — "this is a
TRACING task, not an illustration task", "do not crop, rotate, zoom or
re-centre" — are the parts doing the work. The first Westminster attempt was
asked to *draw* rather than trace and put six of ten pubs in the wrong place,
three of them by 500–840 m.

Save what comes back and hand it to the session working this milestone, or
check it yourself:

```bash
uv run python .claude/skills/draw-venue-map/scripts/check_venue_map.py \
    --meta docs/venue_map_westminster/meta.json \
    --drawn ~/Downloads/whatever-it-sent.png
```

That writes `05_check_overlay.png`: the drawing with a ring at every place a
marker *should* be. **Look at it.** Every ring should land on its own
hand-drawn label. Rings in open street mean the model composed instead of
tracing, and one bad marker condemns the whole drawing — they fail in groups.

## Two rules that cost us a good map last time

- **If it comes back wrong, re-roll — do not ask for corrections.** A
  four-item correction request on the good Westminster map triggered a full
  redraw that scrambled eight of ten pubs. Corrections are not cheap here,
  they are a re-roll with the good result thrown away.
- **If it composes, change the model before changing the prompt.** The same
  prompt and images gave a scrambled map on one model and a near-exact trace
  on another.

## The crop changed on 17 September

It used to be pinned to House Absolute — the crop symmetric about it, which
forced 1300 × 1300 m because Big Ben is 537 m north. Nothing actually needs
House Absolute at the centre, so the crop is now sized to the markers instead:
the centre is the middle of the nineteen pubs, Big Ben, Parliament, the Abbey
and House Absolute, and the half-span is the tightest that fits them with room
to draw.

That makes it **1150 × 1150 m**, a quarter less ground on the same sheet of
paper, which is the whole point of redrawing — nineteen pubs in the middle of
a 1300 m square is what made the old one hard to read. It also lands within
3 m of the Kingston map's 1153 m, the size this style is tuned for. Every
marker has at least 117 m to the nearest edge; Parliament, Windsor Castle and
Big Ben are the three closest to one.

House Absolute is now an ordinary landmark. **Nothing stands at the centre**
(the nearest pub is 105 m away), so the skeleton carries a thin blue crosshair
there instead of a marker, and the prompt tells the model to keep that point
centred without drawing or labelling it.

## What must not move

The framing. 1150 × 1150 m square, north up, the crosshair's point at dead
centre. A drawing that re-crops is unusable however pretty it is, and if what
comes back is not square the framing changed: re-roll.

**The venue's reference points move with the image, not before it.** They
*are* this crop's corners, so `backend/venues.py` needs these the moment the
new drawing is wired in — and must keep the old ones until then, because they
describe the map that is live:

```python
ref_1=MapReferencePoint(x=0, y=0, lat=51.502881, long=-0.139506),
ref_2=MapReferencePoint(x=W, y=H, lat=51.492481, long=-0.122912),
```

(was 51.501752, −0.140302 and 51.489995, −0.121544.) `corner_width_km` wants a
look too: 0.2 was chosen for 1300 m across 1024 px, and both numbers change.

## The files

| File | What it is |
| --- | --- |
| `build.sh` | Exactly how this bundle was made. Re-runnable. |
| `prompt.md` | The prompt, with this venue's nineteen pubs filled in. |
| `01_*`, `02_*`, `03_*` | The four references above. |
| `meta.json` | Where every marker belongs; feeds `check_venue_map.py`. |

The pubs were passed to the builder by hand rather than searched for on
OpenStreetMap, because the nineteen are Charles's choice and a nearest-N
search returns a different set. That is what `--pub` is for.

`check_venue_map.py` rings the 23 markers and not the centre — there is
nothing drawn under the crosshair, so a ring there would look like a failure
on every overlay.

The `Venue` snippet `build.sh` prints at the end is **not** to be pasted over
`backend/venues.py`: the names here are how people say them, so the keys it
derives (`THE_SPEAKER`, `ST_STEPHEN_S_TAVERN`) are not the keys the rest of
the code uses. Only the image file and its `width_px` / `height_px` change
when the drawing lands.
