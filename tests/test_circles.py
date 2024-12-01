from backend.user_interface import UserInterface


def test_circles_start_empty(user_in_team):
    ui = UserInterface(user_in_team)

    for name, value in ui.get_circles().items():
        assert value is None
