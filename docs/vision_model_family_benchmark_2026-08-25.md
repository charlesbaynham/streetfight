# Handover: benchmarking a model family on the R1 harness — 2026-08-25

Written for whoever picks this up next (Charles, or another session with an
`OPENROUTER_API_KEY`). Covers: what was asked, what got built, why no numbers
exist yet, and exactly what to run to get them.

## What was asked

Benchmark vision *accuracy* (not the downstream `classify()` logic — that's a
separate, already-tracked problem, see the R1 entry above and
`handover_vision_replay_2026-08-24.md`) across a family of models:

- The whole **Qwen3-VL** line, flagship down to the small ones.
- **Gemini Flash** re-benchmarked alongside them, as the point of comparison
  (it's the pipeline's current default,
  `google/gemini-3.7-flash-20260813`).

Plus a report on **vision clarity** (does the model's raw channel/hit-or-miss
reading match what's actually in the photo) and **correct tool use** (does it
respect the JSON-schema contract, the zoom-request protocol, and so on —
separate from whether it saw correctly).

## What got built

1. `scripts/replay_shot_reviews.py` — extracted the body of `cmd_replay` into
   a reusable `replay_to_file(shots, client, prompt, variant_name,
   always_zoom, out_path, limit, concurrency)`. Same behaviour (resumable
   JSONL, one API call per shot per the pipeline's zoom protocol), just
   callable from more than one entry point. `cmd_replay` itself is unchanged
   in behaviour.

2. **New:** `scripts/benchmark_vision_family.py`. Runs `replay_to_file` once
   per model in `MODEL_FAMILY`, each into its own resumable JSONL under
   `--out-dir`, then prints each model's confusion report (via the existing
   `aggregate`/`print_report`) plus a summary table across the family and a
   tool-use tally bucketing every stored error string into `empty_reply`,
   `unparseable_json`, `rejected_4xx`, `http_error`, or `other`.

   ```bash
   python -m scripts.benchmark_vision_family \
       --fixtures tests/fixtures/shot_replay \
       --out-dir tests/fixtures/shot_replay/family_benchmark
   # a cheap trial run first:
   python -m scripts.benchmark_vision_family --limit 3 --models qwen3-vl-8b-instruct,gemini-3.7-flash
   ```

   `MODEL_FAMILY` (OpenRouter slugs, confirmed against openrouter.ai's Qwen
   catalogue on 2026-08-25 — re-check there before trusting this list stays
   current, OpenRouter renames/retires dated snapshots):

   | label | OpenRouter slug |
   |---|---|
   | qwen3-vl-235b-a22b-instruct | `qwen/qwen3-vl-235b-a22b-instruct` |
   | qwen3-vl-235b-a22b-thinking | `qwen/qwen3-vl-235b-a22b-thinking` |
   | qwen3-vl-32b-instruct | `qwen/qwen3-vl-32b-instruct` |
   | qwen3-vl-30b-a3b-instruct | `qwen/qwen3-vl-30b-a3b-instruct` |
   | qwen3-vl-30b-a3b-thinking | `qwen/qwen3-vl-30b-a3b-thinking` |
   | qwen3-vl-8b-instruct | `qwen/qwen3-vl-8b-instruct` |
   | qwen3-vl-8b-thinking | `qwen/qwen3-vl-8b-thinking` |
   | gemini-3.7-flash | `google/gemini-3.7-flash-20260813` |

   Note there is no Qwen3-VL size below 8B on OpenRouter as of this writing —
   Qwen2.5-VL goes down to 3B, but that's the previous generation, not "the
   quite small ones" of the *3-VL* family the request named. If a smaller
   Qwen3-VL ships later, add it to `MODEL_FAMILY` and re-run; nothing else
   needs to change.

3. **Verified structurally, not against real models.** Both the happy path
   (a stubbed `complete()` returning a plausible reply) and the error path (a
   stubbed `complete()` raising `VisionError("...empty reply")`) were run
   through `run_family()` directly, confirming: the JSONL files are written
   per model, `print_report` runs on each, the tool-use tally buckets the
   injected error correctly, and the summary table renders. This is *not* a
   test of any model's actual accuracy — see below.

## Why there are no accuracy numbers yet

This session had no `OPENROUTER_API_KEY` available — not in `.env` (it's
commented out there, same as noted in the 2026-08-24 handover), not in the
environment, and this sandbox has no path to the homeserver secrets file the
previous session used. Every model call in `benchmark_vision_family.py` is a
real, billed OpenRouter request, so nothing was run against actual photos.

**To finish this:** source a real key and run the command above. Concretely,
same recipe as the 2026-08-24 session:

```bash
# on a machine that can reach homeserver:
ssh homeserver "cat /mnt/usbpool/data/subvol-9101-disk-0/secrets/streetfight.env" \
    | grep OPENROUTER_API_KEY
export OPENROUTER_API_KEY=...   # do not write it into the repo
python -m scripts.benchmark_vision_family --limit 3   # cheap sanity check first
python -m scripts.benchmark_vision_family             # full family, full fixture set
```

13 fixture shots × 8 models = 104 calls for a full baseline pass (more if a
shot's screening question asks for the zoom, since that's a second call).
Cheap relative to a full game night, but not free — `--limit` and `--models`
exist so a first pass can be small.

## What to look for once it runs, per the ask

- **Vision clarity** — read `report["by_readable_channels"]` and the raw
  per-shot `reasoning` fields in each model's JSONL against the fixture
  manifest's `admin_notes` (same method as the 2026-08-24 handover's
  shot-by-shot table). A model whose *channel readings* match the notes even
  when its hit/miss call is wrong (like the false misses in that handover)
  is seeing clearly; `classify()` is a separate concern.
- **Correct tool use** — the tool-use tally this script prints. A smaller
  model failing to hit the JSON schema, returning empty replies, or not
  following the zoom-request protocol (asking for a zoom that's already been
  spent, or never asking when the screening answer says the target is small)
  shows up as `errors` and in `error_kinds`, separate from whether its
  answers were accurate. Worth eyeballing a few raw JSONL rows per model,
  not just the aggregate counts.
- Compare against the existing `google/gemini-3.7-flash-20260813` baseline
  in `tests/fixtures/shot_replay/replay_baseline.jsonl` (from
  `handover_vision_replay_2026-08-24.md`) — the family benchmark re-runs the
  same model, so the two should agree modulo API nondeterminism, which is
  itself a useful sanity check on the harness.

## Uncommitted vs. committed

- `scripts/replay_shot_reviews.py` (refactor), `scripts/benchmark_vision_family.py`
  (new), this doc, and the `docs/roadmap.md` R1 note are committed on
  `claude/vision-accuracy-benchmark-l6q7pw`.
- No new fixture/JSONL data is committed — none was generated, for the reason
  above. `tests/fixtures/shot_replay/family_benchmark/` doesn't exist yet;
  the script creates it on first real run.
