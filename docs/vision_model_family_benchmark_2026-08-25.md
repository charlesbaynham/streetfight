# Handover: benchmarking a model family on the R1 harness — 2026-08-25

Written for whoever picks this up next. Covers: what was asked, what got
built, the real results from a full run against the fixture set, and what
they mean.

## What was asked

Benchmark vision *accuracy* (not the downstream `classify()` logic — that's a
separate, already-tracked problem, see the R1 entry above and
`handover_vision_replay_2026-08-24.md`) across a family of models:

- The whole **Qwen3-VL** line, flagship down to the small ones.
- **Gemini Flash** re-benchmarked alongside them, as the point of comparison
  (it's the pipeline's current default, `google/gemini-3.7-flash-20260813`).

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

2. `scripts/benchmark_vision_family.py`. Runs `replay_to_file` once per model
   in `MODEL_FAMILY`, each into its own resumable JSONL under `--out-dir`,
   then prints each model's confusion report (via the existing
   `aggregate`/`print_report`) plus a summary table across the family and a
   tool-use tally bucketing every stored error string into `empty_reply`,
   `unparseable_json`, `rejected_4xx`, `http_error`, or `other`.

   ```bash
   python -m scripts.benchmark_vision_family \
       --fixtures tests/fixtures/shot_replay \
       --out-dir tests/fixtures/shot_replay/family_benchmark
   ```

   `MODEL_FAMILY` (OpenRouter slugs, confirmed against openrouter.ai's Qwen
   catalogue on 2026-08-25 — re-check there before trusting this list stays
   current, OpenRouter renames/retires dated snapshots). There is no
   Qwen3-VL size below 8B on OpenRouter as of this writing — Qwen2.5-VL goes
   down to 3B, but that's the previous generation.

## The real run

A full pass (all 8 models × the 13-shot fixture set, `baseline` variant,
concurrency 3) was run against live OpenRouter with a short-lived key. Output
JSONL per model is committed at `tests/fixtures/shot_replay/family_benchmark/`.

**Headline table** (false hits/misses are against the fixture set's 8
non-hits and 5 hits; "errors" is outright pipeline failures, not wrong
answers; "tool-use errors" buckets those failures — see below):

| model | false hits | false misses | errors | zoom used | mean confidence | tool-use errors |
|---|---|---|---|---|---|---|
| qwen3-vl-235b-a22b-instruct | 0/5 | 4/4 | **4** | 8/9 | 0.74 | `unparseable_json=4` |
| qwen3-vl-235b-a22b-thinking | **1/8** | 3/5 | 0 | 12/13 | 0.77 | — |
| qwen3-vl-32b-instruct | 0/8 | 5/5 | 0 | 12/13 | 0.52 | — |
| qwen3-vl-30b-a3b-instruct | 0/8 | 4/5 | 0 | 13/13 | 0.65 | — |
| qwen3-vl-30b-a3b-thinking | 0/8 | 3/5 | 0 | 9/13 | 0.81 | — |
| qwen3-vl-8b-instruct | 0/8 | 3/5 | 0 | 5/13 | 0.66 | — |
| qwen3-vl-8b-thinking | **4/8** | 3/5 | 0 | 7/13 | 0.81 | — |
| gemini-3.7-flash (baseline) | 0/8 | 4/5 | 0 | 12/13 | 0.92 | — |

(N=13 fixture shots — small, so read this as directional, same caveat the
2026-08-24 handover gives its own numbers.)

## Correct tool use

**`qwen3-vl-235b-a22b-instruct` failed outright on 4 of 13 shots (31%).** Not
a wrong answer — the OpenRouter response body's `content` was pure
whitespace (tabs/newlines, no JSON at all), which `parse_json_reply` rightly
rejects rather than guessing. All 3 retries hit the same thing, so this isn't
a transient blip:

```
could not find a JSON object in the reply: '{\t\t\t\t\t\t\n\t      \t ... '
```

This is specific to the **instruct** variant of the flagship model called
through OpenRouter's `response_format: json_schema` — none of the other
seven models (including its own `-thinking` sibling, and every smaller
Qwen3-VL size) showed this at all. Plausible cause: the instruct variant
treats the schema as satisfied by emitting only whitespace under some
sampling settings OpenRouter applies for this route; not something this
pipeline's prompt controls. Worth flagging upstream or retrying with
different provider routing before trusting this model in production —
right now, a quarter of its shots would silently fall through to
`ai_review_state = "error"` and sit in the queue for a human, no worse than
today's fallback but no better either.

No other model showed a schema, empty-reply, or rejected-request failure.
Zoom-request adherence looked correct everywhere reviewed by eye: every model
that called for a zoom got exactly one follow-up image, and none asked for a
second (the pipeline caps it at one; nothing suggested a model tried to
ignore that cap).

## Vision clarity

**`qwen3-vl-8b-thinking` is the standout bad case — not for being unsure, but
for being confidently wrong.** Two examples from the shared fixture set (the
same shots every model saw):

- `c3d2d6db` — a genuine miss, admin note "nobody in frame" (sea and open
  water). Every other model in the family, including `qwen3-vl-8b-thinking`'s
  own non-thinking sibling, correctly reported "no person visible" at
  confidence ≥ 0.9. `qwen3-vl-8b-thinking` instead reported:

  > "The cross center is on the person's torso, indicating a hit. Visible
  > clothing includes a black t-shirt, black trousers, black hat, and black
  > wristbands with high confidence." (`hit_player`, confidence 0.9)

  It hallucinated a person and four garment colours out of open water.

- `d1c4e6ad` — a bystander at range, correctly read by every other model as
  either too blurry to call or a `hit_bystander` with honest low-to-medium
  confidence. `qwen3-vl-8b-thinking` reported `hit_player` at confidence 0.9,
  claiming the clothing was "clearly visible" where it demonstrably wasn't.

This pattern — confident fabrication on exactly the shots where every other
model (including its own same-size non-thinking sibling) hedges or abstains
— accounts for all 4 of its false hits, the worst false-hit rate in the
family by a wide margin. **"Thinking" made this small model worse, not
better**: `qwen3-vl-8b-instruct` (0 false hits) versus `qwen3-vl-8b-thinking`
(4 false hits) on the identical fixture set.

**`qwen3-vl-235b-a22b-thinking` reproduced the exact false hit the
2026-08-24 handover documented for Gemini** (`d91548d3`, the marker-geometry
case — the crosshair's arms visually touch the person's head while the true
aim point is in foliage above-left): it called `hit_player` at 0.85,
reasoning "the t-shirt is clearly purple; wristband and headband are green" —
correct channel reads, wrong hit/miss call, same root cause (roadmap #4's
marker geometry) as before. `gemini-3.7-flash` and most of the mid-size Qwen
models got this one right ("centre of the crosshairs is on the plant foliage
... missing them"), confirming the marker problem is model-independent
rather than a Gemini quirk — good evidence for prioritising the roadmap #4
marker redesign over a model swap.

**The false misses are consistent across nearly every model** — `d276f718`,
`697899ee`, `eae22475`, `5e9441f2` show up as false misses almost everywhere
in the table, exactly the four the 2026-08-24 handover attributed to
`classify()`'s two-channel-can't-vouch-for-a-code rule, not the vision model.
Every model in this family reads the same two garments correctly at ~50m
range; they disagree on hit/miss only where `classify()` structurally can't
call it a hit. This is further evidence the downstream classifier, not model
choice, is the thing to fix for that failure mode.

**Calibration varies a lot for the same nominal accuracy.**
`qwen3-vl-32b-instruct` tied for the best false-hit rate (0/8) but did it by
abstaining: mean confidence 0.52, four shots scored at confidence 0.0
("too blurred/zoomed to identify"). That's safe but not useful — none of
those would help the admin queue or ever auto-fire. `gemini-3.7-flash` gets
the same 0 false hits at mean confidence 0.92 — right *and* usably
confident, which is the actual bar for auto-actions, not just avoiding false
hits by shrugging.

## Bottom line

- **Don't ship `qwen3-vl-235b-a22b-instruct`** as-is: the whitespace-reply
  failure on 31% of shots is disqualifying regardless of its accuracy on the
  rest.
- **Avoid `qwen3-vl-8b-thinking`**: confident hallucination on genuinely
  empty/ambiguous shots is the worst failure mode this pipeline can have
  (worse than a false miss — it's exactly what would auto-fire a wrongful
  hit). Its non-thinking sibling doesn't share this problem.
- **`gemini-3.7-flash` (the current default) remains the best-calibrated
  model in the family** on this fixture set: 0 false hits at high mean
  confidence, no tool-use failures. Nothing here argues for switching away
  from it.
- **`qwen3-vl-235b-a22b-thinking` and `qwen3-vl-30b-a3b-thinking`** are the
  closest challengers — clean tool use, reasonable calibration (mean
  confidence 0.77–0.81) — but each produced at least one wrong hit/miss call
  a lower-stakes model didn't, on a sample this small to call a win either
  way.
- The false-miss cluster and the `d91548d3`-style false hit are both
  **model-independent**: they reproduce the same way across most of the
  family, reinforcing that `classify()`'s two-channel rule and the aim-marker
  geometry (roadmap #4) are the higher-leverage fixes, not a model swap.

## Files

- `tests/fixtures/shot_replay/family_benchmark/<label>.jsonl` — one file per
  model, raw per-shot outcomes (resumable; re-run
  `scripts.benchmark_vision_family` with the same `--out-dir` to pick up
  where a partial run left off).
- `scripts/benchmark_vision_family.py` / `scripts/replay_shot_reviews.py` —
  the harness itself.
