from backend.admin_interface import AdminInterface
from backend.user_interface import UserInterface


def test_reset_game(user_in_team):
    AdminInterface().set_user_HP(user_in_team, 3)

    assert UserInterface(user_in_team).get_user_model().hit_points == 3

    game_id = UserInterface(user_in_team).get_user_model().game_id
    AdminInterface().reset_game(game_id)

    assert UserInterface(user_in_team).get_user_model().hit_points == 1
