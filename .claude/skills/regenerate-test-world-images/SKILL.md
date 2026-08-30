---
name: regenerate-test-world-images
description: Rebuild the deterministic thirty-player test world and its generated photographs - the cast, the simulated hour of telemetry, the ten shot scenes, the images themselves, and the crops the demo game fires. Every image costs real money at an image model, so use this whenever a scene description, a palette, an outfit or the world seed changes, and before spending anything on `generate` or `observe`.
---

# Regenerate the test world

`backend/test_world/` is the deterministic sample game: thirty players dealt to
locked counts, an hour of simulated movement and phone-shaped telemetry over
the real venue, ten shot scenarios *selected* out of the encounter pool, and a
content-addressed store of generated photographs. `data/world.json` is the
single source of truth; everything else is derived from it.

**Two of the seven steps spend money at OpenRouter. The rest are free.** That
asymmetry is the whole reason this skill exists — get the free steps right and
reviewed before paying for anything.

## The pipeline

Run from the repo root. Prefix with `uv run` (or use `.venv/bin/python`)
unless you are inside `nix develop`.

| Step | Command | Cost |
| --- | --- | --- |
| 1 | `python -m backend.test_world world` | free |
| 2 | `python -m backend.test_world gate` | free |
| 3 | `python -m backend.test_world scenes` | free |
| 4 | `python -m backend.test_world gateb` | free |
| 5 | `python -m backend.test_world generate` → `--execute` | **~$0.04/image** |
| 6 | `python -m backend.test_world observe` → `--execute` | **~$0.003/image** |
| 7 | `python -m backend.test_world shots` (`npm run demoshots`) | free |

`--seed` (default `20260919`, the game date) and `--out` (default
`backend/test_world/data/world.json`) apply throughout.

### 1–2. Build the world, then read it

`world` rebuilds `world.json` from the seed alone, in a throwaway database. It
**carries the localisation boxes forward** from the previous file — those were
bought one at a time, are keyed by image id, and stay true however the world
around them is rebuilt. They went twice before that carry-forward existed.

`gate` prints the Gate A summary: teams and their colours, how the telemetry
actually came out, the encounter pool. Read it — a world that drifted is
usually one wrong key.

`check` proves the seed determines the world completely: it builds twice and
compares. Run it if you touched anything under `backend/test_world/`.

### 3–4. Select and describe the scenes, then review every prompt

`scenes` picks the ten shots out of the encounter pool and writes the prompt
for each, plus thirty reference photos and one shared background. It also
re-renders `kit_swatches.png`.

⚠️ **`scenes` rewrites `world["scenes"]` wholesale.** The localisation boxes
live *outside* it, under `world["boxes"]` keyed by image id, precisely so this
does not throw away work that was paid for.

`gateb` prints every prompt for human review — `--only S4` or
`--only references` narrows it. **This is the gate that matters**: a prompt is
the only thing that decides what the picture looks like, and once you have paid
for the picture the only way to change it is to pay again.

`availability` shows which (locale, light, distance) cells the world can
actually serve, flagging the empty ones. Useful when a scenario cannot be cast.

### 5. Generate the images — the money step

```bash
python -m backend.test_world generate            # dry run: says what it would spend
python -m backend.test_world generate --execute  # actually spends
```

**Always dry-run first and read the plan.** Without `--execute` nothing is
sent; it prints each missing image, its model, its price and its image id.

- **Images are content-addressed.** An image id is the hash of its prompt, its
  input images, the model and the parameters. So editing one scene description
  regenerates exactly the images it touches and nothing else, and re-running
  `generate` when nothing changed **sends nothing at all**.
- Reference photos are generated first, then the shots conditioned on them — a
  shot's identity includes its target's reference photo, so it cannot be
  planned until that photo is in the store. `generate` loops until nothing new
  unblocks.
- Models: `bytedance-seed/seedream-5-0-lite` ($0.04), falling back to
  `seedream-5-0-pro` ($0.12). Generation goes through OpenRouter's **Image**
  API (`OpenRouterImageClient`), *not* `/chat/completions`, which does not
  serve image models.
- A **hard ceiling of $8.00** refuses a plan that would commit more.
- `--gate c|d|e` restricts the run to a subset.

Needs `OPENROUTER_API_KEY` in the environment.

### 6. Localise, crop and measure

```bash
python -m backend.test_world observe             # says what it would spend
python -m backend.test_world observe --execute   # buys the missing boxes
```

One vision call per image finds the subject's bounding box (~$0.003 each);
those boxes are cached by image id and never bought twice. The crops and the
colour measurements that follow are **free and rewritten every run**, so a
changed cropping rule takes effect without paying for anything again.

A stored reading with no subject in it is treated as missing and asked for
again — a failure that merely got written down is still a failure.

### 7. Put the shots in the game

`python -m backend.test_world shots` (= `npm run demoshots`) loads the ten
cropped photographs into the sample game as shots somebody fired, walking the
scenarios in tick order and moving the whole cast to the fix each had *at that
tick*. Shot ids come from the seed, so replaying twice is a no-op; `--only S4`
re-loads one. To watch the shots arrive one at a time instead of finding them
all there, use the admin page's **Fire demo game** button
(`backend/demo_game.py`) — note that it clears the database and rebuilds the
sample game from the seed before it fires anything, so it undoes any hand
edits you made to the game first.

## The rules that are not negotiable

- **No Google models in the generation or localisation paths.** An explicit
  guard (`FORBIDDEN_LOCALISATION_PREFIXES`) refuses them. The recogniser under
  test is a Google model, so using one to make or measure its own inputs would
  make the benchmark circular. Localisation uses
  `qwen/qwen3-vl-235b-a22b-instruct`.
- **Measurements are recorded and reported, never acted on.** Nothing
  regenerates an image because a colour came out wrong. If you want a different
  picture, edit the scene description — that is the only lever.
- **Only a checkout ever regenerates a picture.** `world.json` and
  `data/shots/` are declared as package data in `pyproject.toml` and travel
  into every deployment; the generated store (`data/images/`) and the
  generator's inputs deliberately do not.
- The truth track (`data/*.truth.npz`, 2.4 MB) is gitignored and rebuilt
  identically from the seed by `world`.

## Changing a palette or an outfit

`backend/identity/config.py` is **append-only while the game is live** — see
CLAUDE.md. If a change there is agreed, it invalidates every reference photo
whose prompt names a colour that moved, and `generate` will price exactly those
back in. Dry-run it and put the number in front of Charles before spending.
