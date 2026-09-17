import asyncio
import time

import pytest

from backend import next_event
from backend.admin_interface import AdminInterface
from backend.model import Game
from backend.model import User
from backend.user_interface import UserInterface


@pytest.fixture
def cue(db_session):
    """Write a cue straight onto a game's columns.

    M3.1 is only the carriage - the admin controls that set these, and the
    timer that clears them, are M3.2 and M3.3.
    """

    def setter(game_id, kind, at, note=None):
        game = db_session.query(Game).filter_by(id=game_id).one()
        game.next_event_kind = kind
        game.next_event_at = at
        game.next_event_note = note
        db_session.commit()

    return setter


def test_a_game_starts_with_nothing_cued(user_in_team):
    model = UserInterface(user_in_team).get_user_model()

    assert model.next_event_kind is None
    assert model.next_event_at is None
    assert model.next_event_note is None


def test_the_cue_reaches_the_player(user_in_team, cue, db_session):
    game_id = db_session.query(User).filter_by(id=user_in_team).one().game_id
    deadline = time.time() + 600
    cue(game_id, next_event.KIND_DROP, deadline, "a medpack and two armour")

    model = UserInterface(user_in_team).get_user_model()

    assert model.next_event_kind == next_event.KIND_DROP
    assert model.next_event_at == pytest.approx(deadline)
    assert model.next_event_note == "a medpack and two armour"


def test_a_player_with_no_team_still_sees_the_cue(
    user_factory, one_game, cue, db_session
):
    """The waiting page is exactly where somebody who has signed up but not
    yet been handed a team sits, so the cue has to come off User.game rather
    than off their team's."""
    user_id = user_factory()
    db_session.query(User).filter_by(id=user_id).one().game_id = one_game
    db_session.commit()

    deadline = time.time() + 120
    cue(one_game, next_event.KIND_CIRCLE, deadline)

    model = UserInterface(user_id).get_user_model()

    assert model.next_event_kind == next_event.KIND_CIRCLE
    assert model.next_event_at == pytest.approx(deadline)


def test_a_player_in_no_game_at_all_sees_nothing(user_factory, one_game, cue):
    cue(one_game, next_event.KIND_CIRCLE, time.time() + 120)

    model = UserInterface(user_factory()).get_user_model()

    assert model.next_event_at is None


# -- the timer (backend/next_event.py) ---------------------------------------


@pytest.fixture(autouse=True)
def clean_timers():
    """Nothing armed before a test, nothing left running after one."""
    for game_id in list(next_event._pending):
        next_event.disarm(game_id)
    yield
    for game_id in list(next_event._pending):
        next_event.disarm(game_id)


def test_arming_without_an_event_loop_is_not_fatal(one_game):
    """A cue written from a CLI or a synchronous test still lands in the
    database; the startup sweep is what picks it up."""
    assert next_event.arm(one_game, time.time() + 600) is None


@pytest.mark.asyncio
async def test_the_timer_fires_at_the_deadline(one_game, mocker):
    fired = mocker.patch("backend.next_event.fire")

    next_event.arm(one_game, time.time() + 0.05)
    await asyncio.sleep(0.2)

    assert fired.call_count == 1


@pytest.mark.asyncio
async def test_re_arming_replaces_the_pending_timer(one_game, mocker):
    """Two clocks racing on one game is exactly how a circle closes early."""
    fired = mocker.patch("backend.next_event.fire")

    next_event.arm(one_game, time.time() + 0.05)
    next_event.arm(one_game, time.time() + 0.1)
    await asyncio.sleep(0.3)

    assert fired.call_count == 1
    assert not next_event._pending


@pytest.mark.asyncio
async def test_disarming_stops_the_timer(one_game, mocker):
    fired = mocker.patch("backend.next_event.fire")

    next_event.arm(one_game, time.time() + 0.05)
    next_event.disarm(one_game)
    await asyncio.sleep(0.2)

    assert fired.call_count == 0


@pytest.mark.asyncio
async def test_the_timer_fires_the_deadline_it_was_armed_for(one_game, mocker):
    """It is that deadline, not "whatever is in the database now", that
    AdminInterface.fire_next_event checks against - which is what stops a
    timer overtaken by a re-cue acting."""
    fired = mocker.patch("backend.next_event.fire")
    deadline = time.time() + 0.05

    next_event.arm(one_game, deadline)
    await asyncio.sleep(0.2)

    assert fired.call_args == mocker.call(one_game, expected_at=deadline)


def test_the_sweep_re_arms_a_future_cue(user_in_team, mocker):
    armed = mocker.patch("backend.next_event.arm")
    fired = mocker.patch("backend.next_event.fire")
    game_id = UserInterface(user_in_team).get_game_id()
    deadline = AdminInterface().cue_next_event(game_id, "circle", seconds=600)

    assert next_event.sweep() == 1

    assert armed.call_args == mocker.call(game_id, deadline)
    assert fired.call_count == 0


def test_the_sweep_fires_a_cue_whose_moment_passed_while_we_were_down(
    user_in_team, cue, mocker
):
    """A circle that should have closed ten minutes ago closes now rather
    than never: the deadline is a column precisely so a restart cannot lose
    it."""
    fired = mocker.patch("backend.next_event.fire")
    game_id = UserInterface(user_in_team).get_game_id()
    deadline = time.time() - 600
    cue(game_id, next_event.KIND_CIRCLE, deadline)

    assert next_event.sweep() == 1

    assert fired.call_args == mocker.call(game_id, expected_at=deadline)


def test_the_sweep_has_nothing_to_do_with_no_cues(user_in_team):
    assert next_event.sweep() == 0
