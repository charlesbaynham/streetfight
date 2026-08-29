"""How much capacity does *free choice* of outfits cost, versus the algebraic code?

The `[4,2,3]` Reed-Solomon code (`backend/identity/code.py`) hands out codewords
that sit on an algebraic lattice: 49 of them, all pairwise Hamming distance >= 3,
which is the densest such set the space allows. The price is that a player cannot
choose their own outfit -- they get the slot the code gives them.

The alternative is to let people pick *any* outfit they like, as long as it is
still at least distance `d` from every outfit already handed out. The decoder
does not care (it only ever needs the pairwise distance guarantee, not the
lattice), but greedy free choice wastes space: an early pick can strand a region
of the space that a more careful choice would have kept usable.

This script measures that waste by Monte Carlo. Each trial repeatedly picks a
uniformly random *still-available* point until none is left -- a maximal random
packing -- and records how many players it fitted. Two configurations are run:

* **trousers constrained** -- trousers restricted to five colours (plan section
  2.6), so the space is 7*5*7*7 = 1715 points;
* **trousers unconstrained** -- every channel gets all seven colours, 7^4 = 2401
  points.

The live scheme is the unconstrained one: the guest list outgrew the 35 slots a
five-colour trousers channel allows, so that channel now carries a full seven of
its own (plan section 2.6 and 11.1 both name widening it as the remedy). Only
the counts matter here -- three of the four channels carry a physical palette of
their own, and none of it reaches the code. The constrained
row is kept because it is what the restriction cost, and the size the scheme
drops back to if a channel ever has to be narrowed again.

Output is a summary table on stdout plus an SVG histogram of the two capacity
distributions with the Reed-Solomon capacities marked for comparison.

Stdlib only, so it runs in the repo's Nix dev shell:

    python -m scripts.simulate_code_capacity --trials 1000 --out histogram.svg
"""

import argparse
import math
import random
import statistics
from collections import Counter
from itertools import combinations
from itertools import product
from typing import Dict
from typing import List
from typing import Sequence
from typing import Tuple

from backend.identity.config import DEFAULT_TARGET_DISTANCE
from backend.identity.config import default_channel_set
from backend.identity.config import default_scheme

Point = Tuple[int, ...]


# -- the code space ------------------------------------------------------


# How many colours the trousers channel carried while it was restricted (plan
# section 2.6). Named here rather than read off the live config, which has no
# narrowed channel left to read it from.
NARROW_TROUSERS = 5


def alphabet_sizes(constrain_trousers: bool) -> List[int]:
    """Wearable symbol count per channel, from the live config.

    Constrained means "pretend the trousers channel were still narrowed to five
    symbols": the point of the comparison is what a restricted channel costs.
    """
    channels = default_channel_set()
    sizes = [channels.max_addressable_symbol(i) for i in range(channels.n)]
    if constrain_trousers:
        trousers = channels.names.index("trousers")
        sizes[trousers] = min(sizes[trousers], NARROW_TROUSERS)
    return sizes


def code_space(sizes: Sequence[int]) -> List[Point]:
    """Every wearable outfit, as a tuple of per-channel symbol indices."""
    return list(product(*(range(size) for size in sizes)))


def neighbour_table(
    points: Sequence[Point], min_distance: int
) -> List[Tuple[int, ...]]:
    """For each point, the indices of the points it would exclude if chosen.

    That is every point within Hamming distance ``< min_distance`` of it,
    including itself. Built once per configuration and reused across trials --
    it is the whole cost of the simulation.
    """
    index = {point: i for i, point in enumerate(points)}
    n_positions = len(points[0])
    sizes = [max(point[i] for point in points) + 1 for i in range(n_positions)]
    table: List[Tuple[int, ...]] = []
    for point in points:
        excluded = [index[point]]
        for n_changes in range(1, min_distance):
            for positions in combinations(range(n_positions), n_changes):
                replacements = product(
                    *(
                        [s for s in range(sizes[pos]) if s != point[pos]]
                        for pos in positions
                    )
                )
                for values in replacements:
                    other = list(point)
                    for pos, value in zip(positions, values):
                        other[pos] = value
                    neighbour = index.get(tuple(other))
                    if neighbour is not None:
                        excluded.append(neighbour)
        table.append(tuple(excluded))
    return table


# -- the packing ---------------------------------------------------------


def random_maximal_packing(
    neighbours: Sequence[Tuple[int, ...]], rng: random.Random
) -> List[int]:
    """One trial: pick uniformly at random from the still-available points until
    none remain, and return the points picked.

    Lazy deletion keeps each pick O(1) amortised: dead entries stay in the
    candidate list and are swapped out when drawn, which does not bias the draw
    because rejecting a dead entry is just rejection sampling over the live ones.
    """
    alive = bytearray([1]) * len(neighbours)
    candidates = list(range(len(neighbours)))
    chosen: List[int] = []
    while candidates:
        i = rng.randrange(len(candidates))
        point = candidates[i]
        candidates[i] = candidates[-1]
        candidates.pop()
        if not alive[point]:
            continue
        chosen.append(point)
        for excluded in neighbours[point]:
            alive[excluded] = 0
    return chosen


def hamming(a: Sequence[int], b: Sequence[int]) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


def run_trials(
    constrain_trousers: bool,
    trials: int,
    min_distance: int,
    seed: int,
) -> List[int]:
    """Capacity reached by ``trials`` independent random maximal packings."""
    points = code_space(alphabet_sizes(constrain_trousers))
    neighbours = neighbour_table(points, min_distance)
    rng = random.Random(seed)
    return [len(random_maximal_packing(neighbours, rng)) for _ in range(trials)]


# -- the Reed-Solomon baselines -----------------------------------------


def reed_solomon_capacities() -> Dict[bool, int]:
    """Codewords the scheme offers, keyed by whether trousers are constrained.

    Unconstrained is the full ``q**k`` -- the live scheme, every channel
    wearing the whole palette. Constrained is the subset a five-colour trousers
    channel could wear (35 of the 49 -- the 34 in the plan plus the all-black
    word, which is excluded by policy, not by the code).
    """
    scheme = default_scheme()
    trousers = scheme.channels.names.index("trousers")
    return {
        False: scheme.capacity,
        True: sum(
            1
            for slot in range(scheme.capacity)
            if scheme.codeword_of_slot(slot)[trousers] < NARROW_TROUSERS
        ),
    }


# -- reporting -----------------------------------------------------------


def summarise(label: str, results: Sequence[int], baseline: int) -> str:
    mean = statistics.mean(results)
    return (
        f"{label:<26} n={len(results):<6} "
        f"min={min(results):<3} mean={mean:6.2f} "
        f"median={statistics.median(results):<5} max={max(results):<3} "
        f"sd={statistics.pstdev(results):5.2f}  "
        f"RS={baseline}  mean/RS={mean / baseline:5.1%}"
    )


def distribution_table(results: Sequence[int]) -> str:
    counts = Counter(results)
    lines = []
    for value in sorted(counts):
        share = counts[value] / len(results)
        lines.append(f"  {value:>3}  {counts[value]:>5}  {share:6.2%}")
    return "\n".join(lines)


# -- the histogram -------------------------------------------------------

# Categorical slots 1 and 2 of the validated default palette, light and dark.
SERIES = {
    "constrained": {"light": "#2a78d6", "dark": "#3987e5"},
    "unconstrained": {"light": "#eb6834", "dark": "#d95926"},
}


def _svg_style() -> str:
    """Theme-aware tokens: the SVG is readable on a white page or a dark one."""
    return """
  <style>
    .surface { fill: #fcfcfb; }
    .ink-primary { fill: #0b0b0b; }
    .ink-secondary { fill: #52514e; }
    .axis { stroke: #d7d6d1; }
    .grid { stroke: #ebeae6; }
    .s-constrained { fill: %(constrained_light)s; }
    .s-unconstrained { fill: %(unconstrained_light)s; }
    .k-constrained { stroke: %(constrained_light)s; }
    .k-unconstrained { stroke: %(unconstrained_light)s; }
    @media (prefers-color-scheme: dark) {
      .surface { fill: #1a1a19; }
      .ink-primary { fill: #ffffff; }
      .ink-secondary { fill: #c3c2b7; }
      .axis { stroke: #4a4945; }
      .grid { stroke: #2c2b29; }
      .s-constrained { fill: %(constrained_dark)s; }
      .s-unconstrained { fill: %(unconstrained_dark)s; }
      .k-constrained { stroke: %(constrained_dark)s; }
      .k-unconstrained { stroke: %(unconstrained_dark)s; }
    }
    text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
  </style>
""" % {
        "constrained_light": SERIES["constrained"]["light"],
        "constrained_dark": SERIES["constrained"]["dark"],
        "unconstrained_light": SERIES["unconstrained"]["light"],
        "unconstrained_dark": SERIES["unconstrained"]["dark"],
    }


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def histogram_svg(
    series: Sequence[Tuple[str, Sequence[int], int]],
    title: str,
    subtitle: str,
    width: int = 960,
    height: int = 520,
) -> str:
    """Grouped bar histogram: one bar pair per integer capacity, plus a dashed
    reference line at each series' Reed-Solomon capacity."""
    left, right, top, bottom = 64, 24, 92, 76
    plot_w = width - left - right
    plot_h = height - top - bottom

    counts = [Counter(values) for _, values, _ in series]
    baselines = [baseline for _, _, baseline in series]
    lo = min(min(c) for c in counts)
    hi = max(max(max(c) for c in counts), max(baselines))
    values = list(range(lo, hi + 1))
    total = max(len(v) for _, v, _ in series)
    peak = max(max(c.values()) for c in counts) / total
    y_max = math.ceil(peak / 0.05) * 0.05

    slot_w = plot_w / len(values)
    bar_w = max(1.0, (slot_w - 4) / len(series) - 2)

    def x_of(value: int, index: int) -> float:
        base = left + (value - lo) * slot_w + 2
        return base + index * (bar_w + 2)

    def y_of(share: float) -> float:
        return top + plot_h * (1 - share / y_max)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-label="{_escape(title)}">',
        _svg_style(),
        f'<rect class="surface" width="{width}" height="{height}"/>',
        f'<text class="ink-primary" x="{left}" y="34" font-size="19" '
        f'font-weight="600">{_escape(title)}</text>',
        f'<text class="ink-secondary" x="{left}" y="56" font-size="13">'
        f"{_escape(subtitle)}</text>",
    ]

    # Legend
    legend_x = left
    for i, (label, values_i, _) in enumerate(series):
        css = "s-constrained" if i == 0 else "s-unconstrained"
        out.append(
            f'<rect class="{css}" x="{legend_x}" y="66" width="10" height="10" rx="2"/>'
        )
        out.append(
            f'<text class="ink-secondary" x="{legend_x + 16}" y="75" font-size="12">'
            f"{_escape(label)}</text>"
        )
        legend_x += 22 + 7.2 * len(label)

    # Y grid + axis labels, in percent of trials.
    steps = 5
    for step in range(steps + 1):
        share = y_max * step / steps
        y = y_of(share)
        out.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" '
            f'y2="{y:.1f}" stroke-width="1"/>'
        )
        out.append(
            f'<text class="ink-secondary" x="{left - 8}" y="{y + 4:.1f}" '
            f'font-size="11" text-anchor="end">{share:.0%}</text>'
        )

    # Bars
    for i, (label, values_i, _) in enumerate(series):
        css = "s-constrained" if i == 0 else "s-unconstrained"
        for value, count in sorted(counts[i].items()):
            share = count / total
            y = y_of(share)
            h = top + plot_h - y
            out.append(
                f'<rect class="{css}" x="{x_of(value, i):.1f}" y="{y:.1f}" '
                f'width="{bar_w:.1f}" height="{h:.1f}" rx="2">'
                f"<title>{_escape(label)}: {value} players in "
                f"{count} of {total} runs ({share:.1%})</title></rect>"
            )

    # Reed-Solomon reference lines, drawn in each series' own colour so the
    # dashed line carries the identity and the label can stay in plain ink.
    for i, (label, _, baseline) in enumerate(series):
        css = "k-constrained" if i == 0 else "k-unconstrained"
        x = left + (baseline - lo + 0.5) * slot_w
        out.append(
            f'<line class="{css}" x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" '
            f'y2="{top + plot_h}" stroke-width="1.5" stroke-dasharray="4 3"/>'
        )
        anchor = "end" if i == 0 else "start"
        dx = -6 if i == 0 else 6
        out.append(
            f'<text class="ink-primary" x="{x + dx:.1f}" y="{top + 6}" '
            f'font-size="11" font-weight="600" text-anchor="{anchor}">'
            f"RS {baseline}</text>"
        )

    # X axis
    axis_y = top + plot_h
    out.append(
        f'<line class="axis" x1="{left}" y1="{axis_y}" x2="{left + plot_w}" '
        f'y2="{axis_y}" stroke-width="1"/>'
    )
    tick_every = 1 if len(values) <= 30 else 2
    for value in values:
        if (value - lo) % tick_every:
            continue
        x = left + (value - lo + 0.5) * slot_w
        out.append(
            f'<text class="ink-secondary" x="{x:.1f}" y="{axis_y + 16}" '
            f'font-size="11" text-anchor="middle">{value}</text>'
        )
    out.append(
        f'<text class="ink-secondary" x="{left + plot_w / 2:.1f}" '
        f'y="{height - 26}" font-size="12" text-anchor="middle">'
        "Players fitted before the space ran out</text>"
    )
    out.append(
        f'<text class="ink-secondary" x="16" y="{top + plot_h / 2:.1f}" '
        f'font-size="12" text-anchor="middle" '
        f'transform="rotate(-90 16 {top + plot_h / 2:.1f})">Share of runs</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


# -- entry point ---------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--trials", type=int, default=1000, help="runs per configuration"
    )
    parser.add_argument(
        "--distance",
        type=int,
        default=DEFAULT_TARGET_DISTANCE,
        help="minimum Hamming distance between any two outfits",
    )
    parser.add_argument("--seed", type=int, default=20260822)
    parser.add_argument(
        "--out",
        default="docs/code_capacity_histogram.svg",
        help="where to write the SVG histogram ('-' to skip)",
    )
    parser.add_argument(
        "--table", action="store_true", help="print the full distributions"
    )
    args = parser.parse_args(argv)

    baselines = reed_solomon_capacities()
    series = []
    print(
        f"Random maximal packing, d >= {args.distance}, {args.trials} runs per "
        f"configuration, seed {args.seed}\n"
    )
    for constrained in (True, False):
        label = "trousers constrained" if constrained else "trousers unconstrained"
        sizes = alphabet_sizes(constrained)
        space = 1
        for size in sizes:
            space *= size
        results = run_trials(constrained, args.trials, args.distance, args.seed)
        baseline = baselines[constrained]
        print(f"{label}: alphabet sizes {sizes}, {space} points in the space")
        print(summarise(label, results, baseline))
        if args.table:
            print(distribution_table(results))
        print()
        series.append((label, results, baseline))

    if args.out != "-":
        svg = histogram_svg(
            series,
            title="Free choice of outfit fits 19-28% fewer players than the code does",
            subtitle=(
                f"{args.trials} random maximal packings per configuration, "
                f"minimum Hamming distance {args.distance}. Dashed lines: the "
                "Reed-Solomon capacity."
            ),
        )
        with open(args.out, "w") as handle:
            handle.write(svg + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
