import json
from uuid import UUID
from uuid import uuid4 as get_uuid

import pytest
from fastapi.exceptions import HTTPException

from backend.admin_interface import AdminInterface
from backend.model import Shot
from backend.model import User
from backend.ticker_message_dispatcher import TickerMessageType
from backend.user_interface import UserInterface


def test_submit_shot(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    ui.submit_shot(test_image_string)


def test_a_real_shot_is_stamped_by_the_database(
    db_session, user_in_team, test_image_string
):
    """`submit_shot` takes an optional time for replaying a simulated game
    (backend/test_world/replay.py). Passing it through to the constructor as
    None would write a null over the column's server default, so a live shot
    would land with no time at all - and the queue is ordered by that column."""
    import datetime

    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    shot_id = ui.submit_shot(test_image_string)

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    stamped = db_session.get(Shot, shot_id).time_created
    assert stamped is not None
    assert abs(stamped - now) < datetime.timedelta(minutes=5)


def test_submit_shot_records_shot_timeout(db_session, user_in_team, test_image_string):
    """shot_timeout is captured alongside shot_damage for the same reason:
    damage alone can't name a weapon (react-ui/src/weapons.js's WEAPONS keys
    on both, since e.g. Pewster and Eat-a-bullet share damage 1), so both
    have to be frozen at the moment of firing."""
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    ui.set_weapon_data(damage=2, fire_delay=6)

    shot_id = ui.submit_shot(test_image_string)

    assert db_session.get(Shot, shot_id).shot_timeout == 6

    # Picking up a later upgrade must not retroactively change what this
    # shot recorded - it is a snapshot of the moment it was fired.
    ui.set_weapon_data(damage=3, fire_delay=1)
    assert db_session.get(Shot, shot_id).shot_timeout == 6


def test_submit_shot_no_ammo(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    with pytest.raises(HTTPException):
        ui.submit_shot(test_image_string)


def test_trigger_update_event_on_shot(mocker, user_in_team, test_image_string):
    """A new shot announces itself, whoever put it there.

    Both events come from ``submit_shot`` rather than from the
    ``/api/submit_shot`` route, because the route is not the only way a shot
    gets into a game: the demo drip and ``npm run demoshots`` call the
    interface directly, and a spectator screen watching a shot land is exactly
    what the "shots" event is for.
    """
    mocked = mocker.patch("backend.asyncio_triggers.trigger_update_event")
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    mocked.reset_mock()
    game_id = UserInterface(user_in_team).get_game_id()
    UserInterface(user_in_team).submit_shot(test_image_string)
    events = [c.args for c in mocked.call_args_list]
    assert ("user", user_in_team) in events
    assert ("shots", game_id) in events


def test_a_replayed_shot_announces_itself_too(mocker, user_in_team, test_image_string):
    """The demo game's shots are fired through the interface, not the route.

    Pressing "Fire demo game" used to leave the spectator screen watching a
    perfectly healthy SSE connection that never said anything again: the drip
    fires ten shots over five minutes and none of them triggered an update, so
    the feed stayed on whatever it had when the button was pressed.
    """
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    game_id = ui.get_game_id()

    mocked = mocker.patch("backend.asyncio_triggers.trigger_update_event")
    with UserInterface(user_in_team) as replayer:
        replayer.submit_shot(test_image_string, shot_id=get_uuid())

    assert ("shots", game_id) in [c.args for c in mocked.call_args_list]


# -- the user-facing shot history -------------------------------------------


def submit_a_shot(user_id, test_image_string, time_created=None):
    ui = UserInterface(user_id)
    ui.award_ammo(1)
    ui.set_weapon_data(1, 6)
    return ui.submit_shot(test_image_string, time_created=time_created)


def test_hit_recorded_in_shot_history(two_users_in_different_teams, test_image_string):
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)

    AdminInterface().hit_user(shot_id, target)

    (shot,) = UserInterface(shooter).get_own_shots()
    assert shot["id"] == shot_id
    assert shot["checked"] is True
    assert shot["result"] == "hit"
    assert shot["target_name"] == UserInterface(target).get_user_model().name


def test_miss_recorded_in_shot_history(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    AdminInterface().mark_shot_missed(shot_id)

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["checked"] is True
    assert shot["result"] == "miss"
    assert shot["target_name"] is None


def test_bystander_recorded_in_shot_history(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    AdminInterface().mark_shot_bystander(shot_id)

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["checked"] is True
    assert shot["result"] == "bystander"
    assert shot["target_name"] is None
    # A bystander costs the ammo, exactly like a miss
    assert UserInterface(user_in_team).get_user_model().num_bullets == 0


def test_bystander_tells_the_shooter(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    AdminInterface().mark_shot_bystander(shot_id)

    messages = UserInterface(user_in_team).get_messages(10, private=True)
    assert any("bystander" in message.lower() for _, message, _ in messages)


def test_refund_recorded_in_shot_history(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    AdminInterface().refund_shot(shot_id)

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["result"] == "refunded"
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_knockout_invalidates_the_targets_shot_fired_after_the_kill(
    two_users_in_different_teams, test_image_string
):
    """A shot the target fired *after* the photo that killed them was never a
    legitimate shot from a live player - it is invalidated when the knockout
    lands, whatever order the admin happens to check the queue in."""
    import datetime

    shooter, target = two_users_in_different_teams

    shooter_shot = submit_a_shot(
        shooter, test_image_string, time_created=datetime.datetime(2026, 1, 1, 12, 0, 0)
    )
    target_shot = submit_a_shot(
        target, test_image_string, time_created=datetime.datetime(2026, 1, 1, 12, 0, 5)
    )

    AdminInterface().hit_user(shooter_shot, target)

    (shot,) = UserInterface(target).get_own_shots()
    assert shot["id"] == target_shot
    assert shot["result"] == "invalidated"


def test_knockout_does_not_touch_the_targets_shot_fired_before_the_kill(
    two_users_in_different_teams, test_image_string
):
    """A shot the target fired *before* the photo that killed them was fired
    while they were still alive and playing fair - it is only sitting
    unchecked because the queue has not reached it yet, and the knockout that
    comes later must not sweep it up along with the illegitimate ones."""
    import datetime

    shooter, target = two_users_in_different_teams

    target_shot = submit_a_shot(
        target, test_image_string, time_created=datetime.datetime(2026, 1, 1, 12, 0, 0)
    )
    shooter_shot = submit_a_shot(
        shooter, test_image_string, time_created=datetime.datetime(2026, 1, 1, 12, 0, 5)
    )

    AdminInterface().hit_user(shooter_shot, target)

    (shot,) = UserInterface(target).get_own_shots()
    assert shot["id"] == target_shot
    assert shot["checked"] is False
    assert shot["result"] is None


def test_hit_does_not_tell_shooter_they_missed(
    two_users_in_different_teams, test_image_string
):
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)

    AdminInterface().hit_user(shot_id, target)

    messages = UserInterface(shooter).get_messages(10, private=True)
    assert not any("missed" in message.lower() for _, message, _ in messages)


# -- hitting somebody who is already knocked out -----------------------------


def ticker_types(mocked):
    return [call.args[0] for call in mocked.call_args_list]


def test_the_death_blow_announces_the_knockout_once(
    mocker, two_users_in_different_teams, test_image_string
):
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)
    mocked = mocker.patch("backend.ticker_message_dispatcher.send_ticker_message")

    AdminInterface().hit_user(shot_id, target)

    assert ticker_types(mocked) == [
        TickerMessageType.HIT_AND_KNOCKOUT,
        TickerMessageType.USER_GOT_KNOCKED_OUT,
    ]


def test_the_knockout_announces_invalidated_shots_with_a_count(
    mocker, two_users_in_different_teams, test_image_string
):
    """The target has two shots of their own still queued when they die, both
    fired after the fatal photograph - both are invalidated, and the ticker
    says how many rather than sending one line per shot."""
    import datetime

    shooter, target = two_users_in_different_teams
    kill_shot = submit_a_shot(
        shooter, test_image_string, time_created=datetime.datetime(2026, 1, 1, 12, 0, 0)
    )
    submit_a_shot(
        target, test_image_string, time_created=datetime.datetime(2026, 1, 1, 12, 0, 5)
    )
    submit_a_shot(
        target, test_image_string, time_created=datetime.datetime(2026, 1, 1, 12, 0, 6)
    )
    mocked = mocker.patch("backend.ticker_message_dispatcher.send_ticker_message")

    AdminInterface().hit_user(kill_shot, target)

    assert ticker_types(mocked) == [
        TickerMessageType.HIT_AND_KNOCKOUT,
        TickerMessageType.USER_GOT_KNOCKED_OUT,
        TickerMessageType.SHOTS_INVALIDATED,
    ]
    invalidated_call = mocked.call_args_list[2]
    assert invalidated_call.args[1]["num"] == 2


def test_a_self_shot_kill_does_not_invalidate_itself(
    mocker, user_in_team, test_image_string
):
    """A player's only shot, fired at themselves, is its own fatal blow: it
    must come out of this as a hit, not as an invalidated shot that then gets
    silently patched back to "hit" - and it must not trigger a
    SHOTS_INVALIDATED ticker line about a shot that is, in the end, a hit."""
    shot_id = submit_a_shot(user_in_team, test_image_string)
    mocked = mocker.patch("backend.ticker_message_dispatcher.send_ticker_message")

    AdminInterface().hit_user(shot_id, user_in_team)

    assert TickerMessageType.SHOTS_INVALIDATED not in ticker_types(mocked)
    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["result"] == "hit"


def test_hitting_an_already_dead_player_is_a_plain_hit(
    mocker, two_users_in_different_teams, test_image_string
):
    """A shot queued behind the one that killed its target did hit them; it
    just changes nothing. Announcing a second knockout would credit the kill to
    whoever happened to be next in the queue."""
    shooter, target = two_users_in_different_teams
    death_blow = submit_a_shot(shooter, test_image_string)
    afterwards = submit_a_shot(shooter, test_image_string)
    AdminInterface().hit_user(death_blow, target)

    mocked = mocker.patch("backend.ticker_message_dispatcher.send_ticker_message")
    clearing = mocker.spy(UserInterface, "clear_unchecked_shots")

    AdminInterface().hit_user(afterwards, target)

    assert ticker_types(mocked) == [
        TickerMessageType.HIT_AND_DAMAGE,
        TickerMessageType.USER_GOT_HIT,
    ]
    clearing.assert_not_called()
    assert UserInterface(target).get_user_model().hit_points == 0
    results = {
        shot["id"]: shot["result"] for shot in UserInterface(shooter).get_own_shots()
    }
    assert results[afterwards] == "hit"


def test_adjudication_nudges_the_shooter(mocker, user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    mocked = mocker.patch("backend.admin_interface.trigger_update_event")
    AdminInterface().mark_shot_missed(shot_id)

    assert ("user", user_in_team) in [c.args for c in mocked.call_args_list]


def test_a_hit_nudges_the_target_too(
    mocker, two_users_in_different_teams, test_image_string
):
    """The person who just lost a hit point has a HUD to update and, now, a
    shot to appeal - they cannot be told only through the ticker."""
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)

    mocked = mocker.patch("backend.admin_interface.trigger_update_event")
    AdminInterface().hit_user(shot_id, target)

    events = [c.args for c in mocked.call_args_list]
    assert ("user", shooter) in events
    assert ("user", target) in events


def test_shot_history_only_shares_the_ai_bottom_line(
    user_in_team, shot_from_user_in_team
):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team,
        "done",
        {"is_hit": True, "outcome": "hit_player", "reasoning": "top secret"},
    )

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["ai_review_state"] == "done"
    assert shot["ai_suggestion"] == "hit"
    # No reasoning, no clothing readings, no image - just the summary fields.
    # shot_damage/shot_timeout are the exception worth calling out: not
    # sensitive and not bulky like the excluded fields, and needed so the
    # frontend can name the weapon (react-ui/src/weapons.js's WEAPONS,
    # shared with the admin queue) without a second round trip.
    assert set(shot.keys()) == {
        "id",
        "time_created",
        "checked",
        "result",
        "target_name",
        "ai_review_state",
        "ai_suggestion",
        "ai_target_name",
        "shot_damage",
        "shot_timeout",
        "appeal_state",
        "my_appeal_reason",
        "can_appeal",
    }


def test_shot_history_ai_suggestion_can_be_miss(user_in_team, shot_from_user_in_team):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", {"is_hit": False, "outcome": "miss"}
    )

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["ai_suggestion"] == "miss"


def test_shot_history_ai_suggestion_can_be_bystander(
    user_in_team, shot_from_user_in_team
):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", {"is_hit": False, "outcome": "hit_bystander"}
    )

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["ai_suggestion"] == "bystander"


def test_user_shots_endpoint_excludes_images(
    api_client, api_user_id, one_team, test_image_string
):
    UserInterface(api_user_id).join_team(one_team)
    shot_id = submit_a_shot(api_user_id, test_image_string)

    response = api_client.get("/api/user_shots")
    assert response.is_success

    (shot,) = response.json()
    assert shot["id"] == str(shot_id)
    assert "image_base64" not in shot


def test_user_shot_image_endpoint(api_client, api_user_id, one_team, test_image_string):
    UserInterface(api_user_id).join_team(one_team)
    shot_id = submit_a_shot(api_user_id, test_image_string)

    response = api_client.get(f"/api/user_shot_image?shot_id={shot_id}")
    assert response.is_success
    assert response.json()["image_base64"] == test_image_string


def test_user_cannot_fetch_someone_elses_shot_image(api_client, shot_from_user_in_team):
    # The api_client session is a different user from the one who fired, and
    # not the target either - a third party is told nothing, not even that the
    # id exists
    response = api_client.get(f"/api/user_shot_image?shot_id={shot_from_user_in_team}")
    assert response.status_code == 404


def test_the_target_can_fetch_the_shot_that_hit_them(
    api_client, api_user_id, team_factory, user_factory, test_image_string
):
    # They cannot appeal a photograph they were never shown, and it costs them
    # nothing: it is a photograph of them, and the ticker has named the shooter
    shooter = user_factory()
    UserInterface(shooter).join_team(team_factory())
    UserInterface(api_user_id).join_team(team_factory())
    shot_id = submit_a_shot(shooter, test_image_string)
    AdminInterface().hit_user(shot_id, api_user_id)

    response = api_client.get(f"/api/user_shot_image?shot_id={shot_id}")
    assert response.is_success
    assert response.json()["image_base64"] == test_image_string


# -- appeals (docs/roadmap.md R8) --------------------------------------------


@pytest.fixture
def resolved_hit(two_users_in_different_teams, test_image_string):
    """A shot the admin has already ruled a hit: shooter, target, shot id."""
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)
    AdminInterface().hit_user(shot_id, target)
    return shooter, target, shot_id


def only_shot(user_id):
    (shot,) = UserInterface(user_id).get_own_shots()
    return shot


def test_a_fresh_player_has_three_appeals(user_in_team):
    assert UserInterface(user_in_team).get_user_model().appeals_remaining == 3


def test_the_shooter_can_appeal_a_miss(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)
    AdminInterface().mark_shot_missed(shot_id)

    assert only_shot(user_in_team)["can_appeal"] is True

    UserInterface(user_in_team).appeal_shot(shot_id, "actually_hit")

    shot = only_shot(user_in_team)
    assert shot["appeal_state"] == "open"
    assert shot["my_appeal_reason"] == "actually_hit"
    # One appeal per shot per party
    assert shot["can_appeal"] is False
    assert UserInterface(user_in_team).get_user_model().appeals_remaining == 2


def test_the_target_sees_the_shot_that_hit_them(resolved_hit):
    shooter, target, shot_id = resolved_hit

    (received,) = UserInterface(target).get_shots_received()
    assert received["id"] == shot_id
    assert received["result"] == "hit"
    assert received["shooter_name"] == UserInterface(shooter).get_user_model().name
    assert received["appeal_state"] is None
    assert received["my_appeal_reason"] is None
    assert received["can_appeal"] is True


def test_the_target_can_appeal_being_hit(resolved_hit):
    shooter, target, shot_id = resolved_hit

    UserInterface(target).appeal_shot(shot_id, "wrong_target")

    (received,) = UserInterface(target).get_shots_received()
    assert received["appeal_state"] == "open"
    assert received["my_appeal_reason"] == "wrong_target"
    assert UserInterface(target).get_user_model().appeals_remaining == 2

    # The shooter sees the shot is contested, but not by them
    shot = only_shot(shooter)
    assert shot["appeal_state"] == "open"
    assert shot["my_appeal_reason"] is None
    assert shot["can_appeal"] is True


def test_both_parties_can_appeal_the_same_shot(resolved_hit):
    shooter, target, shot_id = resolved_hit

    UserInterface(target).appeal_shot(shot_id, "missed")
    UserInterface(shooter).appeal_shot(shot_id, "actually_hit")

    appeal = AdminInterface().get_shot_appeal(shot_id)
    assert appeal["target_appeal_reason"] == "missed"
    assert appeal["shooter_appeal_reason"] == "actually_hit"


def test_an_unadjudicated_shot_cannot_be_appealed(user_in_team, shot_from_user_in_team):
    assert only_shot(user_in_team)["can_appeal"] is False

    with pytest.raises(HTTPException) as excinfo:
        UserInterface(user_in_team).appeal_shot(shot_from_user_in_team, "actually_hit")

    assert excinfo.value.status_code == 400


def test_a_refunded_shot_cannot_be_appealed(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)
    AdminInterface().refund_shot(shot_id)

    assert only_shot(user_in_team)["can_appeal"] is False


def test_the_target_cannot_appeal_a_shot_that_was_not_a_hit(
    two_users_in_different_teams, test_image_string
):
    # Only reachable through a re-adjudication, but the rule is the rule: a
    # miss takes nothing off the target, so they have no case to make
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)
    AdminInterface().hit_user(shot_id, target)
    UserInterface(target).appeal_shot(shot_id, "missed")
    AdminInterface().mark_shot_missed(shot_id)

    with pytest.raises(HTTPException) as excinfo:
        UserInterface(target).appeal_shot(shot_id, "missed")

    assert excinfo.value.status_code == 404  # they are no longer the target


def test_running_out_of_appeals_greys_the_button_out(
    user_in_team, test_image_string, db_session
):
    shot_id = submit_a_shot(user_in_team, test_image_string)
    AdminInterface().mark_shot_missed(shot_id)
    db_session.query(User).filter_by(id=user_in_team).update({"appeals_remaining": 0})
    db_session.commit()

    assert only_shot(user_in_team)["can_appeal"] is False

    with pytest.raises(HTTPException) as excinfo:
        UserInterface(user_in_team).appeal_shot(shot_id, "actually_hit")

    assert excinfo.value.status_code == 400
    assert "no appeals left" in excinfo.value.detail


def test_an_unknown_reason_is_rejected(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)
    AdminInterface().mark_shot_missed(shot_id)

    with pytest.raises(HTTPException) as excinfo:
        UserInterface(user_in_team).appeal_shot(shot_id, "i just dont like it")

    assert excinfo.value.status_code == 400
    assert UserInterface(user_in_team).get_user_model().appeals_remaining == 3


def test_a_third_party_cannot_appeal_and_is_not_told_the_shot_exists(
    resolved_hit, user_factory, team_factory
):
    shooter, target, shot_id = resolved_hit
    bystander = user_factory()
    UserInterface(bystander).join_team(team_factory())

    with pytest.raises(HTTPException) as excinfo:
        UserInterface(bystander).appeal_shot(shot_id, "missed")

    assert excinfo.value.status_code == 404


def test_appealing_nudges_the_other_party_and_the_admin(mocker, resolved_hit):
    shooter, target, shot_id = resolved_hit
    game_id = UserInterface(shooter).get_game_id()

    mocked = mocker.patch("backend.asyncio_triggers.trigger_update_event")
    UserInterface(target).appeal_shot(shot_id, "missed")

    events = [c.args for c in mocked.call_args_list]
    assert ("user", target) in events  # fired by @db_scoped
    assert ("user", shooter) in events
    assert ("shots", game_id) in events


def test_a_contested_shot_never_re_enters_the_drain(
    db_session, resolved_hit, test_image_string
):
    """It stays checked, so the head-of-queue drain cannot see it - which is
    the whole reason contested shots get a list of their own."""
    from backend import shot_auto_actions

    shooter, target, shot_id = resolved_hit
    game_id = UserInterface(shooter).get_game_id()
    AdminInterface().set_ai_auto_actions_enabled(game_id, True)
    AdminInterface().set_ai_resolve_everything_enabled(game_id, True)

    UserInterface(target).appeal_shot(shot_id, "missed")

    assert AdminInterface().get_queue_head(game_id) is None
    shot_auto_actions.process_queue_head(game_id)

    db_session.expire_all()
    shot = db_session.get(Shot, shot_id)
    assert shot.checked is True
    assert shot.appeal_state == "open"
    assert shot.result == "hit"


# -- the appeal endpoints ----------------------------------------------------


def test_user_shots_received_endpoint(
    api_client, api_user_id, team_factory, user_factory, test_image_string
):
    shooter = user_factory()
    UserInterface(shooter).join_team(team_factory())
    UserInterface(api_user_id).join_team(team_factory())
    shot_id = submit_a_shot(shooter, test_image_string)
    AdminInterface().hit_user(shot_id, api_user_id)

    response = api_client.get("/api/user_shots_received")
    assert response.is_success

    (received,) = response.json()
    assert received["id"] == str(shot_id)
    assert received["can_appeal"] is True
    assert "image_base64" not in received


def test_appeal_shot_endpoint(api_client, api_user_id, one_team, test_image_string):
    UserInterface(api_user_id).join_team(one_team)
    shot_id = submit_a_shot(api_user_id, test_image_string)
    AdminInterface().mark_shot_missed(shot_id)

    response = api_client.post(
        "/api/appeal_shot", params={"shot_id": str(shot_id), "reason": "actually_hit"}
    )
    assert response.is_success

    assert UserInterface(api_user_id).get_user_model().appeals_remaining == 2
    assert AdminInterface().get_contested_shot_ids() == [shot_id]


def test_appeal_shot_endpoint_refuses_a_stranger(api_client, shot_from_user_in_team):
    AdminInterface().mark_shot_missed(shot_from_user_in_team)

    response = api_client.post(
        "/api/appeal_shot",
        params={"shot_id": str(shot_from_user_in_team), "reason": "actually_hit"},
    )
    assert response.status_code == 404


# -- telemetry captured with a shot (docs/roadmap.md R5) ---------------------
#
# Nothing reads either of these fields yet, on purpose: they are recorded now
# because they cannot be recovered afterwards.


def test_shot_records_the_heading_it_was_fired_on(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    shot_id = ui.submit_shot(test_image_string, heading=137.5)

    assert AdminInterface().get_shot_model(shot_id).heading == 137.5


def test_shot_without_a_heading_is_still_a_shot(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    shot_id = ui.submit_shot(test_image_string)

    assert AdminInterface().get_shot_model(shot_id).heading is None


def test_submit_shot_endpoint_passes_the_heading_through(
    api_client, api_user_id, one_team, test_image_string
):
    UserInterface(api_user_id).join_team(one_team)
    UserInterface(api_user_id).award_ammo(1)

    response = api_client.post(
        "/api/submit_shot", json={"photo": test_image_string, "heading": 42.0}
    )
    assert response.is_success

    shot_id = UUID(response.json())
    assert AdminInterface().get_shot_model(shot_id).heading == 42.0


def test_submit_shot_endpoint_tolerates_a_missing_heading(
    api_client, api_user_id, one_team, test_image_string
):
    UserInterface(api_user_id).join_team(one_team)
    UserInterface(api_user_id).award_ammo(1)

    response = api_client.post("/api/submit_shot", json={"photo": test_image_string})
    assert response.is_success

    shot_id = UUID(response.json())
    assert AdminInterface().get_shot_model(shot_id).heading is None


def test_location_accuracy_is_stored_and_reported(user_in_team):
    ui = UserInterface(user_in_team)
    ui.set_location(51.5, -0.1, accuracy=12.5)

    assert ui.get_user_model().location_accuracy == 12.5

    (location,) = [
        entry
        for entry in AdminInterface().get_locations()
        if entry["user_id"] == user_in_team
    ]
    assert location["accuracy"] == 12.5


def test_location_accuracy_is_optional(user_in_team):
    ui = UserInterface(user_in_team)
    ui.set_location(51.5, -0.1)

    (location,) = [
        entry
        for entry in AdminInterface().get_locations()
        if entry["user_id"] == user_in_team
    ]
    assert location["accuracy"] is None


def test_set_location_endpoint_passes_the_accuracy_through(
    api_client, api_user_id, one_team
):
    UserInterface(api_user_id).join_team(one_team)

    response = api_client.post(
        "/api/set_location",
        params={"latitude": 51.5, "longitude": -0.1, "accuracy": 8.25},
    )
    assert response.is_success

    assert UserInterface(api_user_id).get_user_model().location_accuracy == 8.25


def test_shot_location_context_carries_the_shooters_fix(
    user_in_team, test_image_string
):
    """The context serialised into every shot is what a future model reads
    back, so the accuracy has to survive the round trip into it."""
    ui = UserInterface(user_in_team)
    ui.set_location(51.5, -0.1, accuracy=9.0)
    ui.award_ammo(1)
    shot_id = ui.submit_shot(test_image_string, heading=90.0)

    shot = AdminInterface().get_shot_model(shot_id)
    context = json.loads(shot.location_context)

    (shooter,) = [entry for entry in context if entry["user_id"] == str(user_in_team)]
    assert shooter["latitude"] == 51.5
    assert shooter["longitude"] == -0.1
    assert shooter["accuracy"] == 9.0
