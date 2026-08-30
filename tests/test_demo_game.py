"""The admin's "Fire demo game" button.

The expensive part of every test here is provisioning: thirty players picking
outfits through the real allocator takes a few seconds, and each test gets a
fresh database. So the drip's behaviour -- wiping, firing, cancelling,
restarting from the beginning, and being idempotent while it runs -- is
exercised once each, in one test apiece, rather than paid for repeatedly.

The guard gets more tests than anything else, and cheaper ones, because a
press now *drops every table*: it is the only thing between this button and a
real evening's database.
"""

import asyncio
import datetime
import json
import time
from uuid import uuid4 as get_uuid

import pytest

from backend import demo_game
from backend.admin_interface import AdminInterface
from backend.database import session_scope
from backend.model import Game
from backend.model import Shot
from backend.model import User
from backend.reset_db import SAMPLE_SEED
from backend.reset_db import sample_game_id
from backend.test_world import ids
from backend.test_world import replay as replay_mod
from backend.user_interface import UserInterface


@pytest.fixture(autouse=True)
def no_run_left_behind():
    """The run is module state, so it has to be cleared between tests."""
    demo_game._reset_for_tests()
    yield
    demo_game._reset_for_tests()


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def test_a_player_in_a_team_stops_the_demo_dead(db_session, user_in_team):
    """The whole point of the guard: this must never run against a real game."""
    with pytest.raises(demo_game.DemoGameRefused):
        demo_game.start()

    assert db_session.get(Game, sample_game_id()) is None
    assert demo_game.status()["state"] == demo_game.STATE_IDLE
    # Refused before anything was created *and* before anything was dropped:
    # the player who caused the refusal is still there.
    assert db_session.get(User, user_in_team) is not None


def test_a_game_with_no_players_yet_stops_the_demo_dead(db_session, one_game):
    """An admin's freshly created game has nobody in a team to notice.

    Which is fine while the button only *adds* to a database, and not fine at
    all now that it empties one: the teams somebody set up ten minutes ago
    would go with everything else.
    """
    with pytest.raises(demo_game.DemoGameRefused) as refusal:
        demo_game.start()

    assert str(one_game) in str(refusal.value)
    assert db_session.get(Game, one_game) is not None
    assert demo_game.status()["state"] == demo_game.STATE_IDLE


def test_the_demos_own_game_is_not_a_foreign_one(db_session):
    """A leftover sample game is the demo's to wipe, not somebody else's."""
    AdminInterface().create_game(sample_game_id())

    assert demo_game.foreign_games() == []


def test_a_browser_that_never_joined_is_not_a_real_game(db_session, user_factory):
    """A nameless user row is somebody who opened the app once, not a player."""
    user_factory()

    assert demo_game.strangers() == []


def test_the_demo_cast_are_not_strangers_to_themselves(db_session, one_team):
    """A user carrying a demo id counts as the demo's own, team or no team."""
    cast_id = sorted(demo_game.demo_user_ids())[0]
    with UserInterface(cast_id) as ui:
        ui.join_team(one_team)

    assert demo_game.strangers() == []


@pytest.mark.asyncio
async def test_a_press_wipes_whatever_is_there_and_starts_a_fresh_armed_game(
    db_session,
):
    """The button's whole contract, on two databases it has to cope with.

    Whatever state a previous press (or a crash part-way through one) left
    behind, a press empties every table and rebuilds the game from the seed.
    That is what makes "stop it and start it again" replay the evening from
    the top rather than carry on from shot four, and it is why ``_provision``
    no longer has to work out how much of the cast survived.

    And the game it rebuilds is one the shots can actually change: the cast
    arrive with no ammo and no weapon at all (``DEFAULT_SHOT_DAMAGE`` is zero,
    so a shot from one of them could be confirmed as a hit and still take
    nobody's last hit point), in a game that is created paused.
    """
    admin = AdminInterface()

    # Shape 1: a game row and a stray browser user, with no cast behind either
    # - provisioning stopped at the first commit `test_world.cast.provision`
    # makes. Neither blocks the demo, and neither survives it.
    admin.create_game(sample_game_id())
    stray = get_uuid()
    with UserInterface(stray) as ui:
        ui.get_user()

    demo_game.start(total_s=0.0)
    await demo_game._current.task

    status = demo_game.status()
    assert status["state"] == demo_game.STATE_DONE
    assert status["error"] is None
    assert status["fired"] == 10

    with session_scope() as session:
        assert session.query(User).count() == 30
        assert session.get(User, stray) is None

        # Unpaused: a game created by the demo starts inactive, and a paused
        # game is a demo of nothing.
        assert session.get(Game, sample_game_id()).active is True

        # Armed: plenty of ammo, the weakest weapon, no armour. Ten of them
        # fired a shot, which costs a bullet and is handed one back.
        for user in session.query(User).all():
            assert user.num_bullets == demo_game.DEMO_BULLETS
            assert user.shot_damage == demo_game.DEMO_SHOT_DAMAGE
            assert user.shot_timeout == demo_game.DEMO_SHOT_TIMEOUT
            assert user.hit_points == demo_game.DEMO_HIT_POINTS

        # The damage is copied onto the shot when it is fired, so an unarmed
        # cast would leave ten shots that kill nobody however they are judged.
        for shot in session.query(Shot).all():
            assert shot.shot_damage == demo_game.DEMO_SHOT_DAMAGE

    # Shape 2: that finished game, with two players deleted out from under it
    # - one a bystander, one a shooter, whose shot goes with them. The next
    # press does not repair this; it replaces it.
    bystander = ids.user_id(SAMPLE_SEED, "horseferry-2")
    shooter = ids.user_id(SAMPLE_SEED, "victoria-3")  # fired S2
    admin.delete_user(bystander)
    admin.delete_user(shooter)

    with session_scope() as session:
        assert session.query(User).count() == 28
        assert session.query(Shot).count() == 9

    demo_game._reset_for_tests()
    demo_game.start(total_s=0.0)
    await demo_game._current.task

    status = demo_game.status()
    assert status["state"] == demo_game.STATE_DONE
    assert status["error"] is None
    assert status["fired"] == 10

    with session_scope() as session:
        assert session.query(User).count() == 30
        assert session.query(Shot).count() == 10
        for user_id in (bystander, shooter):
            user = session.get(User, user_id)
            assert user is not None
            assert user.team_id is not None
            assert user.identity_slot is not None


async def wait_until(predicate, timeout=60.0):
    """Poll ``predicate`` on the event loop, giving the drip room to run.

    Provisioning blocks the loop for several seconds, so a bare sleep would be
    racing it; asking repeatedly for the condition we actually care about is
    the only stable way to observe a run mid-flight.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("timed out waiting for the demo game")


def shots_in_database():
    with session_scope() as session:
        return session.query(Shot).count()


@pytest.mark.asyncio
async def test_the_shots_arrive_one_at_a_time_and_can_be_stopped(db_session):
    """Fire, watch it mid-run, cancel, start again from the top."""
    # Ten seconds between shots: slow enough that the run is definitely still
    # going, and still going by a wide margin, when we look at it.
    demo_game.start(total_s=100.0)
    first_run = demo_game._current

    # Idempotent: a second press must not restart or double up.
    demo_game.start(total_s=1.0)
    assert demo_game._current is first_run

    await wait_until(lambda: demo_game.status()["fired"] >= 1)
    status = demo_game.status()
    assert status["running"]
    assert status["state"] == demo_game.STATE_FIRING
    assert status["total"] == 10
    assert status["interval_s"] == 10.0
    assert 0 < status["next_in_s"] <= 10.0
    # One shot, not ten: the rest are still waiting their turn.
    assert status["fired"] == 1
    assert shots_in_database() == 1

    with session_scope() as session:
        assert session.query(User).count() == 30

    demo_game.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_run.task
    assert demo_game.status()["state"] == demo_game.STATE_CANCELLED
    # What was fired stays fired, until somebody presses the button again.
    assert shots_in_database() == 1

    # Restarting replays rather than resuming: the one shot that got out is
    # wiped with everything else, and all ten are fired afresh.
    demo_game.start(total_s=0.0)
    assert demo_game._current is not first_run
    await demo_game._current.task

    status = demo_game.status()
    assert status["state"] == demo_game.STATE_DONE
    assert status["error"] is None
    assert status["fired"] == 10
    assert status["missing"] == []
    assert shots_in_database() == 10


@pytest.mark.asyncio
async def test_each_shot_is_re_anchored_so_it_reads_as_just_fired(db_session):
    """Time is sped up, but every fix keeps the age its own shot gave it.

    This is the property that makes the drip safe to use as a fixture: the
    ninety minutes of world time are squashed into a few seconds of wall time,
    and yet a shot's location_context still says what the world's telemetry
    table says it should.
    """
    fired_from = time.time()
    demo_game.start(total_s=0.0)
    await demo_game._current.task
    fired_until = time.time()

    assert demo_game.status()["state"] == demo_game.STATE_DONE

    scenes = {
        scene["scenario"]: scene for scene in replay_mod.load_world()["scenes"]["shots"]
    }

    for scenario, scene in scenes.items():
        shot = db_session.get(Shot, ids.shot_id(SAMPLE_SEED, scenario))
        stamped = shot.time_created.replace(tzinfo=datetime.timezone.utc).timestamp()

        # Every shot is "now", not the moment ninety minutes ago it depicts.
        assert fired_from - 1 <= stamped <= fired_until + 1

        context = {
            str(entry["user_id"]): entry for entry in json.loads(shot.location_context)
        }
        for role in ("shooter", "target"):
            entry = context[str(ids.user_id(SAMPLE_SEED, scene[role]["slug"]))]
            stamp = entry["timestamp"]
            age = None if stamp is None else round(stamped - stamp)
            assert age == scene["telemetry"][role].get("fix_age_s")


def test_the_admin_endpoints_report_idle_and_refuse_a_real_game(
    admin_api_client, user_in_team
):
    """The HTTP surface: a status anyone can poll, and a 409 with the reason."""
    status = admin_api_client.get("/api/admin_demo_game_status")
    assert status.status_code == 200
    assert status.json()["state"] == demo_game.STATE_IDLE

    refused = admin_api_client.post("/api/admin_start_demo_game")
    assert refused.status_code == 409
    assert "demo cast" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_a_dead_shooter_is_skipped_rather_than_stopping_the_run(
    db_session, mocker
):
    """A demo player has one hit point, so the queue can kill a later shooter.

    Ten shots at thirty players who have no armour: adjudicate one of them as
    a hit -- which is what the auto-actions the demo exists to show off do --
    and the target is dead. If a later scenario has them shooting back,
    ``submit_shot`` refuses with "User is dead", and that used to end the run
    on the spot with the whole rest of the demo unfired.
    """
    world = replay_mod.load_world()
    doomed = replay_mod.demo_shots(world)[1]
    victim = ids.user_id(SAMPLE_SEED, doomed["shooter"]["slug"])

    real_fire = replay_mod.fire_shot

    def kill_the_next_shooter(*args, **kwargs):
        row = real_fire(*args, **kwargs)
        with UserInterface(victim) as ui:
            ui.hit(demo_game.DEMO_HIT_POINTS)
        return row

    mocker.patch.object(replay_mod, "fire_shot", side_effect=kill_the_next_shooter)

    demo_game.start(total_s=0.0)
    await demo_game._current.task

    status = demo_game.status()
    assert status["state"] == demo_game.STATE_DONE
    assert status["error"] is None
    assert status["skipped"] == [
        {"scenario": doomed["scenario"], "reason": "User is dead"}
    ]
    assert status["fired"] == 9
    assert doomed["scenario"] not in status["scenarios"]
    assert shots_in_database() == 9
