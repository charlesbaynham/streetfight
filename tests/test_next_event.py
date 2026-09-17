import time

import pytest

from backend import next_event
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
