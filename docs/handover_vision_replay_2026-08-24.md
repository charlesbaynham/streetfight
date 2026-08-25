# Handover: shot-review replay harness run — 2026-08-24

Written for the next session. Covers: what was done, where everything lives,
what the harness returned, and Charles's spec for what the vision agent is
*supposed* to be. Nothing here is committed yet.

## TL;DR

The live database was re-pulled, the fixture set at `tests/fixtures/shot_replay/`
was rebuilt from it (13 shots, all with real admin verdicts and freeform
admin notes), and one baseline `replay` was run. Result: **1 false hit out of
8 non-hits, 4 false misses out of 5 hits** (model
`google/gemini-3.7-flash-20260813`, baseline prompt). The vision model's raw
observations are mostly *right*; the bad outcomes come from (a) the aim-marker
geometry on the false hit, and (b) Python's `classify()` mapping honest
two-channel readings to `hit_bystander` on the false misses.

## Charles's spec for the vision agent (the target behaviour)

From Charles, 2026-08-24, verbatim requirements:

1. **The vision agent must have no concept of codes** — no error-correcting
   code, no codewords, no "valid outfit" idea. (Some AI text in the database
   refers to the error code; it should not. See "The 'code' wording" below —
   that text is Python's, not the model's.)
2. The correct output is either **`request_zoom`** — at which point it gets
   the second, zoomed-in image — or the final answer: **did the shot hit a
   person at all?**
3. If it did **not** hit a person: all four channels are `unknown` / n/a.
4. If it **did** hit a person: for each channel, either a colour or
   `unknown`. **It is not for the vision agent to judge whether the person is
   a player or a bystander.** That decision belongs to the downstream
   algorithm (`backend/shot_vision.classify` today,
   `backend/shot_identification.py` for the full version), based on the
   channels the agent reports, GPS, and the valid codes.
5. Several admin notes expect borderline readings to be **escalated** ("bumped
   up for review by the more powerful agent or possibly ultimately to the
   admin") — a two-tier design that does not exist yet.

## What was done this session

1. **Re-pulled the live DB.** The live system is CT 101 (`streetfight`) on the
   Proxmox host (`ssh homeserver`); its state volume is
   `/mnt/usbpool/data/subvol-9101-disk-0/` on the host, DB at `db/data.db`.
   Pulled with a consistent online backup:

   ```bash
   ssh homeserver "sqlite3 /mnt/usbpool/data/subvol-9101-disk-0/db/data.db '.backup /tmp/sf.db'"
   scp homeserver:/tmp/sf.db data.db && ssh homeserver "rm /tmp/sf.db"
   ```

   `data.db` (gitignored) now holds 13 shots, all adjudicated (`result` set)
   and all carrying freeform `admin_notes` written by Charles.

2. **Rebuilt the fixture set.** `scripts/replay_shot_reviews.py export` was
   extended to carry `admin_notes` into the manifest (previously dropped), and
   `_load_fixture_shots` to read them back. Then:

   ```bash
   rm tests/fixtures/shot_replay/*.jpg tests/fixtures/shot_replay/manifest.json
   python -m scripts.replay_shot_reviews export --db sqlite:///data.db \
       --out tests/fixtures/shot_replay
   ```

   `tests/fixtures/shot_replay/` = 13 photos + `manifest.json` (verdicts +
   notes + the reviews that were stored in the live DB at export time).

3. **Ran the harness once** (baseline prompt, default model):

   ```bash
   python -m scripts.replay_shot_reviews replay \
       --fixtures tests/fixtures/shot_replay \
       --out tests/fixtures/shot_replay/replay_baseline.jsonl \
       --variant baseline --concurrency 3
   python -m scripts.replay_shot_reviews score tests/fixtures/shot_replay/replay_baseline.jsonl
   ```

   13/13 succeeded. Output: `tests/fixtures/shot_replay/replay_baseline.jsonl`.

### Python environment

`nix develop` builds TeXLive from scratch (far too slow); `nix develop .#ci`
is TeX-free but the cache fetch stalled this session. What actually worked is
a pip venv at **`/tmp/opencode/sfenv`** (python 3.12, runtime deps from
`flake.nix`'s `runtimePythonReqs`). Use `/tmp/opencode/sfenv/bin/python` for
harness commands. If it's gone, recreate with any venv + `pip install
python-dotenv qrcode click sqlalchemy pillow sqlalchemy-utils tzdata fastapi
wsproto uvicorn itsdangerous httpx`.

**`OPENROUTER_API_KEY` is commented out in the local `.env`.** The live key
is in `/mnt/usbpool/data/subvol-9101-disk-0/secrets/streetfight.env` on
`homeserver` — source it into the environment before `replay` (do not write
it into the repo).

## Results: baseline replay vs the admin notes

Confusion (admin rows × CharlesBot columns): hit→hit 1, hit→bystander 4;
miss→hit 1, miss→miss 3; bystander→bystander 4. All 13 reviews came back at
confidence ≥ 0.85, so the confident/auto-action subset is the same set.

| shot (prefix) | admin | model outcome | conf | zoom | model's channels (tshirt/trousers/hat/armbands) | vs the note |
|---|---|---|---|---|---|---|
| d91548d3 | miss | **hit_player** | 0.95 | no | purple/black/green/green | **False hit** — see below |
| d1c4e6ad | bystander | hit_bystander | 0.85 | yes | purple/black/?/? | matches note (marginal hit, zoom needed) |
| d276f718 | hit | hit_bystander | 0.85 | yes | purple/black/?/? | channels exactly per note; killed by classify |
| 697899ee | hit | hit_bystander | 0.90 | yes | purple/black/?/? | same |
| eae22475 | hit | hit_bystander | 0.88 | yes | purple/black/?/? | same |
| 60bd2665 | hit | hit_player | 0.95 | no | purple/black/blue/green | fully correct, incl. no-zoom |
| e21af555 | bystander | hit_bystander | 0.85 | yes | ?/blue@0.70/?/? | good (zoom optional per note) |
| e26c7d08 | bystander | hit_bystander | 0.90 | no | ?/green/?/? | exactly per note |
| 73a492de | miss | miss | 0.95 | no | all unknown | correct (sea past the head) |
| bd21e28a | miss | miss | 0.99 | no | all unknown | correct (tree) |
| 25063242 | bystander | hit_bystander | 0.99 | no | all unknown | correct |
| c3d2d6db | miss | miss | 0.99 | no | all unknown | correct (nobody in frame) |
| 5e9441f2 | hit | hit_bystander | 0.95 | no | black/**green**/?/? | trousers misread (note says blue); hit→bystander via classify |

Zoom behaviour matched the notes everywhere except d91548d3.

### The false hit: d91548d3 (the one worth staring at)

Model's-eye views saved at the repo root (gitignored via `/*.png`):

- `handover_d91548d3_model_input.png` — exactly what the classifier got
  (original + aim marker, downsized to 540×1024 by `prepare_for_vision`).
- `handover_d91548d3_zoom_available.png` — the zoom it could have requested
  but didn't.

Regenerate with: `draw_aim_marker` → `prepare_for_vision` (and
`zoom_image(factor=4)`) on the fixture photo, exactly as
`scripts/replay_shot_reviews.py::_replay_one` does.

Findings:

- **The aim marker's arms lie across the person's head.** The true aim point
  (the empty gap at the centre of the cross) is up in the leaves above-left of
  the head — the admin's "miss". But the horizontal arm's tip lands on the
  forehead and the vertical arm reaches the top of the head, so at 1024px the
  cross visually *touches* the person. "The crosshair lands directly on the
  person" is a defensible read of those pixels. This is the marker-geometry
  problem already suspected in roadmap R1 (four arms + gap ⇒ ~34px hole at the
  aim point while the arms reach into the target).
- **Its channel reads weren't hallucinated.** The zoom shows the man really
  does have a dark green cloth on his head and a green band tied on his right
  upper arm — hence green hat @0.75 / green armbands @0.85, which is what made
  `classify` say `hit_player` ("armbands visible"). The entire error is the
  hit/miss call, driven by the marker.
- It never asked for the zoom because it was already certain from the full
  frame — the zoom view makes the truth (centre in foliage, head below-right)
  obvious. Cf. roadmap #4 items 2–4 (marker redesign, decision pressure,
  Python owning the threshold via an observation like
  `on_body`/`touching_outline`/`clearly_beside`/`nobody_near`).

### The false misses are `classify()`, not the model

All four (d276f718, 697899ee, eae22475, 5e9441f2) reported exactly the
channels the notes prescribe — two garments + honest unknowns at ~50m — and
`classify()` then mapped that to `hit_bystander` because two readable channels
can't vouch for a code (`k + 1` rule). Per Charles's spec the vision *agent*
behaved correctly on all four; what the notes expect instead is "hit a human
but not necessarily a player" with escalation to a stronger reviewer/admin.
Note the admin verdicts call these "hit" because the targets are known
players — the harness scores outcomes, so they show up as false misses even
though the observations were right.

### The "code" wording in stored AI reviews

Eight stored reviews say things like *"armbands hidden and too few other
garments readable to check the code"*. **That text is not the model's** — it
is the `outcome_reason` written by `backend/shot_vision.py::classify()` (the
strings at the `HIT_BYSTANDER` branches) and surfaced in the admin queue
alongside the review. The model's own `reasoning` fields never mention codes.
So Charles's "the AI refers to the error code" observation is real but the fix
is Python-side wording (or not surfacing that field), not the prompt.

## Uncommitted state

- `scripts/replay_shot_reviews.py` — export/load now round-trip `admin_notes`.
- `docs/roadmap.md` — fixture-set description updated (13 shots, real
  verdicts + notes).
- `tests/fixtures/shot_replay/` — rebuilt (13 photos, manifest,
  `replay_baseline.jsonl`).
- `data.db` — refreshed from live (gitignored).
- Two handover PNGs at repo root (gitignored).
- Pre-existing modifications by others (ShotQueue.js, workflows, etc.) were
  already in the working tree; leave them alone.

## Likely next steps (for Charles to pick, not started)

- Roadmap **#4** prompt/marker work, trialled as entries in
  `PROMPT_VARIANTS` and scored against this fixture set — it is now a proper
  labelled set with expected per-channel readings in the notes.
- Whether `classify`'s two-channel → `hit_bystander` mapping should instead
  escalate (the notes repeatedly ask for a stronger second tier).
- Rewording/not-surfacing the code-referencing `outcome_reason` strings.
- 5e9441f2's green-vs-blue trousers read — worth an eyeball before trusting
  colour accuracy at close range indoors.
