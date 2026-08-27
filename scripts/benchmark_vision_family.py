"""Benchmark a family of vision models on the R1 replay fixture set.

Runs the same pipeline ``scripts.replay_shot_reviews`` uses (baseline
prompt/zoom behaviour, unless ``--variant`` says otherwise) over every model
in ``MODEL_FAMILY``, one resumable JSONL per model under ``--out-dir``, then
prints each model's confusion report plus a side-by-side accuracy table and a
tool-use tally (JSON-schema/parse failures, empty replies, rejected
requests -- the things a weaker model gets wrong that have nothing to do with
what it saw).

Needs ``OPENROUTER_API_KEY``: every model call is a real, billed OpenRouter
request. Use ``--limit`` while trying it out, and ``--models`` to run a subset.

    python -m scripts.benchmark_vision_family \\
        --fixtures tests/fixtures/shot_replay \\
        --out-dir tests/fixtures/shot_replay/family_benchmark
"""

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import List
from typing import Tuple

from backend import shot_vision
from backend.dotenv import load_env_vars
from backend.vision_client import OpenRouterVisionClient
from scripts.replay_shot_reviews import PROMPT_VARIANTS
from scripts.replay_shot_reviews import _load_fixture_shots
from scripts.replay_shot_reviews import _min_readable
from scripts.replay_shot_reviews import _record_of
from scripts.replay_shot_reviews import aggregate
from scripts.replay_shot_reviews import print_report
from scripts.replay_shot_reviews import replay_to_file

load_env_vars()

# The family asked for (2026-08-25): every size OpenRouter currently lists
# under Qwen3-VL -- the flagship MoE plus the smaller dense/instruct and
# "thinking" siblings -- next to the pipeline's own default model as the
# point of comparison. Slugs confirmed against openrouter.ai's Qwen catalogue;
# re-check there before adding to this list, since OpenRouter renames/retires
# dated snapshots.
MODEL_FAMILY: List[Tuple[str, str]] = [
    ("qwen3-vl-235b-a22b-instruct", "qwen/qwen3-vl-235b-a22b-instruct"),
    ("qwen3-vl-235b-a22b-thinking", "qwen/qwen3-vl-235b-a22b-thinking"),
    ("qwen3-vl-32b-instruct", "qwen/qwen3-vl-32b-instruct"),
    ("qwen3-vl-30b-a3b-instruct", "qwen/qwen3-vl-30b-a3b-instruct"),
    ("qwen3-vl-30b-a3b-thinking", "qwen/qwen3-vl-30b-a3b-thinking"),
    ("qwen3-vl-8b-instruct", "qwen/qwen3-vl-8b-instruct"),
    ("qwen3-vl-8b-thinking", "qwen/qwen3-vl-8b-thinking"),
    ("gemini-3.7-flash", "google/gemini-3.7-flash-20260813"),
]


def _error_kind(error: str) -> str:
    """A short bucket for an error string -- the tool-use tally's rows."""
    lowered = error.lower()
    if "empty reply" in lowered:
        return "empty_reply"
    if "could not find a json object" in lowered:
        return "unparseable_json"
    if "rejected the request" in lowered:
        return "rejected_4xx"
    if "returned 429" in lowered or "returned 5" in lowered:
        return "http_error"
    return "other"


def run_family(
    fixtures: str,
    out_dir: str,
    variant_name: str,
    models: List[Tuple[str, str]],
    limit,
    concurrency: int,
) -> list:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set; cannot benchmark")
    if variant_name not in PROMPT_VARIANTS:
        raise SystemExit(
            f"unknown variant {variant_name!r}; known: {sorted(PROMPT_VARIANTS)}"
        )

    variant = PROMPT_VARIANTS[variant_name]
    prompt = (
        variant.build_prompt(shot_vision.channel_palettes())
        if variant.build_prompt
        else None
    )

    shots = _load_fixture_shots(fixtures)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    jsonl_paths = []
    for label, model_id in models:
        jsonl_path = out_path / f"{label}.jsonl"
        client = OpenRouterVisionClient(api_key=api_key, model=model_id)
        replay_to_file(
            shots,
            client,
            prompt,
            variant_name,
            variant.zoom_mode,
            jsonl_path,
            limit=limit,
            concurrency=concurrency,
        )
        jsonl_paths.append((label, model_id, jsonl_path))

    summary = []
    for label, model_id, jsonl_path in jsonl_paths:
        records = []
        error_kinds = Counter()
        zoom_requests = 0
        for line in jsonl_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            records.append(
                _record_of(
                    row["shot_id"], row["truth"], row.get("review"), row.get("error")
                )
            )
            if row.get("error"):
                error_kinds[_error_kind(row["error"])] += 1
            elif (row.get("review") or {}).get("zoom_used"):
                zoom_requests += 1
        report = aggregate(records, min_readable=_min_readable())
        print_report(report, f"{label} ({model_id})")
        if error_kinds:
            print(f"  tool-use errors: {dict(error_kinds)}\n")
        summary.append(
            {
                "label": label,
                "model_id": model_id,
                "report": report,
                "error_kinds": error_kinds,
                "zoom_requests": zoom_requests,
            }
        )

    print_summary_table(summary)
    return summary


def print_summary_table(summary: list) -> None:
    print("\n== Summary across the family ==")
    header = (
        f"{'model':<30}{'false hits':>12}{'false misses':>14}"
        f"{'errors':>9}{'zoom':>7}{'tool-use errors':>18}"
    )
    print(header)
    for row in summary:
        all_rates = row["report"]["all"]
        fh = f"{all_rates['false_hits']}/{all_rates['false_hit_base']}"
        fm = f"{all_rates['false_misses']}/{all_rates['false_miss_base']}"
        error_kinds = ",".join(f"{k}={v}" for k, v in row["error_kinds"].items()) or "-"
        print(
            f"{row['label']:<30}{fh:>12}{fm:>14}"
            f"{row['report']['errors']:>9}{row['zoom_requests']:>7}{error_kinds:>18}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fixtures", default="tests/fixtures/shot_replay", help="fixture directory"
    )
    parser.add_argument(
        "--out-dir",
        default="tests/fixtures/shot_replay/family_benchmark",
        help="directory to write one JSONL per model into",
    )
    parser.add_argument(
        "--variant", default="baseline", help=f"one of {sorted(PROMPT_VARIANTS)}"
    )
    parser.add_argument(
        "--models",
        default=None,
        help="comma-separated labels from MODEL_FAMILY to restrict to "
        "(default: the whole family)",
    )
    parser.add_argument("--limit", type=int, default=None, help="shots per model")
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    models = MODEL_FAMILY
    if args.models:
        wanted = set(args.models.split(","))
        models = [
            (label, model_id) for label, model_id in MODEL_FAMILY if label in wanted
        ]
        missing = wanted - {label for label, _ in models}
        if missing:
            raise SystemExit(f"unknown model label(s): {sorted(missing)}")

    run_family(
        args.fixtures, args.out_dir, args.variant, models, args.limit, args.concurrency
    )


if __name__ == "__main__":
    main()
