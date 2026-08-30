"""Tests for backend.shot_identification: ranking a game's candidates against a
stored vision reading.

The point of this module (roadmap #5) is that it identifies people who are
*not* wearing a canonical codeword, which the code-decode path cannot do, so
most of what is worth testing here is about overridden and freely-chosen
outfits, and about the location term staying evidence rather than becoming a
prior.
"""

import datetime
import json
import time
from types import SimpleNamespace
from uuid import uuid4 as get_uuid

import pytest

from backend import shot_identification as si
from backend import shot_vision
from backend.identity.config import default_scheme

SCHEME = default_scheme()


# -- helpers ----------------------------------------------------------------


def player(
    slot=None,
    overrides=None,
    team_id=None,
    hit_points=1,
    name="player",
    team_name="team",
):
    return SimpleNamespace(
        id=get_uuid(),
        name=name,
        team_id=team_id or get_uuid(),
        team_name=team_name,
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


_UNSET = object()


def shot_by(shooter, fixes=None, taken_at=_UNSET):
    return SimpleNamespace(
        user_id=shooter.id,
        location_context=json.dumps(fixes) if fixes is not None else None,
        # Naive UTC, as the database stores it. Every real shot has one, so
        # the default here is a time rather than None; pass `taken_at=None`
        # for the corrupt row that the column's NOT NULL exists to forbid.
        time_created=(
            None
            if taken_at is None
            else datetime.datetime.fromtimestamp(
                time.time() if taken_at is _UNSET else taken_at,
                datetime.timezone.utc,
            ).replace(tzinfo=None)
        ),
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


def test_a_lone_candidate_survives_one_misread():
    """A two-player game leaves exactly one candidate, and then there are no
    pairs to take an effective minimum distance over. Falling back to "no
    exact match" there makes the loosest candidate set the strictest test:
    the single misread [4,2,3] exists to correct flags the reading as fitting
    nobody, and the auto-action gate refuses a shot with one possible target.
    """
    shooter = player()
    target = player(slot=7)

    worn = dict(SCHEME.appearance_of_slot(7))
    palette = {channel.name: channel.labels for channel in SCHEME.channels}
    misread = dict(worn)
    misread["hat"] = next(c for c in palette["hat"] if c != worn["hat"])

    ranked = si.rank_candidates(shot_by(shooter), [shooter, target], review_of(misread))

    assert ranked.best == target.id
    assert ranked.confident and not ranked.ambiguous
    assert not ranked.inconsistent


def test_a_lone_candidate_is_still_contradicted_by_a_reading_that_fits_nobody():
    """The counterweight: one candidate must not mean every reading fits them.
    Two misreads are past what the code can correct, so the shot stays the
    admin's rather than being pinned on the only person available.
    """
    shooter = player()
    target = player(slot=7)

    worn = dict(SCHEME.appearance_of_slot(7))
    palette = {channel.name: channel.labels for channel in SCHEME.channels}
    misread = dict(worn)
    for garment in ("hat", "tshirt"):
        misread[garment] = next(c for c in palette[garment] if c != worn[garment])

    ranked = si.rank_candidates(shot_by(shooter), [shooter, target], review_of(misread))

    assert ranked.inconsistent


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


# -- the payload the admin queue reads ---------------------------------------


def test_the_payload_names_every_candidate_and_scores_their_distance():
    shooter = player(name="shooter")
    target = player(slot=7, name="target", team_name="reds")
    other = player(slot=21, name="other", team_name="blues")

    payload = si.identification_payload(
        shot_by(shooter),
        [shooter, target, other],
        review_of(SCHEME.appearance_of_slot(7)),
    )

    assert payload["readable_channels"] == len(list(SCHEME.channels))
    assert payload["confident"] and not payload["ambiguous"]
    assert not payload["inconsistent"]

    probabilities = [entry["probability"] for entry in payload["ranked"]]
    assert probabilities == sorted(probabilities, reverse=True)

    best, second = payload["ranked"]
    assert (best["user_id"], best["name"], best["team_name"]) == (
        str(target.id),
        "target",
        "reds",
    )
    assert second["name"] == "other"

    # The reading is exactly what the target is wearing, so nothing about it
    # contradicts them; the other candidate is contradicted once per garment
    # the two outfits disagree on.
    worn, theirs = SCHEME.appearance_of_slot(7), SCHEME.appearance_of_slot(21)
    assert best["code_distance"] == 0
    assert second["code_distance"] == sum(
        1 for channel, colour in worn.items() if theirs[channel] != colour
    )


def test_the_payload_carries_what_each_candidate_is_wearing():
    """The admin compares a candidate's colours with the reading by eye, so the
    ranking has to say what they are wearing - and say it in the review's own
    channel order and shape, or the two columns don't line up."""
    shooter = player(name="shooter")
    # An override, because the whole point of scoring against effective words
    # is the player who is not in their canonical codeword.
    worn = dict(SCHEME.appearance_of_slot(7))
    channel = SCHEME.channels.names[0]
    swapped = next(
        colour for colour in SCHEME.channels[0].labels if colour != worn[channel]
    )
    worn[channel] = swapped
    target = player(slot=7, overrides={channel: swapped}, name="target")

    payload = si.identification_payload(
        shot_by(shooter), [shooter, target, player(slot=21)], review_of(worn)
    )

    best = payload["ranked"][0]
    assert best["name"] == "target"
    assert list(best["outfit"]) == list(SCHEME.channels.names)
    assert {name: garment["colour"] for name, garment in best["outfit"].items()} == worn
    assert all(garment["hex"] for garment in best["outfit"].values())


def test_each_garment_is_marked_against_the_reading():
    """The green/red the admin looks at and the code distance printed beside it
    are the same comparison, so they must always agree: one red garment per
    unit of distance, and nothing marked either way where the model read
    nothing."""
    shooter = player(name="shooter")
    names = list(SCHEME.channels.names)
    worn = SCHEME.appearance_of_slot(7)
    # Read one garment as somebody else's colour and one not at all.
    misread, unread = names[0], names[1]
    reading = dict(worn)
    reading[misread] = next(
        colour for colour in SCHEME.channels[0].labels if colour != worn[misread]
    )
    reading[unread] = None

    payload = si.identification_payload(
        shot_by(shooter), [shooter, player(slot=7, name="target")], review_of(reading)
    )

    best = payload["ranked"][0]
    agrees = {name: garment["agrees"] for name, garment in best["outfit"].items()}
    assert agrees[misread] is False
    assert agrees[unread] is None
    assert all(agrees[name] is True for name in names[2:])

    assert (
        sum(1 for value in agrees.values() if value is False) == best["code_distance"]
    )


def test_an_unreadable_photograph_ranks_nobody():
    """Four erasures leave the prior handed back untouched, which would put
    somebody top on no evidence at all. That is a retake, not a recognition."""
    shooter = player()
    blank = {channel.name: None for channel in SCHEME.channels}

    payload = si.identification_payload(
        shot_by(shooter), [shooter, player(slot=7), player(slot=21)], review_of(blank)
    )

    assert payload == {
        "ranked": [],
        "readable_channels": 0,
        "confident": False,
        "ambiguous": False,
        "inconsistent": False,
    }


def test_the_payload_is_none_when_there_is_nobody_to_rank():
    shooter = player()
    review = review_of(SCHEME.appearance_of_slot(7))

    assert si.identification_payload(shot_by(shooter), [shooter], review) is None


def test_an_unread_garment_contradicts_nobody():
    """The distance is counted over what was actually read: erasing a garment
    the candidates disagree on must drop their distance, not their ranking."""
    shooter = player()
    target = player(slot=7)
    other = player(slot=21)

    worn = dict(SCHEME.appearance_of_slot(7))
    theirs = SCHEME.appearance_of_slot(21)
    disagreed = next(name for name, colour in worn.items() if theirs[name] != colour)
    partial = dict(worn, **{disagreed: None})

    def distance_to_other(appearance):
        payload = si.identification_payload(
            shot_by(shooter), [shooter, target, other], review_of(appearance)
        )
        entry = next(e for e in payload["ranked"] if e["user_id"] == str(other.id))
        return entry["code_distance"]

    assert distance_to_other(partial) == distance_to_other(worn) - 1


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


def test_a_shot_is_scored_as_of_when_it_was_taken():
    """A fix's age is measured from the photograph, not from the adjudication.

    The two are minutes apart in a live game, so this went unnoticed. It is
    ninety minutes on a replayed test-world shot (`npm run demoshots`) and
    unbounded on any shot an admin comes back to the morning after: every fix
    reads as stale, every Lambda collapses to 1, and the location term silently
    stops existing exactly when the queue is longest and the admin most wants
    the help.
    """
    shooter = player()
    near = player(slot=7)
    far = player(slot=7)  # deliberately identical: colour cannot separate them

    # Fixes contemporaneous with the shot, and the whole thing long ago.
    taken = 1_000_000.0
    fixes = [
        fix(shooter, 51.5000, -0.1000, taken),
        fix(near, 51.5001, -0.1000, taken),
        fix(far, 51.5300, -0.1000, taken),
    ]

    ranked = si.rank_candidates(
        shot_by(shooter, fixes, taken_at=taken),
        [shooter, near, far],
        review_of(SCHEME.appearance_of_slot(7)),
    )

    posteriors = dict(ranked.ranked)
    assert posteriors[near.id] > posteriors[far.id]
    assert ranked.best == near.id


def test_an_unstamped_shot_is_an_error_rather_than_scored_as_now():
    """There is no such shot: `submit_shot` is the only thing that writes one
    and the column is NOT NULL. Substituting the wall clock would turn a
    corrupt row into a plausible-looking ranking, which is the one outcome
    worse than a traceback."""
    shooter = player()
    with pytest.raises(ValueError, match="no time_created"):
        si.rank_candidates(
            shot_by(shooter, taken_at=None),
            [shooter, player(slot=7)],
            review_of(SCHEME.appearance_of_slot(7)),
        )


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
