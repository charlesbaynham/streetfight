"""``python -m backend.test_world`` -- build and inspect the test world.

    world   build world.json from a seed (free, no network)
    check   rebuild and confirm the output is byte-identical
    gate    print the human review summary for Gate A
    shots   replay the cropped demo shots into the sample game

Later phases (scene selection, image generation, observation) add their own
subcommands here and read the world file rather than rebuilding it.
"""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "world.json"
DEFAULT_SEED = 20260919  # the game date, so the default world is not arbitrary


def _scratch_db(path: Path):
    """Point the ORM at a throwaway database and create the schema."""
    os.environ["DATABASE_URL"] = f"sqlite:///{path.resolve()}"
    os.environ.pop("MAKE_DEBUG_ENTRIES", None)
    os.environ.pop("RESET_DATABASE", None)

    import backend.database as database

    database.load()
    from backend.model import Base

    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)


def carry_paid_work_forward(world: dict, out: Path) -> int:
    """Move anything that cost money from the old world file into the new one.

    `build` makes the world from the seed alone and knows nothing about the
    localisation boxes, which are bought one at a time and keyed by image id
    -- so they stay true however the world around them is rebuilt. Without
    this they go every time `world` runs, and they went twice before it
    existed. Everything else derived (scenes, crops, measurements) is free to
    recompute and is deliberately left to be.
    """
    from backend.test_world import world as world_mod

    if not Path(out).exists():
        return 0
    previous = world_mod.load(Path(out)).get("boxes") or {}
    if previous:
        world["boxes"] = previous
    return len(previous)


def cmd_world(args) -> int:
    import tempfile

    from backend.test_world import world as world_mod
    from backend.test_world.movement import truth_track
    from backend.test_world.personas import build_cast

    with tempfile.TemporaryDirectory() as tmp:
        _scratch_db(Path(tmp) / "world.db")
        world = world_mod.build(args.seed)

    out = Path(args.out)
    carried = carry_paid_work_forward(world, out)
    if carried:
        print(f"  carried {carried} localisation boxes across")

    track = truth_track(args.seed, build_cast(args.seed))
    world_mod.save(world, out, track=track)
    print(f"wrote {out} (seed {args.seed})")
    print(f"  {len(world['cast'])} players, {len(world['teams'])} teams")
    print(f"  {sum(len(v) for v in world['fixes'].values())} fixes")
    print(f"  {len(world['encounters'])} encounters")
    return 0


def cmd_check(args) -> int:
    """Invariant 2: the master seed determines the world completely."""
    import tempfile

    from backend.test_world import world as world_mod

    digests = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as tmp:
            _scratch_db(Path(tmp) / "world.db")
            digests.append(world_mod.reproducible_core(world_mod.build(args.seed)))

    if digests[0] != digests[1]:
        # Say *where*, not merely that: a drifting world is usually one key.
        import json

        a, b = (json.loads(d) for d in digests)
        differing = [
            k
            for k in a
            if json.dumps(a[k], sort_keys=True) != json.dumps(b[k], sort_keys=True)
        ]
        print(f"NOT reproducible - differing keys: {differing}", file=sys.stderr)
        return 1

    print(f"reproducible: two builds of seed {args.seed} agree byte for byte")
    return 0


def _load(args):
    import numpy as np

    from backend.test_world import world as world_mod

    world = world_mod.load(Path(args.out))
    positions = np.load(Path(args.out).with_suffix(".truth.npz"))["positions"]
    return world, positions


def cmd_scenes(args) -> int:
    from backend.test_world import scenes as scenes_mod
    from backend.test_world import swatches
    from backend.test_world import world as world_mod

    world, positions = _load(args)
    world["scenes"] = scenes_mod.build(world, positions)
    world_mod.save(world, Path(args.out))
    card = swatches.render(Path(args.out).parent / "kit_swatches.png")

    scenes = world["scenes"]
    print(
        f"selected and described {len(scenes['shots'])} shots, "
        f"{len(scenes['references'])} reference photos, 1 background"
    )
    print(f"  {len(scenes['shots']) + len(scenes['references']) + 1} prompts in total")
    print(f"  wrote {card}")
    return 0


def cmd_availability(args) -> int:
    """Which (locale kind, light, distance) cells the world can actually serve."""
    import datetime
    import math
    from collections import Counter

    from backend.test_world import scenarios as scen
    from backend.test_world import spec as spec_mod

    world, positions = _load(args)
    index_of = {p["slug"]: i for i, p in enumerate(world["cast"])}
    counts = Counter()
    for event in world["encounters"]:
        ia, ib = index_of[event["a"]], index_of[event["b"]]
        seen = set()
        for tick in range(event["first_tick"], event["last_tick"] + 1):
            delta = positions[tick, ia] - positions[tick, ib]
            separation = math.hypot(delta[0], delta[1])
            band = next(
                (
                    k
                    for k, (lo, hi) in scen.DISTANCE_BANDS.items()
                    if lo <= separation <= hi
                ),
                None,
            )
            if band is None:
                continue
            moment = spec_mod.START_LOCAL + datetime.timedelta(seconds=int(tick))
            seen.add((event["locale_kind"], spec_mod.light_band(moment), band))
        for key in seen:
            counts[key] += 1

    print(f"{'locale':10s} {'light':9s} {'distance':9s} encounters")
    for locale_kind in ("street", "park", "forecourt"):
        for light in ("daylight", "twilight", "dark"):
            for band in ("close", "mid", "distant"):
                n = counts[(locale_kind, light, band)]
                flag = "   <- EMPTY" if n == 0 else ""
                print(f"{locale_kind:10s} {light:9s} {band:9s} {n:5d}{flag}")
    return 0


def cmd_gate_b(args) -> int:
    world, _ = _load(args)
    scenes = world.get("scenes")
    if not scenes:
        print("no scenes yet - run `scenes` first", file=sys.stderr)
        return 1

    only = getattr(args, "only", None)
    if only in (None, "background"):
        print("=" * 78)
        print("BACKGROUND (generated once, reused by all thirty reference photos)")
        print("=" * 78)
        print(scenes["background"]["prompt"])
        print()

    for shot in scenes["shots"]:
        if only and only != shot["scenario"]:
            continue
        print("=" * 78)
        print(
            f"{shot['scenario']}  intended: {shot['intended_result']}  "
            f"({shot['probes']})"
        )
        print(
            f"  encounter {shot['encounter_id']} at {shot['time_local']}, "
            f"{shot['locale']} - {shot['separation_m']} m apart"
        )
        print(
            f"  heading {shot['heading']} (true {shot['true_bearing']}, "
            f"compass {shot['compass_class']})"
        )
        for role, row in shot["telemetry"].items():
            if row.get("fix_age_s") is None:
                print(f"  {role:8s} {row['slug']}: never reported")
            else:
                print(
                    f"  {role:8s} {row['slug']:15s} {row['phone_class']:16s} "
                    f"fix {row['fix_age_s']:5d}s old, {row['fix_error_m']:6.1f} m out, "
                    f"Lambda {row['lambda_at_true_position']}"
                )
        if shot.get("misread"):
            m = shot["misread"]
            print(
                f"  MISREAD: {m['channel']} is really {m['true_colour']}, "
                f"photographed as {m['photographed_as']} "
                f"(distance {m['distance_to_target']} to target vs "
                f"{m['distance_to_nearest_other']} to {m['nearest_other']})"
            )
        print("-" * 78)
        print(shot["prompt"])
        print()

    if only in (None, "references"):
        for reference in scenes["references"]:
            print("=" * 78)
            print(f"REFERENCE {reference['slug']} ({reference['team']})")
            print("-" * 78)
            print(reference["prompt"])
            print()
    return 0


def cmd_generate(args) -> int:
    from backend.test_world import generate as generate_mod
    from backend.test_world import store as store_mod

    world, _ = _load(args)
    if "scenes" not in world:
        print("no scenes yet - run `scenes` first", file=sys.stderr)
        return 1

    out = Path(args.out)
    store = store_mod.ImageStore(out.parent / "images")
    gate = args.gate if args.gate != "e" else None

    spent = 0.0
    failed = []
    # Reference photos first, then the shots that are conditioned on them: a
    # shot's identity includes its target's reference photo, so it can only be
    # planned once that photo is in the store. Each pass picks up whatever the
    # last one unblocked, and the loop ends when nothing new was generated.
    while True:
        plan = generate_mod.plan(world, out, gate=gate, store=store)
        report = generate_mod.run_sync(
            plan.jobs, store, dry_run=not args.execute, blocked=len(plan.blocked)
        )

        print(
            f"planned {report['total']} image(s); "
            f"{report['already_present']} already in the store, "
            f"{report['to_generate']} to generate"
        )
        print(
            f"estimated cost ${report['estimated_usd']:.2f} now"
            + (
                f" + ${report['blocked_usd']:.2f} once the shots unblock"
                if report["blocked_usd"]
                else ""
            )
            + f" (ceiling ${generate_mod.HARD_CEILING_USD:.2f})"
        )
        for job in report["missing"]:
            print(
                f"  {job.kind:10s} {job.name:16s} {job.model:24s} "
                f"${job.price:.4f}  -> {job.image_id}.jpg"
            )
        for waiting in plan.blocked:
            print(f"  shot       {waiting:16s} after its reference photo")

        if not report.get("ran"):
            print("\nnothing was sent. Re-run with --execute to spend.")
            return 0

        spent += report["spent_usd"]
        failed += report["failed"]
        if not plan.blocked or not report["generated"]:
            break
        print()

    print(f"\nactually spent ${spent:.3f}, {len(failed)} failed")
    for kind, name, err in failed:
        print(f"  FAILED {kind} {name}: {err}", file=sys.stderr)
    return 1 if failed else 0


def cmd_observe(args) -> int:
    """Localise, crop, measure. The boxes cost money once and are cached."""
    import asyncio

    from PIL import Image

    from backend.image_processing import prepare_for_vision
    from backend.test_world import crop as crop_mod
    from backend.test_world import generate as generate_mod
    from backend.test_world import localise as localise_mod
    from backend.test_world import measure as measure_mod
    from backend.test_world import store as store_mod
    from backend.test_world import world as world_mod

    world, _ = _load(args)
    out = Path(args.out)
    store = store_mod.ImageStore(out.parent / "images")
    scenes = world.get("scenes")
    if not scenes:
        print("no scenes yet - run `scenes` first", file=sys.stderr)
        return 1

    plan = generate_mod.plan(world, out, store=store)
    by_name = {(job.kind, job.name): job for job in plan.jobs}

    # Keyed by image id, not by scenario, and kept outside "scenes" -- which
    # `scenes` rewrites wholesale, and did once throw away every box that had
    # been paid for. An id already encodes the prompt that made the picture,
    # so an edited scene description gets a new id and no stale box comes
    # with it. Same bargain as the image store: pay once, never again.
    boxes = world.setdefault("boxes", {})

    def job_for(kind, name):
        job = by_name.get((kind, name))
        if job is None or not store.has(job.image_id):
            return None
        return job

    entries = [("reference", r["slug"], r) for r in scenes["references"]]
    entries += [("shot", s["scenario"], s) for s in scenes["shots"]]

    def boxes_for(kind, name):
        job = job_for(kind, name)
        return boxes.get(job.image_id) if job else None

    # A stored reading with no subject in it is a failure that happened to
    # get written down, so it counts as missing and is asked for again.
    missing = [
        (kind, name, entry)
        for kind, name, entry in entries
        if job_for(kind, name) and not (boxes_for(kind, name) or {}).get("subject")
    ]
    print(
        f"{len(entries) - len(missing)} of {len(entries)} already localised; "
        f"{len(missing)} to do (~${len(missing) * 0.003:.2f})"
    )

    if missing and args.execute:

        async def run_all():
            semaphore = asyncio.Semaphore(generate_mod.CONCURRENCY)

            async def one(kind, name, entry):
                async with semaphore:
                    job = job_for(kind, name)
                    path = store.path_for(job.image_id)
                    with Image.open(path) as image:
                        size = image.size
                    # Downsized exactly as the real vision path downsizes a
                    # shot: a 2048px generation is 640KB of base64 per
                    # request, and with retries that is minutes of upload for
                    # a box a 1024px copy locates just as well. The boxes are
                    # normalised, so nothing is lost by sending less.
                    url = prepare_for_vision(generate_mod.data_url(path))
                    try:
                        boxes[job.image_id] = await localise_mod.locate(url, size)
                    except Exception as e:  # noqa: BLE001 - reported
                        print(f"  FAILED {kind} {name}: {e}", file=sys.stderr)

            await asyncio.gather(*(one(*row) for row in missing))

        asyncio.run(run_all())
        world_mod.save(world, out)
    elif missing:
        print("nothing was sent. Re-run with --execute to spend.")
        return 0

    # Crops: free, deterministic, and rewritten every time so a changed rule
    # takes effect without paying for anything again.
    crops = {}
    for shot in scenes["shots"]:
        job = job_for("shot", shot["scenario"])
        found = boxes_for("shot", shot["scenario"])
        if job is None or not (found or {}).get("subject"):
            continue
        target = out.parent / "shots" / f"{shot['scenario']}.jpg"
        crops[shot["scenario"]] = crop_mod.render(
            store.path_for(job.image_id), target, shot, found
        )

    # Measurements: recorded, reported, and triggering nothing.
    players = world["identity"]["players"]
    readings = []
    for reference in scenes["references"]:
        job = job_for("reference", reference["slug"])
        found = boxes_for("reference", reference["slug"])
        if job is None or not (found or {}).get("subject"):
            continue
        appearance = players[reference["slug"]]["appearance"]
        source = store.path_for(job.image_id)
        for row in measure_mod.kit_colours(source, found, appearance):
            readings.append(dict(row, slug=reference["slug"]))

    world["observations"] = {
        "kit_colour": readings,
        "wardrobe_variance": measure_mod.wardrobe_variance(readings),
        "crops": crops,
    }
    world_mod.save(world, out)

    print(f"\ncropped {len(crops)} shots into {out.parent / 'shots'}")
    _print_observations(world["observations"])
    return 0


def _print_observations(observations) -> None:
    readings = observations["kit_colour"]
    print("\n-- kit colour, measured against PALETTE_HEX --")
    if readings:
        worst = sorted(readings, key=lambda r: -r["delta_e"])[:8]
        by_channel = {}
        for row in readings:
            by_channel.setdefault(row["channel"], []).append(row["delta_e"])
        for channel, values in sorted(by_channel.items()):
            print(
                f"  {channel:9s} n={len(values):3d}  median dE "
                f"{sorted(values)[len(values) // 2]:5.1f}  worst {max(values):5.1f}"
            )
        print("  furthest from the hex asked for:")
        for row in worst:
            print(
                f"    {row['slug']:15s} {row['channel']:9s} {row['colour']:10s} "
                f"wanted {row['wanted_hex']} got {row['measured_hex']} "
                f"dE {row['delta_e']}"
            )

    print("\n-- wardrobe variance (same label, different players) --")
    print("   hats and armbands are ours, so a small spread is right;")
    print("   t-shirts are the player's own, so a spread of zero is a fault.")
    for row in observations["wardrobe_variance"]:
        print(
            f"  {row['channel']:9s} {row['colour']:10s} worn by "
            f"{row['worn_by']:2d}  mean dE {row['mean_pairwise_delta_e']:5.1f}  "
            f"max {row['max_pairwise_delta_e']:5.1f}"
        )

    print("\n-- crosshair geometry --")
    for scenario, row in sorted(observations["crops"].items()):
        note = "" if row["crosshair_offset"] < 0.01 else "   <- slid off an edge"
        print(
            f"  {scenario:4s} aim {row['aim_point']}  crop {row['crop_box']}  "
            f"offset {row['crosshair_offset']}{note}"
        )


def cmd_shots(args) -> int:
    """Put the cropped demo shots into the sample game (`npm run demoshots`)."""
    from backend.test_world import replay as replay_mod

    try:
        made = replay_mod.load_shots(
            args.seed,
            Path(args.out),
            images_dir=args.images,
            only=args.only.split(",") if args.only else None,
        )
    except RuntimeError as problem:
        print(problem, file=sys.stderr)
        return 1

    print(f"game {made['game_id']}")
    for row in made["loaded"]:
        print(
            f"  {row['scenario']:4s} {row['seconds_ago'] // 60:3d} min ago  "
            f"{row['shooter']:15s} -> {row['target']:15s} "
            f"({row['intended_result']})"
        )
    print(
        f"loaded {len(made['loaded'])}, "
        f"{len(made['skipped'])} already there, "
        f"{len(made['missing'])} with no cropped image"
    )
    if made["missing"]:
        print(
            "  missing: "
            + ", ".join(made["missing"])
            + " - run `observe --execute` to crop them",
            file=sys.stderr,
        )
    print(f"put {made['located']} players back where the game left them")
    return 0


def cmd_gate(args) -> int:
    import json

    from backend.test_world import world as world_mod

    world = world_mod.load(Path(args.out))
    print(f"=== Gate A: seed {world['seed']}, {world['venue']['name']} ===")
    print(json.dumps(world["clock"], indent=1))
    print("\n-- teams --")
    colours = world.get("identity", {}).get("team_colours", {})
    for team in world["teams"]:
        print(
            f"  {team['name']:14s} {colours.get(team['name'],'?'):10s} from {team['start_landmark']}"
        )
    print("\n-- telemetry, as it actually came out --")
    for name, row in world["telemetry_summary"].items():
        print(
            f"  {name:16s} median age {row['median_age_s']:>6.0f}s  "
            f"p90 {row['p90_age_s']:>6.0f}s  median error {row['median_position_error_m']:>5.0f}m"
        )
        print(f"  {'':16s} {row['note']}")
    print("\n-- encounter pool --")
    print(json.dumps(world["encounter_summary"], indent=1))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.test_world")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("world", help="build world.json from the seed")
    sub.add_parser("check", help="confirm the build is byte-reproducible")
    sub.add_parser("gate", help="print the Gate A review summary")
    sub.add_parser("scenes", help="select and describe the ten scenes (free)")
    sub.add_parser("availability", help="which (locale, light, distance) cells exist")
    gate_b = sub.add_parser("gateb", help="print every prompt for review")
    gate_b.add_argument("--only", help="one scenario id, or 'references'")
    gen = sub.add_parser("generate", help="generate missing images (costs money)")
    gen.add_argument("--gate", choices=["c", "d", "e"], help="which subset")
    gen.add_argument(
        "--execute",
        action="store_true",
        help="actually spend; without this it only says what it would do",
    )
    obs = sub.add_parser("observe", help="localise, crop and measure")
    obs.add_argument(
        "--execute",
        action="store_true",
        help="actually spend on localisation; crops and measurements are free",
    )
    shots = sub.add_parser("shots", help="replay the demo shots into the sample game")
    shots.add_argument(
        "--images", help="where the cropped shots are (default: next to world.json)"
    )
    shots.add_argument("--only", help="comma-separated scenario ids, e.g. S4,S9")

    args = parser.parse_args(argv)
    return {
        "world": cmd_world,
        "check": cmd_check,
        "gate": cmd_gate,
        "scenes": cmd_scenes,
        "availability": cmd_availability,
        "gateb": cmd_gate_b,
        "generate": cmd_generate,
        "observe": cmd_observe,
        "shots": cmd_shots,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
