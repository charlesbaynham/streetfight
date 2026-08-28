"""Tests for backend.shot_identification: ranking a game's candidates against a
stored vision reading.

The point of this module (roadmap #5) is that it identifies people who are
*not* wearing a canonical codeword, which the code-decode path cannot do, so
most of what is worth testing here is about overridden and freely-chosen
outfits, and about the location term staying evidence rather than becoming a
prior.
"""

import json
from types import SimpleNamespace
from uuid import uuid4 as get_uuid

import pytest

from backend import shot_identification as si
from backend import shot_vision
from backend.identity.config import default_scheme

SCHEME = default_scheme()


# -- helpers ----------------------------------------------------------------


def player(slot=None, overrides=None, team_id=None, hit_points=1, name="player"):
    return SimpleNamespace(
        id=get_uuid(),
        name=name,
        team_id=team_id or get_uuid(),
        hit_points=hit_points,
        identity_slot=slot,
        identity_overrides=json.dumps(overrides) if overrides else None,
    )


def review_of(appearance, confidence=0.9):
    """The stored review a vision model would produce seeing ``appearance``.

    ``None`` for a channel means it could not be read.
    """
    raw = {
        "shot_hit_a_person": True,
        "reasoning": "test",
        "confidence": 0.9,
        "channels": {
            name: (
                {"visible": False, "colour": "unknown", "confidence": 0.9}
                if colour is None
                else {"visible": True, "colour": colour, "confidence": confidence}
            )
            for name, colour in appearance.items()
        },
    }
    return shot_vision.classify(shot_vision.parse_result(raw), SCHEME).to_dict()


def shot_by(shooter, fixes=None):
    return SimpleNamespace(
        user_id=shooter.id,
        location_context=json.dumps(fixes) if fixes is not None else None,
    )


def fix(user, lat, lon, timestamp, accuracy=None):
    entry = {
        "user_id": str(user.id),
        "latitude": lat,
        "longitude": lon,
        "timestamp": timestamp,
    }
    if accuracy is not None:
        entry["accuracy"] = accuracy
    return entry


# -- the thing the code-decode path could not do -----------------------------


def test_an_overridden_player_is_still_identified():
    """The whole reason #5 exists: a player wearing something that is not their
    codeword is invisible to a decoder that decodes against the code."""
    shooter = player()
    # Wearing slot 7, except the trousers, which are recorded as what they
    # actually own. The resulting outfit is not a codeword of the scheme.
    worn = dict(SCHEME.appearance_of_slot(7))
    worn["trousers"] = "black" if worn["trousers"] != "black" else "green"
    target = player(slot=7, overrides={"trousers": worn["trousers"]})
    other = player(slot=21)

    ranked = si.rank_candidates(
        shot_by(shooter), [shooter, target, other], review_of(worn)
    )

    assert ranked.best == target.id
    assert ranked.confident

    # And the code-decode path really does fail on the same reading, so the
    # test above is not just restating what already worked.
    assert shot_vision.slot_candidates_from_review(review_of(worn)) != [7]


def test_two_readable_channels_still_identify_somebody():
    """The roadmap's stated symptom: two erasures is exactly what [4,2,3] is
    meant to survive, but the old path gave up when neither was the armbands."""
    shooter = player()
    worn = dict(SCHEME.appearance_of_slot(7))
    target = player(slot=7)
    others = [player(slot=s) for s in (13, 21, 27, 31)]

    partial = dict(worn)
    partial["armbands"] = None
    partial["hat"] = None

    ranked = si.rank_candidates(
        shot_by(shooter), [shooter, target, *others], review_of(partial)
    )

    assert ranked.best == target.id


def test_no_candidate_is_ever_given_a_zero_posterior():
    """A zero in a product is unrecoverable: a candidate at zero cannot be
    rescued by a photograph that reads their outfit perfectly."""
    shooter = player()
    candidates = [player(slot=s) for s in (7, 13, 21, 27)]

    ranked = si.rank_candidates(
        shot_by(shooter),
        [shooter, *candidates],
        review_of(SCHEME.appearance_of_slot(7)),
    )

    assert len(ranked.ranked) == len(candidates)
    assert all(posterior > 0 for _, posterior in ranked.ranked)


# -- who is a candidate at all ----------------------------------------------


def test_the_shooter_is_not_a_candidate():
    shooter = player(slot=7)
    alive = player(slot=21)

    assert si.eligible_candidates([shooter, alive], shooter.id) == [alive]


def test_a_knocked_out_player_is_still_a_candidate():
    """They are still standing there to be photographed -- most obviously in
    the seconds after the shot that killed them. A shot that hits them is a hit
    that does nothing, which beats matching nobody at all."""
    shooter = player(slot=7)
    dead = player(slot=13, hit_points=0)

    assert si.eligible_candidates([shooter, dead], shooter.id) == [dead]


def test_a_player_with_no_slot_is_not_a_candidate():
    """No slot means no effective word, so there is nothing to score them on."""
    shooter = player()
    unassigned = player(slot=None)

    assert si.eligible_candidates([shooter, unassigned], shooter.id) == []


def test_ranking_an_empty_field_is_none_rather_than_an_error():
    shooter = player()
    review = review_of(SCHEME.appearance_of_slot(7))
    assert si.rank_candidates(shot_by(shooter), [shooter], review) is None


# -- the location term ------------------------------------------------------


def test_a_teammate_is_a_less_likely_target_than_an_opponent():
    """Not impossible - hit_user performs no team check - just unlikely."""
    team = get_uuid()
    mate = player(slot=7, team_id=team)
    foe = player(slot=13)

    prior = si.structural_prior([mate, foe], team)

    assert prior[mate.id] < prior[foe.id]


def test_proximity_breaks_a_tie_between_identical_outfits():
    """Colour is the primary evidence; location exists to break ties."""
    shooter = player()
    near = player(slot=7)
    far = player(slot=7)  # deliberately identical: colour cannot separate them

    now = 1_000_000.0
    fixes = [
        fix(shooter, 51.5000, -0.1000, now),
        fix(near, 51.5001, -0.1000, now),
        fix(far, 51.5300, -0.1000, now),
    ]

    ranked = si.rank_candidates(
        shot_by(shooter, fixes),
        [shooter, near, far],
        review_of(SCHEME.appearance_of_slot(7)),
        at_time=now,
    )

    assert ranked.best == near.id


def test_a_stale_fix_goes_quiet_rather_than_eliminating_the_candidate():
    """As a fix ages the location term must tend to 1, leaving the image
    evidence to decide - never to 0, which no photograph could climb back from."""
    stale = player(slot=7)
    now = 1_000_000.0

    fresh_ratio = si.location_likelihood_ratios(
        {"latitude": 51.5, "longitude": -0.1},
        {stale.id: fix(stale, 51.5300, -0.1, now)},
        [stale.id],
        now,
    )[stale.id]
    aged_ratio = si.location_likelihood_ratios(
        {"latitude": 51.5, "longitude": -0.1},
        {stale.id: fix(stale, 51.5300, -0.1, now - 3600)},
        [stale.id],
        now,
    )[stale.id]

    assert fresh_ratio >= 1.0 and aged_ratio >= 1.0
    assert aged_ratio == pytest.approx(1.0)


def test_a_close_fix_is_stronger_evidence_than_a_distant_one():
    now = 1_000_000.0
    a, b = player(), player()
    ratios = si.location_likelihood_ratios(
        {"latitude": 51.5, "longitude": -0.1},
        {
            a.id: fix(a, 51.5001, -0.1, now),
            b.id: fix(b, 51.5100, -0.1, now),
        },
        [a.id, b.id],
        now,
    )

    assert ratios[a.id] > ratios[b.id]


def test_a_missing_or_unparseable_location_context_is_simply_no_evidence():
    shooter = player()
    target = player(slot=7)

    for raw in (None, "", "not json", '{"not": "a list"}'):
        assert si.parse_location_context(raw) == {}

    ranked = si.rank_candidates(
        shot_by(shooter), [shooter, target], review_of(SCHEME.appearance_of_slot(7))
    )
    assert ranked.best == target.id


def test_a_fix_without_a_position_is_dropped_not_defaulted():
    """ "We don't know where they were" must not become "they were at (0, 0)"."""
    a = player()
    raw = json.dumps(
        [
            {"user_id": str(a.id), "latitude": None, "longitude": None, "timestamp": 0},
        ]
    )
    assert si.parse_location_context(raw) == {}


def test_haversine_matches_a_known_separation():
    # One degree of latitude is about 111 km anywhere on the globe.
    assert si.haversine_m(51.0, -0.1, 52.0, -0.1) == pytest.approx(111_195, rel=0.01)
