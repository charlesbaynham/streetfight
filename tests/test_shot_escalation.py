"""Tests for the escalated second opinion (backend.shot_escalation).

Nothing here touches the network: every test injects a FakeVisionClient. What
is worth pinning down is mostly the *contract*: what the stronger model is
shown (and what it is deliberately not shown), that Python keeps the
thresholds, and that a failure lands the shot back with the admin rather than
anywhere else.
"""

import json

import pytest

from backend import ai_shot_review
from backend import shot_escalation
from backend import shot_vision
from backend import vision_client
from backend.admin_interface import AdminInterface
from backend.identity.config import default_scheme
from backend.model import User
from backend.user_interface import UserInterface
from backend.vision_client import FakeVisionClient
from backend.vision_client import VisionError
from backend.vision_client import get_escalation_client

SCHEME = default_scheme()

# Four candidates, each in a different outfit.
CANDIDATE_SLOTS = list(SCHEME.usable_slots())[:4]

# A sentence unique to the cheap pass's reading, so a test can prove none of it
# reached the stronger model.
WEAK_REASONING = "the cheap pass thought it saw a passer-by in plain clothes"


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


@pytest.fixture
def candidates(db_session, team_factory, user_factory, test_image_string):
    """Four other players in the game, each with a slot and a reference photo."""
    team_id = team_factory()
    user_ids = []
    for slot in CANDIDATE_SLOTS:
        user_id = user_factory()
        with UserInterface(user_id) as ui:
            ui.join_team(team_id)
        db_session.query(User).filter_by(id=user_id).update({"identity_slot": slot})
        db_session.commit()
        AdminInterface().set_reference_photo(user_id, test_image_string)
        user_ids.append(user_id)
    return user_ids


def weak_review(hidden=("armbands",)):
    """The stored reading that sends a shot up the ladder: too little read."""
    appearance = SCHEME.appearance_of_slot(CANDIDATE_SLOTS[0])
    raw = {
        "shot_hit_a_person": True,
        "reasoning": WEAK_REASONING,
        "confidence": 0.5,
        "channels": {
            name: {
                "visible": name not in hidden,
                "colour": "unknown" if name in hidden else colour,
                "confidence": 0.2 if name in hidden else 0.9,
            }
            for name, colour in appearance.items()
        },
    }
    return shot_vision.classify(shot_vision.parse_result(raw), SCHEME).to_dict()


def store_weak_review(shot_id, review=None):
    AdminInterface().store_shot_ai_review(
        shot_id, ai_shot_review.STATE_DONE, review or weak_review()
    )


def verdict_reply(verdict, confidence=0.9, candidate=None, requested=None):
    reply = {
        "verdict": verdict,
        "candidate": candidate,
        "confidence": confidence,
        "reasoning": "the reference photo settles it",
    }
    if requested is not None:
        reply["request_reference_photos"] = requested
    return reply


def name_of(user_id):
    return AdminInterface().get_user_model(user_id).name


def stored_escalation(shot_id):
    return AdminInterface().get_shot_ai_review(shot_id)


# -- what the stronger model is shown ---------------------------------------


@pytest.mark.asyncio
async def test_the_call_carries_the_frame_the_zoom_and_the_top_reference_photos(
    db_session, shot_from_user_in_team, candidates
):
    store_weak_review(shot_from_user_in_team)
    client = FakeVisionClient(reply=verdict_reply("unsure", confidence=0.3))

    await shot_escalation.escalate_shot(shot_from_user_in_team, client)

    turns = client.calls[0]["turns"]
    # The full frame, the zoom, then one turn per up-front reference photo.
    assert len(turns) == 2 + shot_escalation.UPFRONT_REFERENCE_PHOTOS
    assert all(turn["image_data_url"] for turn in turns)
    assert shot_escalation.ZOOM_TURN in turns[1]["text"]
    for turn, user_id in zip(turns[2:], candidates[:3]):
        assert "Reference photo of candidate" in turn["text"]
        assert name_of(user_id) in turn["text"]


@pytest.mark.asyncio
async def test_the_prompt_lists_every_candidate_with_a_prior_and_an_outfit(
    db_session, shot_from_user_in_team, candidates
):
    store_weak_review(shot_from_user_in_team)
    client = FakeVisionClient(reply=verdict_reply("unsure", confidence=0.3))

    await shot_escalation.escalate_shot(shot_from_user_in_team, client)

    prompt = client.calls[0]["turns"][0]["text"]
    for user_id in candidates:
        assert name_of(user_id) in prompt
    assert "% likely" in prompt
    # Each candidate's actual outfit, channel by channel
    appearance = SCHEME.appearance_of_slot(CANDIDATE_SLOTS[0])
    assert f"tshirt {appearance['tshirt']}" in prompt
    # The three attached photos are announced as such, the fourth as askable
    assert prompt.count("Reference photo attached below.") == 3
    assert "Reference photo available on request." in prompt
    # The listed armband colour is only useful to somebody who knows where to
    # look for it, and that it is not always the upper arm.
    assert shot_vision.ARMBANDS_PLACEMENT in prompt
    # The reference photos share backdrops by accident of where they were
    # taken, so the prompt says the backdrop means nothing either way.
    assert shot_escalation.REFERENCE_BACKGROUND_CLAUSE in prompt


@pytest.mark.asyncio
async def test_a_knocked_out_candidate_is_listed_and_flagged_as_such(
    db_session, shot_from_user_in_team, candidates
):
    # The dead stay on the list -- they are still in the photograph -- but the
    # model is told, so it is not looking for somebody standing up.
    with UserInterface(candidates[0]) as ui:
        ui.hit(1)
    store_weak_review(shot_from_user_in_team)
    client = FakeVisionClient(reply=verdict_reply("unsure", confidence=0.3))

    await shot_escalation.escalate_shot(shot_from_user_in_team, client)

    prompt = client.calls[0]["turns"][0]["text"]
    assert name_of(candidates[0]) in prompt
    assert prompt.count(shot_escalation.KNOCKED_OUT_CLAUSE) == 1

    listed = {
        candidate["user_id"]: candidate["alive"]
        for candidate in stored_escalation(shot_from_user_in_team)["escalation"][
            "candidates"
        ]
    }
    assert listed[str(candidates[0])] is False
    assert all(
        alive for user_id, alive in listed.items() if user_id != str(candidates[0])
    )


@pytest.mark.asyncio
async def test_the_weak_models_conclusions_never_reach_the_stronger_one(
    db_session, shot_from_user_in_team, candidates
):
    # It draws its own conclusions from the pixels; the ranking is the only
    # thing it inherits. A second opinion that has read the first is not one.
    store_weak_review(shot_from_user_in_team)
    client = FakeVisionClient(reply=verdict_reply("unsure", confidence=0.3))

    await shot_escalation.escalate_shot(shot_from_user_in_team, client)

    sent = json.dumps(client.calls)
    assert WEAK_REASONING not in sent
    assert shot_vision.HIT_PLAYER not in sent
    assert "outcome" not in sent


@pytest.mark.asyncio
async def test_an_empty_candidate_list_rules_out_the_player_verdict(
    db_session, shot_from_user_in_team
):
    # Nobody placed and alive: there is no list to pick from, and the prompt
    # has to say so rather than offering a verdict that cannot be given.
    store_weak_review(shot_from_user_in_team)
    client = FakeVisionClient(reply=verdict_reply("miss"))

    await shot_escalation.escalate_shot(shot_from_user_in_team, client)

    prompt = client.calls[0]["turns"][0]["text"]
    assert 'so "player" is not a valid verdict here' in prompt
    assert len(client.calls[0]["turns"]) == 2  # no reference photos to attach


# -- asking for another reference photo -------------------------------------


@pytest.mark.asyncio
async def test_a_requested_reference_photo_is_supplied_in_a_follow_up_turn(
    db_session, shot_from_user_in_team, candidates
):
    store_weak_review(shot_from_user_in_team)
    client = FakeVisionClient(
        reply=[
            verdict_reply("unsure", confidence=0.2, requested=[4]),
            verdict_reply("player", confidence=0.9, candidate=4),
        ]
    )

    await shot_escalation.escalate_shot(shot_from_user_in_team, client)

    assert len(client.calls) == 2
    # The second call replays the first exchange, then the model's own answer,
    # then the photos it asked for.
    already_sent = len(client.calls[0]["turns"]) + 1
    follow_up = client.calls[1]["turns"][already_sent:]
    assert name_of(candidates[3]) in follow_up[0]["text"]
    assert follow_up[0]["image_data_url"]
    assert follow_up[-1]["text"] == shot_escalation.NO_FURTHER_PHOTOS

    stored = stored_escalation(shot_from_user_in_team)
    assert stored["escalation_state"] == shot_escalation.STATE_DONE
    assert stored["escalation"]["verdict"] == "player"
    assert stored["escalation"]["target_user_id"] == str(candidates[3])
    assert stored["escalation"]["requested_reference_photos"] == [4]


@pytest.mark.asyncio
async def test_a_second_round_of_requests_is_ignored(
    db_session, shot_from_user_in_team, candidates
):
    store_weak_review(shot_from_user_in_team)
    client = FakeVisionClient(
        reply=[
            verdict_reply("unsure", confidence=0.2, requested=[4]),
            verdict_reply("unsure", confidence=0.2, requested=[2]),
        ]
    )

    await shot_escalation.escalate_shot(shot_from_user_in_team, client)

    assert len(client.calls) == 2
    assert (
        stored_escalation(shot_from_user_in_team)["escalation"]["verdict"] == "unsure"
    )


@pytest.mark.asyncio
async def test_a_request_for_a_photo_that_does_not_exist_is_pressed_once(
    db_session, shot_from_user_in_team, candidates
):
    # It asked for nothing we can supply and decided nothing: pressing once for
    # the verdict is the difference between an answer and an errored escalation.
    store_weak_review(shot_from_user_in_team)
    client = FakeVisionClient(
        reply=[
            {"request_reference_photos": [9]},
            verdict_reply("miss", confidence=0.9),
        ]
    )

    await shot_escalation.escalate_shot(shot_from_user_in_team, client)

    assert len(client.calls) == 2
    assert client.calls[1]["turns"][-1]["text"] == shot_escalation.NO_FURTHER_PHOTOS
    assert stored_escalation(shot_from_user_in_team)["escalation"]["verdict"] == "miss"


# -- parsing the reply -------------------------------------------------------


def test_parse_accepts_each_verdict():
    for verdict in shot_escalation.VERDICTS:
        candidate = 1 if verdict == shot_escalation.VERDICT_PLAYER else None
        parsed = shot_escalation.parse_escalation_reply(
            verdict_reply(verdict, candidate=candidate), [1, 2]
        )
        assert parsed["verdict"] == verdict


def test_parse_rejects_a_reply_to_some_other_question():
    with pytest.raises(shot_escalation.EscalationError):
        shot_escalation.parse_escalation_reply({"verdict": "maybe"}, [1])
    with pytest.raises(shot_escalation.EscalationError):
        shot_escalation.parse_escalation_reply("a sentence", [1])


def test_a_player_verdict_naming_nobody_on_the_list_degrades_to_unsure():
    # A model that answers the right question badly has told us it could not
    # decide, and there is a rung for that.
    parsed = shot_escalation.parse_escalation_reply(
        verdict_reply("player", candidate=9), [1, 2]
    )

    assert parsed["verdict"] == shot_escalation.VERDICT_UNSURE
    assert parsed["candidate"] is None
    assert "not on the candidate list" in parsed["reasoning"]


def test_a_player_verdict_naming_true_is_not_read_as_candidate_one():
    parsed = shot_escalation.parse_escalation_reply(
        verdict_reply("player", candidate=True), [1, 2]
    )

    assert parsed["verdict"] == shot_escalation.VERDICT_UNSURE


def test_a_missing_confidence_parses_as_zero():
    parsed = shot_escalation.parse_escalation_reply({"verdict": "miss"}, [1])

    assert parsed["confidence"] == 0.0


def test_requested_numbers_drops_anything_not_on_the_list():
    raw = {"request_reference_photos": [2, 2, 9, "three", None]}

    assert shot_escalation.requested_numbers(raw, [1, 2, 3]) == [2]
    assert shot_escalation.requested_numbers({}, [1, 2, 3]) == []


# -- Python owns the thresholds ----------------------------------------------


def payload(verdict, confidence, target_user_id=None):
    return {
        "verdict": verdict,
        "confidence": confidence,
        "target_user_id": target_user_id,
    }


def test_a_player_verdict_needs_more_than_the_generic_threshold(user_in_team):
    at = shot_escalation.ESCALATION_HIT_THRESHOLD

    assert shot_escalation.decide_from_escalation(
        payload("player", at, str(user_in_team))
    ) == (shot_escalation.ACTION_HIT, user_in_team)
    assert (
        shot_escalation.decide_from_escalation(
            payload("player", at - 0.01, str(user_in_team))
        )
        is None
    )


def test_a_player_verdict_without_a_usable_target_decides_nothing():
    assert shot_escalation.decide_from_escalation(payload("player", 0.99)) is None
    assert (
        shot_escalation.decide_from_escalation(payload("player", 0.99, "not-a-uuid"))
        is None
    )


def test_miss_and_bystander_clear_the_same_bar_as_the_weak_model():
    at = shot_escalation.ESCALATION_OUTCOME_THRESHOLD

    assert shot_escalation.decide_from_escalation(payload("miss", at)) == (
        shot_escalation.ACTION_MISS,
        None,
    )
    assert shot_escalation.decide_from_escalation(payload("bystander", at)) == (
        shot_escalation.ACTION_BYSTANDER,
        None,
    )
    assert shot_escalation.decide_from_escalation(payload("miss", at - 0.01)) is None


def test_unsure_and_nonsense_decide_nothing():
    assert shot_escalation.decide_from_escalation(payload("unsure", 1.0)) is None
    assert shot_escalation.decide_from_escalation(payload("shrug", 1.0)) is None
    assert shot_escalation.decide_from_escalation("not a payload") is None


# -- never raising, never affecting the shot ---------------------------------


@pytest.mark.asyncio
async def test_a_failing_client_is_recorded_as_an_error(
    db_session, shot_from_user_in_team, candidates
):
    store_weak_review(shot_from_user_in_team)

    await shot_escalation.escalate_shot(
        shot_from_user_in_team,
        FakeVisionClient(error=VisionError("the model fell over")),
    )

    stored = stored_escalation(shot_from_user_in_team)
    assert stored["escalation_state"] == shot_escalation.STATE_ERROR
    assert "fell over" in stored["escalation"]["error"]


@pytest.mark.asyncio
async def test_a_garbled_reply_is_recorded_as_an_error(
    db_session, shot_from_user_in_team, candidates
):
    store_weak_review(shot_from_user_in_team)

    await shot_escalation.escalate_shot(
        shot_from_user_in_team, FakeVisionClient(reply={"nonsense": True})
    )

    assert (
        stored_escalation(shot_from_user_in_team)["escalation_state"]
        == shot_escalation.STATE_ERROR
    )


@pytest.mark.asyncio
async def test_escalating_a_shot_with_no_stored_review_errors_rather_than_raising(
    db_session, shot_from_user_in_team
):
    await shot_escalation.escalate_shot(
        shot_from_user_in_team, FakeVisionClient(reply=verdict_reply("miss"))
    )

    stored = stored_escalation(shot_from_user_in_team)
    assert stored["escalation_state"] == shot_escalation.STATE_ERROR
    assert "no stored review" in stored["escalation"]["error"]


@pytest.mark.asyncio
async def test_a_failing_escalation_leaves_the_shot_alone(
    db_session, shot_from_user_in_team, candidates
):
    store_weak_review(shot_from_user_in_team)

    await shot_escalation.escalate_shot(
        shot_from_user_in_team, FakeVisionClient(error=VisionError("nope"))
    )

    shot = AdminInterface().get_shot_model(shot_from_user_in_team)
    assert shot.checked is False
    assert shot.target_user_id is None


@pytest.mark.asyncio
async def test_an_escalation_is_marked_pending_while_it_runs(
    db_session, shot_from_user_in_team, candidates
):
    # Escalations are slow, so the queue is told about one as it starts rather
    # than only when it finishes.
    store_weak_review(shot_from_user_in_team)
    states = []

    def reply(turns, schema):
        states.append(stored_escalation(shot_from_user_in_team)["escalation_state"])
        return verdict_reply("unsure", confidence=0.2)

    await shot_escalation.escalate_shot(
        shot_from_user_in_team, FakeVisionClient(reply=reply)
    )

    assert states == [shot_escalation.STATE_PENDING]


def test_escalation_defaults_to_the_recognition_model(monkeypatch, db_session):
    # Unset, OPENROUTER_ESCALATION_MODEL mirrors whatever recognition uses --
    # escalation is enabled by default wherever recognition is, rather than
    # needing a second model configured on top.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_ESCALATION_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    client = get_escalation_client()

    assert client is not None
    assert client.model == vision_client.DEFAULT_MODEL


def test_escalation_thinks_hard_by_default(monkeypatch, db_session):
    # The cheap pass sends no reasoning override; this rung asks for "high"
    # unless told otherwise, and the env var still wins when it is set.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_ESCALATION_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("OPENROUTER_REASONING_EFFORT", raising=False)

    assert get_escalation_client().reasoning_effort == "high"

    monkeypatch.setenv("OPENROUTER_ESCALATION_REASONING_EFFORT", "low")
    assert get_escalation_client().reasoning_effort == "low"
    assert get_escalation_client(reasoning_effort="medium").reasoning_effort == "medium"


def test_escalation_mirrors_an_explicit_recognition_model(monkeypatch, db_session):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/recognition-model")
    monkeypatch.delenv("OPENROUTER_ESCALATION_MODEL", raising=False)

    client = get_escalation_client()

    assert client.model == "test/recognition-model"


def test_without_an_api_key_nothing_is_queued(
    monkeypatch, db_session, shot_from_user_in_team
):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_ESCALATION_MODEL", raising=False)

    assert shot_escalation.enqueue_escalation(shot_from_user_in_team) is None
    assert stored_escalation(shot_from_user_in_team)["escalation_state"] is None


# -- the admin's "Run escalated review" button -------------------------------


@pytest.fixture
def escalation_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_ESCALATION_MODEL", "test/strong-model")


def test_the_manual_escalation_needs_an_api_key(
    monkeypatch, db_session, admin_api_client, shot_from_user_in_team
):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_ESCALATION_MODEL", raising=False)
    store_weak_review(shot_from_user_in_team)

    response = admin_api_client.post(
        f"/api/admin_escalate_shot?shot_id={shot_from_user_in_team}"
    )

    assert response.status_code == 400
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


def test_the_manual_escalation_needs_a_review_to_escalate_from(
    escalation_model, db_session, admin_api_client, shot_from_user_in_team
):
    # The candidate ranking is built from the cheap pass's reading, so without
    # one there is nothing to hand the stronger model.
    response = admin_api_client.post(
        f"/api/admin_escalate_shot?shot_id={shot_from_user_in_team}"
    )

    assert response.status_code == 400
    assert "run the AI review first" in response.json()["detail"]


def test_the_manual_escalation_runs_whatever_the_toggles_say(
    mocker, escalation_model, db_session, admin_api_client, shot_from_user_in_team
):
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    game_id = AdminInterface().get_shot_game_id(shot_from_user_in_team)
    AdminInterface().set_ai_escalation_enabled(game_id, False)
    store_weak_review(shot_from_user_in_team)

    response = admin_api_client.post(
        f"/api/admin_escalate_shot?shot_id={shot_from_user_in_team}"
    )

    assert response.is_success
    assert enqueue.call_args.args[0] == shot_from_user_in_team


# -- the columns and the shooter's shot history ------------------------------


def test_re_running_the_weak_review_clears_the_escalation(
    db_session, shot_from_user_in_team
):
    # A new reading invalidates the old escalation -- and this is how an admin
    # unsticks an escalation that errored.
    AdminInterface().store_shot_escalation(
        shot_from_user_in_team, shot_escalation.STATE_ERROR, "timed out"
    )

    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_PENDING
    )

    stored = stored_escalation(shot_from_user_in_team)
    assert stored["escalation_state"] is None
    assert stored["escalation"] is None


def test_storing_a_finished_review_leaves_the_escalation_alone(
    db_session, shot_from_user_in_team
):
    AdminInterface().store_shot_escalation(
        shot_from_user_in_team, shot_escalation.STATE_DONE, {"verdict": "unsure"}
    )

    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_DONE, {"outcome": "miss"}
    )

    assert (
        stored_escalation(shot_from_user_in_team)["escalation_state"]
        == shot_escalation.STATE_DONE
    )


def suggestion_for(user_id):
    return UserInterface(user_id).get_own_shots()[0]["ai_suggestion"]


def test_the_shot_history_prefers_the_escalated_verdict(
    db_session, shot_from_user_in_team, user_in_team
):
    store_weak_review(shot_from_user_in_team, {"outcome": "miss", "is_hit": False})
    AdminInterface().store_shot_escalation(
        shot_from_user_in_team,
        shot_escalation.STATE_DONE,
        {"verdict": "player", "confidence": 0.9},
    )

    assert suggestion_for(user_in_team) == "hit"


def test_an_unsure_escalation_falls_back_to_the_weak_review(
    db_session, shot_from_user_in_team, user_in_team
):
    # "unsure" means an admin still has to look, so there is nothing to tell
    # the shooter that the cheap review did not already say.
    store_weak_review(shot_from_user_in_team, {"outcome": "miss", "is_hit": False})
    AdminInterface().store_shot_escalation(
        shot_from_user_in_team,
        shot_escalation.STATE_DONE,
        {"verdict": "unsure", "confidence": 0.9},
    )

    assert suggestion_for(user_in_team) == "miss"


def test_an_errored_escalation_falls_back_to_the_weak_review(
    db_session, shot_from_user_in_team, user_in_team
):
    store_weak_review(shot_from_user_in_team, {"outcome": "miss", "is_hit": False})
    AdminInterface().store_shot_escalation(
        shot_from_user_in_team, shot_escalation.STATE_ERROR, "timed out"
    )

    assert suggestion_for(user_in_team) == "miss"


# -- the replay workbench's escalation (roadmap R13 #9) ----------------------


def test_the_escalation_replay_needs_admin_auth(api_client, shot_from_user_in_team):
    response = api_client.post(
        "/api/admin_replay_shot_escalation",
        json={"shot_id": str(shot_from_user_in_team)},
    )

    assert response.status_code == 403


def test_the_escalation_replay_without_a_key_is_a_clear_error(
    monkeypatch, db_session, admin_api_client, shot_from_user_in_team
):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    store_weak_review(shot_from_user_in_team)

    response = admin_api_client.post(
        "/api/admin_replay_shot_escalation",
        json={"shot_id": str(shot_from_user_in_team)},
    )

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


def test_the_escalation_replay_needs_a_review_to_escalate_from(
    escalation_model, db_session, admin_api_client, shot_from_user_in_team
):
    # The same precondition as the queue's own button: the candidate ranking
    # is built from the cheap pass's reading.
    response = admin_api_client.post(
        "/api/admin_replay_shot_escalation",
        json={"shot_id": str(shot_from_user_in_team)},
    )

    assert response.status_code == 400
    assert "run the AI review first" in response.json()["detail"]


def test_the_escalation_replay_returns_the_verdict_and_the_transcript(
    mocker,
    escalation_model,
    db_session,
    admin_api_client,
    shot_from_user_in_team,
    candidates,
):
    client = FakeVisionClient(
        reply=verdict_reply("player", confidence=0.9, candidate=1),
        reasoning="the hat settles it",
    )
    mocker.patch("backend.main.get_escalation_client", return_value=client)
    store_weak_review(shot_from_user_in_team)

    response = admin_api_client.post(
        "/api/admin_replay_shot_escalation",
        json={"shot_id": str(shot_from_user_in_team)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["verdict"] == "player"
    assert payload["target_name"] == name_of(candidates[0])
    # The whole point of the endpoint: the exchange, turn by turn, the way
    # TranscriptView already renders a review's.
    assert [turn["role"] for turn in payload["transcript"]] == [
        "user",
        "user",
        "user",
        "user",
        "user",
        "assistant",
    ]
    assert payload["transcript"][-1]["reasoning"] == "the hat settles it"


def test_the_escalation_replay_stores_nothing_and_settles_nothing(
    mocker,
    escalation_model,
    db_session,
    admin_api_client,
    shot_from_user_in_team,
    candidates,
):
    # A confident "player" verdict through the real path would take a life;
    # through the workbench it must leave the shot exactly as it found it.
    mocker.patch(
        "backend.main.get_escalation_client",
        return_value=FakeVisionClient(
            reply=verdict_reply("player", confidence=0.99, candidate=1)
        ),
    )
    drain = mocker.patch("backend.shot_auto_actions.process_queue_head")
    store_weak_review(shot_from_user_in_team)

    assert admin_api_client.post(
        "/api/admin_replay_shot_escalation",
        json={"shot_id": str(shot_from_user_in_team)},
    ).is_success

    stored = stored_escalation(shot_from_user_in_team)
    assert stored["escalation_state"] is None
    assert stored["escalation"] is None
    drain.assert_not_called()
    assert AdminInterface().get_shot_model(shot_from_user_in_team).checked is False


def test_the_escalation_replay_passes_the_reasoning_effort_override_through(
    mocker, escalation_model, db_session, admin_api_client, shot_from_user_in_team
):
    get_client = mocker.patch(
        "backend.main.get_escalation_client",
        return_value=FakeVisionClient(reply=verdict_reply("unsure", confidence=0.2)),
    )
    store_weak_review(shot_from_user_in_team)

    response = admin_api_client.post(
        "/api/admin_replay_shot_escalation",
        json={"shot_id": str(shot_from_user_in_team), "reasoning_effort": "high"},
    )

    assert response.is_success
    get_client.assert_called_once_with(reasoning_effort="high")
