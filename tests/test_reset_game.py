from backend.admin_interface import AdminInterface
from backend.user_interface import UserInterface


def test_reset_game(user_in_team):
    AdminInterface().set_user_HP(user_in_team, 3)

    assert UserInterface(user_in_team).get_user_model().hit_points == 3

    game_id = UserInterface(user_in_team).get_user_model().game_id
    AdminInterface().reset_game(game_id)

    assert UserInterface(user_in_team).get_user_model().hit_points == 1


def test_reset_game_does_not_affect_another(user_factory, game_factory):
    # Make two users in two teams in separate games
    uid1 = user_factory()
    uid2 = user_factory()

    gid1 = game_factory()
    gid2 = game_factory()

    tid1 = AdminInterface().create_team(gid1, "Team 1")
    tid2 = AdminInterface().create_team(gid2, "Team 2")

    AdminInterface().add_user_to_team(uid1, tid1)
    AdminInterface().add_user_to_team(uid2, tid2)

    # Set the HPs
    AdminInterface().set_user_HP(uid1, 3)
    AdminInterface().set_user_HP(uid2, 5)

    assert UserInterface(uid1).get_user_model().hit_points == 3
    assert UserInterface(uid2).get_user_model().hit_points == 5

    # Reset game 1
    AdminInterface().reset_game(game_id=gid1)

    # Make sure that game 2 was not reset
    assert UserInterface(uid1).get_user_model().hit_points == 1
    assert UserInterface(uid2).get_user_model().hit_points == 5
