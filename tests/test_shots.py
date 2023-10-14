import pytest
from fastapi.exceptions import HTTPException

from backend.user_interface import UserInterface


def test_submit_shot(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    ui.submit_shot(test_image_string)


def test_submit_shot_no_ammo(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    with pytest.raises(HTTPException):
        ui.submit_shot(test_image_string)


def test_trigger_update_event_on_shot(mocker, user_in_team, test_image_string):
    mocked = mocker.patch("backend.asyncio_triggers.trigger_update_event")
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    mocked.reset_mock()
    UserInterface(user_in_team).submit_shot(test_image_string)
    assert mocked.call_count == 1
    assert mocked.call_args_list[0][0][0] == "user"
