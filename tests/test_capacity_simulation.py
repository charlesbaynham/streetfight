"""The capacity simulation in ``scripts/simulate_code_capacity.py``.

Worth testing because the answer it gives is a design input: it is only
meaningful if the packings it produces really are valid (every pair at least
``d`` apart) and really are maximal (nothing left that could have been added).
"""

from itertools import combinations
from random import Random

import pytest

from scripts.simulate_code_capacity import alphabet_sizes
from scripts.simulate_code_capacity import code_space
from scripts.simulate_code_capacity import hamming
from scripts.simulate_code_capacity import neighbour_table
from scripts.simulate_code_capacity import random_maximal_packing
from scripts.simulate_code_capacity import reed_solomon_capacities
from scripts.simulate_code_capacity import run_trials


@pytest.mark.parametrize("constrain_trousers", [True, False])
def test_packing_is_valid_and_maximal(constrain_trousers):
    points = code_space(alphabet_sizes(constrain_trousers))
    neighbours = neighbour_table(points, 3)
    rng = Random(1)

    for _ in range(5):
        chosen = [points[i] for i in random_maximal_packing(neighbours, rng)]

        for a, b in combinations(chosen, 2):
            assert hamming(a, b) >= 3

        for point in points:
            assert any(hamming(point, other) < 3 for other in chosen)


def test_constrained_packing_only_uses_wearable_trousers():
    points = code_space(alphabet_sizes(constrain_trousers=True))
    chosen = random_maximal_packing(neighbour_table(points, 3), Random(2))
    assert all(points[i][1] < 5 for i in chosen)


def test_neighbour_table_matches_brute_force():
    points = code_space([3, 3, 3])
    table = neighbour_table(points, 3)
    for i, point in enumerate(points):
        expected = {j for j, other in enumerate(points) if hamming(point, other) < 3}
        assert set(table[i]) == expected


def test_reed_solomon_baselines_match_the_plan():
    # Plan section 11.1: 49 codewords, 35 of them wearable with restricted trousers.
    assert reed_solomon_capacities() == {False: 49, True: 35}


@pytest.mark.parametrize("constrain_trousers", [True, False])
def test_free_choice_never_beats_the_algebraic_code(constrain_trousers):
    results = run_trials(constrain_trousers, trials=20, min_distance=3, seed=3)
    assert len(results) == 20
    assert max(results) <= reed_solomon_capacities()[constrain_trousers]


def test_seed_is_reproducible():
    first = run_trials(True, trials=10, min_distance=3, seed=7)
    assert first == run_trials(True, trials=10, min_distance=3, seed=7)
