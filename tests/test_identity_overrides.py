"""Tests for the admin-overrides helpers: effective words, distances, and the
free-channel suggestion / slot-picking flow, plus a decoder integration test
proving an overridden player still ranks top given a matching reading.

No DB, no network: everything is built directly from the pure scheme/channel
objects, the same style as test_identity_scheme.py / test_identity_decoder.py.
"""

import pytest

from backend.identity.config import TROUSERS_PALETTE
from backend.identity.config import default_scheme
from backend.identity.decoder import decode
from backend.identity.observations import ChannelObservation
from backend.identity.observations import Reading
from backend.identity.overrides import effective_word
from backend.identity.overrides import nearest_slots
from backend.identity.overrides import overlap_distance
from backend.identity.overrides import overrides_for
from backend.identity.overrides import pairwise_distances
from backend.identity.overrides import suggest_free_channels

# -- effective_word ----------------------------------------------------------


def test_effective_word_with_no_overrides_is_the_codeword():
    scheme = default_scheme()
    codeword = scheme.codeword_of_slot(scheme.usable_slots()[0])
    assert effective_word(codeword, {}, scheme.channels) == tuple(codeword)


def test_effective_word_substitutes_a_label():
    scheme = default_scheme()
    codeword = scheme.codeword_of_slot(scheme.usable_slots()[0])
    word = effective_word(codeword, {"tshirt": "yellow"}, scheme.channels)

    assert word[0] == scheme.channels.by_name("tshirt").label_to_index("yellow")
    assert word[1:] == tuple(codeword[1:])


def test_effective_word_none_marks_a_position_uninformative():
    scheme = default_scheme()
    codeword = scheme.codeword_of_slot(scheme.usable_slots()[0])
    word = effective_word(codeword, {"hat": None}, scheme.channels)

    assert word[2] is None
    assert word[0] == codeword[0]
    assert word[3] == codeword[3]


def test_effective_word_rejects_unknown_channel():
    scheme = default_scheme()
    codeword = scheme.codeword_of_slot(0)
    with pytest.raises(ValueError, match="unknown channels"):
        effective_word(codeword, {"cape": "red"}, scheme.channels)


def test_effective_word_rejects_unknown_label():
    scheme = default_scheme()
    codeword = scheme.codeword_of_slot(scheme.usable_slots()[0])
    # "yellow" is in the main palette but not the restricted trousers one.
    with pytest.raises(ValueError, match="no label"):
        effective_word(codeword, {"trousers": "yellow"}, scheme.channels)


def test_effective_word_rejects_wrong_length_codeword():
    scheme = default_scheme()
    with pytest.raises(ValueError):
        effective_word((0, 1, 2), {}, scheme.channels)


# -- overlap_distance ---------------------------------------------------------


def test_overlap_distance_matches_hamming_when_fully_known():
    assert overlap_distance((0, 1, 2, 3), (0, 1, 2, 3)) == 0
    assert overlap_distance((0, 1, 2, 3), (0, 1, 2, 4)) == 1
    assert overlap_distance((0, 1, 2, 3), (6, 5, 4, 3)) == 3


def test_overlap_distance_ignores_none_on_either_side():
    # A None on just one side can't be shown to disagree.
    assert overlap_distance((None, 1, 2, 3), (0, 1, 2, 3)) == 0
    assert overlap_distance((0, 1, 2, 3), (0, 1, 2, None)) == 0
    # Both None at a position: still can't be shown to disagree.
    assert overlap_distance((None, 1, 2, 3), (None, 5, 2, 3)) == 1  # only pos 1 differs


def test_overlap_distance_all_none_is_zero():
    assert overlap_distance((None, None, None), (None, None, None)) == 0


def test_overlap_distance_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        overlap_distance((0, 1), (0, 1, 2))


# -- pairwise_distances -------------------------------------------------------


def test_pairwise_distances_is_ascending_and_covers_every_pair():
    words = {"a": (0, 0, 0, 0), "b": (0, 0, 0, 1), "c": (6, 6, 6, 6)}
    pairs = pairwise_distances(words)

    assert len(pairs) == 3  # 3 choose 2
    assert [p[2] for p in pairs] == sorted(p[2] for p in pairs)
    assert {frozenset((p[0], p[1])) for p in pairs} == {
        frozenset(("a", "b")),
        frozenset(("a", "c")),
        frozenset(("b", "c")),
    }
    # a-b differ in exactly one position; a-c and b-c differ in all four.
    assert pairs[0] == ("a", "b", 1)


def test_pairwise_distances_ties_keep_generation_order():
    # a-b and a-c are both distance 1 from each other's construction; the
    # unordered-pair generation order (i, j) with i < j in dict order must be
    # preserved by the stable sort.
    words = {"a": (0, 0), "b": (0, 1), "c": (1, 0)}
    pairs = pairwise_distances(words)

    assert pairs == [("a", "b", 1), ("a", "c", 1), ("b", "c", 2)]


def test_pairwise_distances_empty_and_singleton():
    assert pairwise_distances({}) == []
    assert pairwise_distances({"a": (0, 0)}) == []


# -- suggest_free_channels -----------------------------------------------------


def _scheme():
    return default_scheme()  # tshirt, trousers, hat, armbands; q=7


def test_suggest_free_channels_maximises_distance_to_others():
    scheme = _scheme()
    channels = scheme.channels
    # Everyone visible is wearing the same tshirt/trousers/hat; only armbands
    # (the free channel) is still up to the admin.
    fixed = {"tshirt": "black", "trousers": "blue", "hat": "red"}
    other_word = effective_word((0, 0, 0, 0), {**fixed, "armbands": "black"}, channels)
    others = {"rival": other_word}

    suggestions = suggest_free_channels(fixed, ["armbands"], others, channels, limit=5)

    assert suggestions  # got something
    top = suggestions[0]
    assert top.min_distance == 1  # only armbands can ever differ here
    assert top.closest == ["rival"]
    assert top.assignment["armbands"] != "black"  # must not repeat the rival
    # Final deterministic tie-break is ascending symbol order: among the six
    # non-black armband options, the lowest-index one wins.
    assert top.assignment["armbands"] == channels.by_name("armbands").index_to_label(1)
    # Every one of the (up to 5) suggestions actually beats "black".
    assert all(s.assignment["armbands"] != "black" for s in suggestions)


def test_suggest_free_channels_respects_restricted_trousers_palette():
    scheme = _scheme()
    channels = scheme.channels
    fixed = {"tshirt": "black", "hat": "red", "armbands": "black"}

    suggestions = suggest_free_channels(
        fixed, ["trousers"], others={}, channels=channels, limit=10
    )

    # Only 5 trousers colours exist, even though q = 7 and armbands/tshirt do.
    assert len(suggestions) == 5
    assert {s.assignment["trousers"] for s in suggestions} == set(TROUSERS_PALETTE)


def test_suggest_free_channels_empty_others_uses_documented_sentinel():
    scheme = _scheme()
    channels = scheme.channels
    fixed = {"tshirt": "black", "trousers": "blue", "hat": "red"}

    suggestions = suggest_free_channels(fixed, ["armbands"], {}, channels, limit=3)

    assert suggestions
    for s in suggestions:
        assert s.min_distance == channels.n  # documented empty-others sentinel
        assert s.closest == []


def test_suggest_free_channels_avoids_avoid_words_and_all_black():
    scheme = _scheme()
    channels = scheme.channels
    fixed = {"tshirt": "black", "trousers": "blue", "hat": "red"}
    # An unassigned slot whose outfit is otherwise identical to `fixed` +
    # armbands=blue (index 3): squatting on it should be avoided even though
    # there are no other in-play players to conflict with.
    avoid_word = (0, 1, 2, 3)

    suggestions = suggest_free_channels(
        fixed, ["armbands"], others={}, channels=channels, avoid=[avoid_word], limit=10
    )
    armbands = channels.by_name("armbands")
    ordered_indices = [
        armbands.label_to_index(s.assignment["armbands"]) for s in suggestions
    ]

    assert len(ordered_indices) == 7
    # The avoid word's own armband colour (3) is dead last: it is the only
    # option with zero overlap distance to `avoid`.
    assert ordered_indices[-1] == 3
    # All-black (0) is also disfavoured, ranked below every other non-avoided
    # colour (it's closer to the all-zero passer-by word).
    assert ordered_indices.index(0) == len(ordered_indices) - 2
    # The winner is neither of those.
    assert ordered_indices[0] not in (0, 3)


def test_suggest_free_channels_rejects_channel_in_both_fixed_and_free():
    scheme = _scheme()
    with pytest.raises(ValueError):
        suggest_free_channels({"tshirt": "black"}, ["tshirt"], {}, scheme.channels)


def test_suggest_free_channels_rejects_unknown_channel_names():
    scheme = _scheme()
    with pytest.raises(ValueError):
        suggest_free_channels({"cape": "red"}, ["armbands"], {}, scheme.channels)


# -- nearest_slots + overrides_for round trip ----------------------------------


def test_nearest_slots_ranks_the_exact_match_first():
    scheme = default_scheme()
    slot = scheme.usable_slots()[10]
    word = scheme.codeword_of_slot(slot)

    assert nearest_slots(word, scheme)[0] == slot


def test_nearest_slots_ignores_none_positions_and_excludes_taken():
    scheme = default_scheme()
    slots = scheme.usable_slots()
    slot = slots[10]
    codeword = scheme.codeword_of_slot(slot)
    # Mask one channel: shouldn't cost anything against any slot.
    word = (None,) + tuple(codeword[1:])

    ranked = nearest_slots(word, scheme, taken=())
    assert ranked[0] == slot  # still the best match: 0 overrides needed

    ranked_excl = nearest_slots(word, scheme, taken=(slot,))
    assert slot not in ranked_excl
    assert set(ranked_excl) == set(slots) - {slot}


def test_nearest_slots_orders_by_overrides_needed_then_slot_number():
    scheme = default_scheme()
    slots = scheme.usable_slots()
    slot = slots[10]
    codeword = scheme.codeword_of_slot(slot)
    # Flip one concrete channel: `slot` now needs exactly 1 override to match.
    flipped = list(codeword)
    flipped[0] = (flipped[0] + 1) % scheme.channels.max_addressable_symbol(0)
    word = tuple(flipped)

    def cost(candidate_slot):
        other = scheme.codeword_of_slot(candidate_slot)
        return sum(1 for w, c in zip(word, other) if w != c)

    ranked = nearest_slots(word, scheme)
    costs = [cost(s) for s in ranked]

    assert costs == sorted(costs)  # non-decreasing cost
    for i in range(len(ranked) - 1):  # equal-cost runs are ascending by slot number
        if costs[i] == costs[i + 1]:
            assert ranked[i] < ranked[i + 1]
    # The MDS code's "any two channels identify the player" guarantee means no
    # other codeword can agree with `word` on 3 of its 4 positions, so the
    # single flipped symbol leaves `slot` a unique closest match.
    assert ranked[0] == slot
    assert costs[0] == 1


def test_overrides_for_round_trips_through_effective_word():
    scheme = default_scheme()
    slots = scheme.usable_slots()
    slot = slots[15]
    other_codeword = scheme.codeword_of_slot(slots[20])
    # A word that: agrees with `slot` on some channels, differs on one, and is
    # unknown (None) on another -- the general case.
    word = (other_codeword[0], None) + tuple(scheme.codeword_of_slot(slot)[2:])

    overrides = overrides_for(word, slot, scheme)
    roundtripped = effective_word(
        scheme.codeword_of_slot(slot), overrides, scheme.channels
    )

    assert roundtripped == word


def test_overrides_for_omits_agreeing_positions():
    scheme = default_scheme()
    slot = scheme.usable_slots()[0]
    codeword = scheme.codeword_of_slot(slot)

    assert overrides_for(tuple(codeword), slot, scheme) == {}


def test_overrides_for_reports_none_and_differing_labels():
    scheme = default_scheme()
    slot = scheme.usable_slots()[0]
    codeword = scheme.codeword_of_slot(slot)
    new_tshirt = (codeword[0] + 1) % scheme.channels.max_addressable_symbol(0)
    word = (new_tshirt, None) + tuple(codeword[2:])

    overrides = overrides_for(word, slot, scheme)

    assert overrides == {
        "tshirt": scheme.channels.by_name("tshirt").index_to_label(new_tshirt),
        "trousers": None,
    }


# -- decode() integration: an overridden player still ranks top ---------------


def test_decode_ranks_an_overridden_player_top():
    scheme = default_scheme()
    slots = scheme.usable_slots()
    target = slots[7]
    codeword = scheme.codeword_of_slot(target)

    # The player's real outfit: a wrong hat (they couldn't find the colour)
    # and armbands nobody could get a clean read on.
    wrong_hat = scheme.channels.by_name("hat").index_to_label(
        (codeword[2] + 1) % scheme.channels.max_addressable_symbol(2)
    )
    overrides = {"hat": wrong_hat, "armbands": None}
    target_word = effective_word(codeword, overrides, scheme.channels)
    assert target_word != tuple(codeword)  # genuinely not a codeword any more
    assert None in target_word

    candidates = {slot: scheme.codeword_of_slot(slot) for slot in slots}
    candidates[target] = target_word

    # Effective min distance across this candidate set no longer equals the
    # code's nominal d, per the decoder's documented convention.
    effective_min_distance = min(d for _, _, d in pairwise_distances(candidates))

    obs = []
    for symbol in target_word:
        if symbol is None:
            obs.append(ChannelObservation.erasure())
        else:
            label = scheme.channels[len(obs)].index_to_label(symbol)
            obs.append(ChannelObservation.best_guess(label, 0.9))
    reading = Reading(obs)

    result = decode(
        reading, candidates, scheme.channels, code_min_distance=effective_min_distance
    )

    assert result.best == target
    assert result.min_distance_to_codeword == 0
    assert not result.inconsistent
