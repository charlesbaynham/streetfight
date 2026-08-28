"""The team-colour slot allocation (backend/identity/allocation.py)."""

import pytest

from backend.identity.allocation import allocate_team_slots
from backend.identity.allocation import assign_team_colours
from backend.identity.allocation import colour_capacity
from backend.identity.allocation import group_slots_by_channel
from backend.identity.config import TEAM_CHANNEL
from backend.identity.config import default_scheme

SCHEME = default_scheme()

# The default scheme's team channel holds seven colours, six worth seven usable
# slots and black worth six (48 usable slots in total -- slot 0, the all-black
# codeword, is the one black loses).
BUCKET_SIZE = 7


def hats(slots):
    return [SCHEME.appearance_of_slot(slot)[TEAM_CHANNEL] for slot in slots]


def test_group_slots_by_channel_partitions_the_usable_slots():
    buckets = group_slots_by_channel(SCHEME, TEAM_CHANNEL)

    grouped = [slot for _, slots in buckets for slot in slots]
    assert sorted(grouped) == SCHEME.usable_slots()

    # Every slot in a bucket wears that bucket's colour, and the buckets come
    # biggest first so allocation spends the roomiest colours before black.
    for label, slots in buckets:
        assert hats(slots) == [label] * len(slots)
        assert slots == sorted(slots)
    sizes = [len(slots) for _, slots in buckets]
    assert sizes == sorted(sizes, reverse=True)


def test_group_slots_by_channel_rejects_an_unknown_channel():
    with pytest.raises(ValueError):
        group_slots_by_channel(SCHEME, "moustache")


@pytest.mark.parametrize("n_teams,slots_per_team", [(1, 1), (2, 3), (4, 5), (7, 4)])
def test_each_team_gets_one_colour_when_it_fits(n_teams, slots_per_team):
    allocations = allocate_team_slots(SCHEME, n_teams, slots_per_team, TEAM_CHANNEL)

    assert len(allocations) == n_teams

    colours = []
    for allocation in allocations:
        assert len(allocation.slots) == slots_per_team
        assert len(allocation.labels) == 1
        assert hats(allocation.slots) == allocation.labels * slots_per_team
        colours.append(allocation.labels[0])

    # ...and no two teams share it, which is the entire point
    assert len(set(colours)) == n_teams


def test_slots_are_unique_across_teams_and_usable():
    allocations = allocate_team_slots(SCHEME, 4, 8, TEAM_CHANNEL)

    slots = [slot for a in allocations for slot in a.slots]
    assert len(slots) == len(set(slots)) == 32
    assert set(slots) <= set(SCHEME.usable_slots())


def test_an_oversized_team_takes_a_second_whole_colour_after_the_first():
    n_teams, slots_per_team = 2, BUCKET_SIZE + 3
    allocations = allocate_team_slots(SCHEME, n_teams, slots_per_team, TEAM_CHANNEL)

    for allocation in allocations:
        # The minimum number of colours: two, not "spread over whatever fits"
        assert len(allocation.labels) == 2
        primary, secondary = allocation.labels

        # ...and the first bucketful is contiguous, so a team that never fills
        # its block is still all one colour
        assert hats(allocation.slots) == [primary] * BUCKET_SIZE + [secondary] * 3

    # The overflow colours are exclusive too - a hat colour still names one team
    all_labels = [label for a in allocations for label in a.labels]
    assert len(set(all_labels)) == len(all_labels)


def test_allocation_is_deterministic_so_reprints_match():
    first = allocate_team_slots(SCHEME, 3, 6, TEAM_CHANNEL)
    second = allocate_team_slots(SCHEME, 3, 6, TEAM_CHANNEL)

    assert [a.slots for a in first] == [a.slots for a in second]
    assert [a.labels for a in first] == [a.labels for a in second]


def test_colours_run_out_before_slots_do_and_the_leftovers_still_fill():
    # 2 x 24 = every usable slot, far more than seven colours can keep apart
    allocations = allocate_team_slots(SCHEME, 2, 24, TEAM_CHANNEL)

    slots = [slot for a in allocations for slot in a.slots]
    assert sorted(slots) == SCHEME.usable_slots()

    for allocation in allocations:
        # The first bucketful is still one clean colour, and labels report
        # honestly on the rest
        assert (
            hats(allocation.slots[:BUCKET_SIZE]) == [allocation.labels[0]] * BUCKET_SIZE
        )
        assert set(hats(allocation.slots)) == set(allocation.labels)


def test_more_slots_than_the_scheme_has_is_an_error():
    with pytest.raises(ValueError):
        allocate_team_slots(SCHEME, 2, 25, TEAM_CHANNEL)  # 50 > 48 usable


@pytest.mark.parametrize("n_teams,slots_per_team", [(0, 4), (2, 0), (-1, 4)])
def test_nonsense_requests_are_rejected(n_teams, slots_per_team):
    with pytest.raises(ValueError):
        allocate_team_slots(SCHEME, n_teams, slots_per_team, TEAM_CHANNEL)


def test_assign_team_colours_keeps_pinned_teams_and_colours_the_rest_freshly():
    existing = {"reds": "red", "blues": "blue", "newcomers": None}

    assigned = assign_team_colours(SCHEME, TEAM_CHANNEL, existing)

    assert assigned["reds"] == "red"
    assert assigned["blues"] == "blue"
    assert assigned["newcomers"] not in {"red", "blue"}


def test_assign_team_colours_rejects_more_teams_than_the_channel_has_colours():
    existing = {
        f"team{i}": None for i in range(len(colour_capacity(SCHEME, TEAM_CHANNEL)) + 1)
    }

    with pytest.raises(ValueError):
        assign_team_colours(SCHEME, TEAM_CHANNEL, existing)


def test_assign_team_colours_on_a_fresh_game_follows_the_bucket_order():
    buckets = group_slots_by_channel(SCHEME, TEAM_CHANNEL)
    existing = {f"team{i}": None for i in range(len(buckets))}

    assigned = assign_team_colours(SCHEME, TEAM_CHANNEL, existing)

    assert [assigned[f"team{i}"] for i in range(len(buckets))] == [
        label for label, _ in buckets
    ]


def test_colour_capacity_matches_group_slots_by_channel_bucket_sizes():
    capacity = colour_capacity(SCHEME, TEAM_CHANNEL)

    assert capacity == {
        label: len(slots)
        for label, slots in group_slots_by_channel(SCHEME, TEAM_CHANNEL)
    }
    assert capacity["black"] == BUCKET_SIZE - 1
    non_black = {label: size for label, size in capacity.items() if label != "black"}
    assert set(non_black.values()) == {BUCKET_SIZE}
