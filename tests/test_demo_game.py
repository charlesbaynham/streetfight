"""The admin's "Fire demo game" button.

The expensive part of every test here is provisioning: thirty players picking
outfits through the real allocator takes a few seconds, and each test gets a
fresh database. So the drip's behaviour -- firing, cancelling, resuming, and
being idempotent -- is exercised once, in one test, rather than paid for four
times over.
"""

import asyncio
import datetime
import json
import time

import pytest

from backend import demo_game
from backend.database import session_scope
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

    from backend.model import Game

    assert db_session.get(Game, sample_game_id()) is None
    assert demo_game.status()["state"] == demo_game.STATE_IDLE


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
    """Fire, pause mid-run, cancel, resume, finish - all on one provisioning."""
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
    # What was fired stays fired; nothing else joins it.
    assert shots_in_database() == 1

    # Restarting resumes rather than replaying: the shot ids come from the
    # seed, so the one already in the game is counted and skipped.
    demo_game.start(total_s=0.0)
    assert demo_game._current is not first_run
    await demo_game._current.task

    status = demo_game.status()
    assert status["state"] == demo_game.STATE_DONE
    assert status["error"] is None
    assert status["already_fired"] == 1
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
