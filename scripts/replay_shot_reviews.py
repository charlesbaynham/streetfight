"""R1: the offline replay harness for CharlesBot's shot reviews.

Every adjudicated shot already carries both halves of a labelled example:
``Shot.ai_review`` (the model's verdict) and ``Shot.result`` (the admin's),
plus the original photo in ``Shot.image_base64``. Nothing compares them. This
script is that comparison, in three subcommands:

* **audit** -- score the reviews already stored in a database against the
  admin verdicts. No API calls, no cost: the baseline confusion matrix.
* **replay** -- re-run the vision pipeline (the same one
  ``backend.ai_shot_review`` uses) over the saved photos, offline, with a
  chosen model and prompt variant, writing one JSON line per shot. Resumable:
  shot ids already in the output file are skipped.
* **score** -- turn a replay file into the same report audit prints, so
  prompt variants can be compared on identical data.

The point of all three is roadmap #4: shots that visibly miss being called
hits. Every report ends with the ids of the false hits and false misses so
the offending photos can be looked at (``extract`` dumps them to PNG).

The database is only ever read. The engine is built here rather than imported
from ``backend.database``, whose import-time ``load()`` creates tables and
columns -- fine for the app, not for a script pointed at a copy of the live
data. SQLite databases are opened in read-only mode for the same reason.

    python -m scripts.replay_shot_reviews audit --db sqlite:///data.db
    python -m scripts.replay_shot_reviews replay --db sqlite:///data.db \
        --out baseline.jsonl --variant baseline
    python -m scripts.replay_shot_reviews score baseline.jsonl
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Callable
from typing import Dict
from typing import List
from typing import NamedTuple
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import shot_vision
from backend.dotenv import load_env_vars
from backend.image_processing import draw_aim_marker
from backend.image_processing import load_image
from backend.image_processing import prepare_for_vision
from backend.image_processing import zoom_image
from backend.model import AI_REVIEW_STATE_DONE
from backend.model import Shot
from backend.shot_vision import CONFIDENT_THRESHOLD
from backend.shot_vision import HIT_BYSTANDER
from backend.shot_vision import HIT_PLAYER
from backend.shot_vision import MISS
from backend.shot_vision import confident_channel_count
from backend.vision_client import OpenRouterVisionClient

logger = logging.getLogger(__name__)

load_env_vars()

# Coarse verdicts, shared by the admin's result and the model's outcome.
TRUTH_VALUES = ("hit", "miss", "bystander", "refunded")
AI_OUTCOMES = {HIT_PLAYER: "hit", HIT_BYSTANDER: "bystander", MISS: "miss"}

# Roadmap #4 suspects 3+4: instead of a bare "did it hit" boolean, make the
# model place the cross's centre point into four buckets spanning clearly-hit
# to clearly-miss, with the two boundary buckets explicitly naming which side
# of "hit" they're on -- and break a genuine tie towards "miss" (the cheaper
# wrong answer). Same JSON contract as the default rule, so parsing is
# unchanged; only the reasoning scaffold differs.
BOUNDARY_SCALE_RULE = f"""FIRST: did the shot hit a person? Judge this by placing the centre point of \
the cross into one of these four buckets:

- clearly hitting: the centre point is unambiguously on the person's body or \
clothing, with room to spare on every side.
- on the boundary, but just hitting: the centre point is right at the edge of \
the person -- on their outline, or on the very edge of their clothing -- close \
enough that if you had to bet, you would bet it is on them.
- on the boundary, but just missing: the centre point is right at the edge but \
just outside the person -- beside them, touching their outline from the \
outside, or in the gap between two people -- close enough that if you had to \
bet, you would bet it is not on them.
- miles away: there is clear space between the centre point and any person, or \
there is nobody near it at all.

Set "{shot_vision.HIT_FIELD}" to true for "clearly hitting" or "on the \
boundary, but just hitting". Set it to false for "on the boundary, but just \
missing" or "miles away". If the centre point lands on foliage, an object, or \
empty ground, that is a miss even if a person is standing right next to it.

When genuinely torn between "just hitting" and "just missing", pick "just \
missing": a wrongly-called miss costs the shooter one bullet, but a \
wrongly-called hit takes a life from somebody who was never shot."""


def _boundary_scale_prompt(palettes: Dict[str, List[str]]) -> str:
    return shot_vision.build_prompt(palettes, decision_rule=BOUNDARY_SCALE_RULE)


class PromptVariant(NamedTuple):
    """A replay experiment: the prompt to send, and how the zoom is handled.

    ``build_prompt`` is a callable taking the channel palettes and returning
    the prompt text; None means whatever ``shot_vision.build_prompt`` currently
    produces, so a replay always scores what the live pipeline would have said.
    ``zoom_mode`` is passed through to ``shot_vision.review_image`` (see its
    ``ZOOM_*`` constants) and picks the shape of the exchange.
    """

    build_prompt: Optional[Callable] = None
    zoom_mode: str = shot_vision.ZOOM_SCREENED


# Prompt variants for roadmap #4 land here. "baseline" is the live pipeline's
# own prompt and zoom behaviour: the screening question (does the person fill
# less than half of the screen?) decides whether the zoom is spent.
# "always_zoom" preserves the previous live behaviour -- both views up front in
# a single call -- for comparison runs.
PROMPT_VARIANTS = {
    "baseline": PromptVariant(),
    "boundary_scale": PromptVariant(build_prompt=_boundary_scale_prompt),
    # Roadmap #4, the experiment that worked before the screening question
    # replaced it: the false hits never requested the zoom because they never
    # doubted themselves, so the zoom was sent whether they asked or not. Kept
    # under its own name because that is what the replay_always_zoom_run*.jsonl
    # files record.
    "always_zoom": PromptVariant(zoom_mode=shot_vision.ZOOM_UPFRONT),
}

# Scoring a historical shot against the *current* user table cannot reproduce
# what the auto-actions would have done at the time (hit points have moved on
# since), so identification is not simulated: a would-be auto-hit is counted
# correct iff the admin called it a hit at all. That makes the reported
# auto-hit accuracy an upper bound, and the report says so.
_AUTO_HIT_NOTE = (
    "identification not simulated: an auto-hit is 'right' iff the admin "
    "called the shot a hit, so this is an upper bound"
)


# ---------------------------------------------------------------------------
# Loading shots, read-only
# ---------------------------------------------------------------------------


def _read_only_engine(db_url: str):
    """An engine that cannot write. SQLite gets a real read-only connection."""
    if db_url.startswith("sqlite"):
        path = db_url.split("sqlite:///", 1)[-1]
        if path and path != ":memory:":
            # The pysqlite dialect recognises uri=true in the query string and
            # hands the whole thing to sqlite as a URI filename.
            uri = f"file:{Path(path).resolve()}?mode=ro"
            return create_engine(f"sqlite:///{uri}&uri=true")
    return create_engine(db_url)


def _load_shots(db_url: str, game_id: str = None, with_images: bool = False):
    """Adjudicated shots as plain dicts, oldest first. The session is short."""
    from sqlalchemy.orm import defer

    session = sessionmaker(bind=_read_only_engine(db_url))()
    try:
        query = session.query(Shot).filter(Shot.result.isnot(None))
        if game_id:
            query = query.filter(Shot.game_id == game_id)
        if not with_images:
            query = query.options(defer(Shot.image_base64))
        shots = query.order_by(Shot.time_created).all()
        return [_shot_row(shot, with_images) for shot in shots]
    finally:
        session.close()


def _shot_row(shot, with_images: bool) -> dict:
    return {
        "shot_id": str(shot.id),
        "game_id": str(shot.game_id),
        "time": str(shot.time_created),
        "truth": shot.result,
        "ai_review_state": shot.ai_review_state,
        "ai_review": shot.ai_review,
        "image_base64": shot.image_base64 if with_images else None,
    }


def _load_fixture_shots(fixtures_dir: str):
    """Shots from an exported fixture directory (see ``cmd_export``).

    A fixture's truth is the admin's ``result`` when it exists, else the
    ``human_label`` somebody gave the photo by eye -- recorded separately in
    the manifest precisely because it is not the admin's adjudication.
    """
    fixtures_path = Path(fixtures_dir)
    manifest = json.loads((fixtures_path / "manifest.json").read_text())
    shots = []
    for entry in manifest["shots"]:
        image_bytes = (fixtures_path / entry["image"]).read_bytes()
        shots.append(
            {
                "shot_id": entry["shot_id"],
                "game_id": entry.get("game_id"),
                "time": entry.get("time"),
                "truth": entry.get("result") or entry.get("human_label"),
                "admin_notes": entry.get("admin_notes"),
                "ai_review_state": (
                    AI_REVIEW_STATE_DONE if entry.get("ai_review") else None
                ),
                "ai_review": (
                    json.dumps(entry["ai_review"]) if entry.get("ai_review") else None
                ),
                "image_base64": "data:image/jpeg;base64,"
                + base64.b64encode(image_bytes).decode(),
            }
        )
    return shots


def _parse_stored_review(shot: dict):
    """The review payload of a stored shot, or None if there is nothing usable."""
    if shot["ai_review_state"] != AI_REVIEW_STATE_DONE or not shot["ai_review"]:
        return None
    try:
        review = json.loads(shot["ai_review"])
    except ValueError:
        return None
    return review if isinstance(review, dict) else None


# ---------------------------------------------------------------------------
# Scoring: one record per shot, then an aggregate report
# ---------------------------------------------------------------------------


def _record_of(shot_id: str, truth: str, review: dict, error: str = None) -> dict:
    """The unit of scoring: what the admin said, and what the review said."""
    record = {
        "shot_id": shot_id,
        "truth": truth if truth in TRUTH_VALUES else "other",
        "error": error,
        "outcome": None,
        "confidence": 0.0,
        "zoom_used": False,
        "readable_channels": 0,
    }
    if review is not None:
        record["outcome"] = AI_OUTCOMES.get(review.get("outcome"))
        try:
            record["confidence"] = float(review.get("confidence"))
        except (TypeError, ValueError):
            record["confidence"] = 0.0
        record["zoom_used"] = bool(review.get("zoom_used"))
        record["readable_channels"] = confident_channel_count(review)
    return record


def _simulated_action(record: dict, min_readable: int):
    """What the auto-actions would have done with this review (outcome level).

    Mirrors backend.shot_auto_actions._decide's gates minus identification:
    confident overall, and for a hit at least k + 1 confidently-read channels.
    """
    if record["outcome"] is None or record["confidence"] < CONFIDENT_THRESHOLD:
        return None
    if record["outcome"] in ("miss", "bystander"):
        return record["outcome"]
    if record["readable_channels"] >= min_readable:
        return "hit"
    return None


def aggregate(records, min_readable: int) -> dict:
    """Rates and breakdowns over a list of ``_record_of`` dicts.

    "Refunded" shots are counted but excluded from every rate: a refund says
    something about the game state, not about what the photo shows.
    """
    scored = [r for r in records if r["truth"] in ("hit", "miss", "bystander")]
    reviewed = [r for r in scored if r["outcome"] is not None]

    matrix = Counter((r["truth"], r["outcome"] or "none") for r in scored)

    def rates(subset):
        false_hits = [
            r for r in subset if r["truth"] != "hit" and r["outcome"] == "hit"
        ]
        false_misses = [
            r for r in subset if r["truth"] == "hit" and r["outcome"] != "hit"
        ]
        non_hits = [r for r in subset if r["truth"] != "hit"]
        hits = [r for r in subset if r["truth"] == "hit"]
        return {
            "n": len(subset),
            "false_hits": len(false_hits),
            "false_hit_base": len(non_hits),
            "false_hit_ids": [r["shot_id"] for r in false_hits],
            "false_misses": len(false_misses),
            "false_miss_base": len(hits),
            "false_miss_ids": [r["shot_id"] for r in false_misses],
        }

    confident = [r for r in reviewed if r["confidence"] >= CONFIDENT_THRESHOLD]

    actions = []
    for r in reviewed:
        action = _simulated_action(r, min_readable)
        if action is not None:
            actions.append((action, r))

    return {
        "total": len(records),
        "truths": Counter(r["truth"] for r in records),
        "errors": sum(1 for r in records if r["error"]),
        "reviewed": len(reviewed),
        "matrix": matrix,
        "all": rates(reviewed),
        "confident": rates(confident),
        "actions": Counter(
            (action, "right" if r["truth"] == action else "wrong")
            for action, r in actions
        ),
        "by_zoom": {
            "zoom": rates([r for r in reviewed if r["zoom_used"]]),
            "no_zoom": rates([r for r in reviewed if not r["zoom_used"]]),
        },
        "by_readable_channels": {
            count: rates([r for r in reviewed if r["readable_channels"] == count])
            for count in range(5)
        },
    }


def _rate_line(label: str, rates: dict) -> str:
    def pct(part, base):
        return f"{part}/{base} ({100 * part / base:.0f}%)" if base else "0/0"

    return (
        f"  {label}: false hits {pct(rates['false_hits'], rates['false_hit_base'])}"
        f", false misses {pct(rates['false_misses'], rates['false_miss_base'])}"
        f"  (n={rates['n']})"
    )


def print_report(report: dict, title: str) -> None:
    print(f"== {title} ==")
    truths = report["truths"]
    counts = ", ".join(
        f"{value}={truths.get(value, 0)}" for value in TRUTH_VALUES + ("other",)
    )
    print(
        f"{report['total']} adjudicated shots ({counts}); "
        f"{report['reviewed']} with a usable review, {report['errors']} errored"
    )

    print("\nConfusion (rows: admin verdict; columns: CharlesBot):")
    outcomes = ("hit", "bystander", "miss", "none")
    header = "                " + "".join(f"{o:>12}" for o in outcomes)
    print(header)
    for truth in ("hit", "miss", "bystander"):
        row = f"  admin {truth:>9}"
        for outcome in outcomes:
            row += f"{report['matrix'].get((truth, outcome), 0):>12}"
        print(row)

    print("\nAll reviewed:")
    print(_rate_line("rates", report["all"]))
    print(
        "Confident subset (would-be auto-actions, confidence "
        f">= {CONFIDENT_THRESHOLD}):"
    )
    print(_rate_line("rates", report["confident"]))

    print("\nSimulated auto-actions (outcome level; " + _AUTO_HIT_NOTE + "):")
    for action in ("hit", "miss", "bystander"):
        right = report["actions"].get((action, "right"), 0)
        wrong = report["actions"].get((action, "wrong"), 0)
        print(f"  auto-{action}: {right + wrong} (right {right}, wrong {wrong})")

    print("\nBy zoom:")
    print(_rate_line("zoom used", report["by_zoom"]["zoom"]))
    print(_rate_line("no zoom  ", report["by_zoom"]["no_zoom"]))

    print("\nBy confidently-read channels:")
    for count, rates in report["by_readable_channels"].items():
        if rates["n"]:
            print(_rate_line(f"{count} channels", rates))

    for label in ("false_hit_ids", "false_miss_ids"):
        ids = report["all"][label]
        if ids:
            print(f"\n{label.replace('_', ' ')} ({len(ids)}):")
            for shot_id in ids:
                print(f"  {shot_id}")
    print()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _load_source(args, with_images: bool = False):
    """Shots from whichever source the command was pointed at."""
    if getattr(args, "fixtures", None):
        return _load_fixture_shots(args.fixtures)
    return _load_shots(
        args.db, game_id=getattr(args, "game_id", None), with_images=with_images
    )


def cmd_audit(args) -> None:
    shots = _load_source(args)
    records = [
        _record_of(
            shot["shot_id"],
            shot["truth"],
            _parse_stored_review(shot),
            error=(shot["ai_review"] if shot["ai_review_state"] == "error" else None),
        )
        for shot in shots
    ]
    report = aggregate(records, min_readable=_min_readable())
    print_report(report, f"stored reviews, {args.fixtures or args.db}")


def cmd_export(args) -> None:
    """Export every shot's photo and review to a fixture directory.

    The photos go in as plain image files plus a ``manifest.json`` holding the
    metadata (verdict, stored review); ``result`` is null for shots the admin
    never adjudicated, and a ``human_label`` added by hand later takes its
    place for scoring. The output is what ``--fixtures`` reads back.
    """
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True, parents=True)

    session = sessionmaker(bind=_read_only_engine(args.db))()
    try:
        query = session.query(Shot)
        if args.game_id:
            query = query.filter(Shot.game_id == args.game_id)
        shots = query.order_by(Shot.time_created).all()
        entries = []
        for shot in shots:
            image, split = load_image(shot.image_base64)
            extension = "jpg" if "jpeg" in split[0] else "png"
            filename = f"{shot.id}.{extension}"
            image.save(out_dir / filename)
            image.close()
            entries.append(
                {
                    "shot_id": str(shot.id),
                    "game_id": str(shot.game_id),
                    "time": str(shot.time_created),
                    "shooter": shot.user.name,
                    "result": shot.result,
                    "admin_notes": shot.admin_notes,
                    "human_label": None,
                    "label_note": None,
                    "image": filename,
                    "ai_review": (
                        json.loads(shot.ai_review)
                        if shot.ai_review_state == AI_REVIEW_STATE_DONE
                        and shot.ai_review
                        else None
                    ),
                }
            )
    finally:
        session.close()

    manifest = {"source": args.db, "shots": entries}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Exported {len(entries)} shots to {out_dir}")


async def _replay_one(shot: dict, client, prompt, semaphore, zoom_mode: str) -> dict:
    """One shot through the real pipeline: marker, resize, review, one zoom."""
    async with semaphore:
        try:
            prepared = prepare_for_vision(draw_aim_marker(shot["image_base64"]))

            def zoom_provider(level):
                return zoom_image(
                    shot["image_base64"], factor=shot_vision.ZOOM_FACTOR**level
                )

            result = await shot_vision.review_image(
                client,
                prepared,
                zoom_provider=zoom_provider,
                prompt=prompt,
                zoom_mode=zoom_mode,
            )
            return {"review": result.to_dict()}
        except Exception as e:  # a failed shot is data, not a crash
            logger.exception("Replay of shot %s failed", shot["shot_id"])
            return {"error": str(e) or e.__class__.__name__}


def replay_to_file(
    shots: List[dict],
    client,
    prompt,
    variant_name: str,
    zoom_mode: str,
    out_path: Path,
    limit: Optional[int] = None,
    concurrency: int = 2,
) -> int:
    """Replay ``shots`` through ``client``, appending outcomes to ``out_path``.

    Resumable: shot ids already present in ``out_path`` are skipped, which is
    what lets :mod:`scripts.benchmark_vision_family` and ``cmd_replay`` share
    this without either re-paying for a model's already-replayed shots.
    Returns the number of errored outcomes just written.
    """
    done_ids = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            if line.strip():
                done_ids.add(json.loads(line)["shot_id"])

    todo = [shot for shot in shots if shot["shot_id"] not in done_ids]
    if limit:
        todo = todo[:limit]
    print(
        f"{len(shots)} shots, {len(done_ids)} already replayed, "
        f"{len(todo)} to do (model={client.model}, variant={variant_name})"
    )
    if not todo:
        return 0

    semaphore = asyncio.Semaphore(concurrency)

    async def run_all():
        return await asyncio.gather(
            *(_replay_one(shot, client, prompt, semaphore, zoom_mode) for shot in todo)
        )

    outcomes = asyncio.run(run_all())

    with out_path.open("a") as out_file:
        for shot, outcome in zip(todo, outcomes):
            out_file.write(
                json.dumps(
                    {
                        "shot_id": shot["shot_id"],
                        "game_id": shot["game_id"],
                        "time": shot["time"],
                        "truth": shot["truth"],
                        "model": client.model,
                        "variant": variant_name,
                        **outcome,
                    }
                )
                + "\n"
            )
    errors = sum(1 for outcome in outcomes if "error" in outcome)
    print(f"Wrote {len(outcomes)} results to {out_path} ({errors} errors)")
    return errors


def cmd_replay(args) -> None:
    if args.variant not in PROMPT_VARIANTS:
        raise SystemExit(
            f"unknown variant {args.variant!r}; known: {sorted(PROMPT_VARIANTS)}"
        )
    variant = PROMPT_VARIANTS[args.variant]
    prompt = (
        variant.build_prompt(shot_vision.channel_palettes())
        if variant.build_prompt
        else None
    )

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set; cannot replay")
    client = OpenRouterVisionClient(api_key=api_key, model=args.model)

    shots = _load_source(args, with_images=True)
    replay_to_file(
        shots,
        client,
        prompt,
        args.variant,
        variant.zoom_mode,
        Path(args.out),
        limit=args.limit,
        concurrency=args.concurrency,
    )


def cmd_score(args) -> None:
    for path in args.replay_files:
        records = []
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            records.append(
                _record_of(
                    row["shot_id"], row["truth"], row.get("review"), row.get("error")
                )
            )
        print_report(aggregate(records, min_readable=_min_readable()), path)


def cmd_extract(args) -> None:
    """Dump shots' original photos to PNG, for looking at false hits."""
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True, parents=True)
    wanted = set(args.shot_ids)
    shots = _load_source(args, with_images=True)
    written = 0
    for shot in shots:
        if wanted and shot["shot_id"] not in wanted:
            continue
        image, _ = load_image(shot["image_base64"])
        image.save(out_dir / f"{shot['shot_id']}_{shot['truth']}.png")
        image.close()
        written += 1
    print(f"Wrote {written} images to {out_dir}")


_MIN_READABLE = None


def _min_readable() -> int:
    """The auto-action readability gate: k + 1 confidently-read channels."""
    from backend.identity.config import default_scheme

    global _MIN_READABLE
    if _MIN_READABLE is None:
        _MIN_READABLE = default_scheme().code.k + 1
    return _MIN_READABLE


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_source(p):
        p.add_argument(
            "--db",
            default=os.getenv("DATABASE_URL"),
            help="SQLAlchemy URL (default: $DATABASE_URL). Read-only.",
        )
        p.add_argument(
            "--fixtures",
            default=None,
            help="an exported fixture directory, instead of a database",
        )
        p.add_argument("--game-id", default=None, help="restrict to one game")

    audit = subparsers.add_parser("audit", help="score the reviews already stored")
    add_source(audit)

    replay = subparsers.add_parser("replay", help="re-run the vision pipeline")
    add_source(replay)
    replay.add_argument("--out", required=True, help="JSONL output file (append)")
    replay.add_argument("--model", default=None, help="overrides OPENROUTER_MODEL")
    replay.add_argument(
        "--variant", default="baseline", help=f"one of {sorted(PROMPT_VARIANTS)}"
    )
    replay.add_argument("--limit", type=int, default=None)
    replay.add_argument("--concurrency", type=int, default=2)

    score = subparsers.add_parser("score", help="score replay JSONL file(s)")
    score.add_argument("replay_files", nargs="+")

    export = subparsers.add_parser(
        "export", help="export shots to a fixture directory (photos + manifest)"
    )
    add_source(export)
    export.add_argument("--out", required=True, help="output fixture directory")

    extract = subparsers.add_parser("extract", help="dump shot photos to PNG")
    add_source(extract)
    extract.add_argument("--out", required=True, help="output directory")
    extract.add_argument("shot_ids", nargs="*", help="restrict to these shots")

    args = parser.parse_args()
    needs_source = ("audit", "replay", "export", "extract")
    if args.command in needs_source and not (args.fixtures or args.db):
        raise SystemExit("pass --fixtures, --db, or set DATABASE_URL")
    if args.command == "export" and args.fixtures:
        raise SystemExit("export reads a database; --fixtures makes no sense here")

    {
        "audit": cmd_audit,
        "replay": cmd_replay,
        "score": cmd_score,
        "export": cmd_export,
        "extract": cmd_extract,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
