"""``python -m backend.test_world`` -- build and inspect the test world.

    world   build world.json from a seed (free, no network)
    check   rebuild and confirm the output is byte-identical
    gate    print the human review summary for Gate A

Later phases (scene selection, image generation, observation) add their own
subcommands here and read the world file rather than rebuilding it.
"""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_OUT = Path("tests/fixtures/test_game/world.json")
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


def cmd_world(args) -> int:
    import tempfile

    from backend.test_world import world as world_mod
    from backend.test_world.movement import truth_track
    from backend.test_world.personas import build_cast

    with tempfile.TemporaryDirectory() as tmp:
        _scratch_db(Path(tmp) / "world.db")
        world = world_mod.build(args.seed)

    track = truth_track(args.seed, build_cast(args.seed))
    world_mod.save(world, Path(args.out), track=track)
    print(f"wrote {args.out} (seed {args.seed})")
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

    args = parser.parse_args(argv)
    return {"world": cmd_world, "check": cmd_check, "gate": cmd_gate}[args.command](
        args
    )


if __name__ == "__main__":
    raise SystemExit(main())
