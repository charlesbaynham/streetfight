from typing import TYPE_CHECKING

from .items import ItemDataWeapon
from .items import ItemModel
from .model import ItemType
from .model import UserModel

if TYPE_CHECKING:
    from .user_interface import UserInterface


def _check_alive(user_model: UserModel):
    if user_model.hit_points <= 0:
        raise RuntimeError("Cannot collect, you are dead!")


def _handle_ammo_user(user_interface: "UserInterface", item: ItemModel):
    user_model: UserModel = user_interface.get_user_model()
    _check_alive(user_model)
    user_interface.award_ammo(item.data["num"])
    user_interface.get_ticker().post_message(
        f"{user_model.name} collected {item.data['num']}x ammo"
    )


def _handle_ammo_team(user_interface: "UserInterface", item: ItemModel):
    from .user_interface import UserInterface

    user_model: UserModel = user_interface.get_user_model()
    _check_alive(user_model)

    user_orm = user_interface.get_user()
    team_name = user_orm.team.name
    users_in_team = user_orm.team.users

    for team_user in users_in_team:
        UserInterface(team_user.id, session=user_interface.get_session()).award_ammo(
            item.data["num"]
        )

    user_interface.get_ticker().post_message(
        f"Team {team_name} collected {item.data['num']}x ammo"
    )


def _handle_armour(user_interface: "UserInterface", item: ItemModel):
    user_model: UserModel = user_interface.get_user_model()
    current_HP = user_model.hit_points

    _check_alive(user_model)

    if current_HP >= 1 + item.data["num"]:
        raise RuntimeError("You already have armour as good as this")

    user_interface.award_HP(item.data["num"] - current_HP + 1)
    user_interface.get_ticker().post_message(
        f"{user_model.name} collected a level {item.data['num']} armour"
    )


def _handle_medpack(user_interface: "UserInterface", item: ItemModel):
    user_model: UserModel = user_interface.get_user_model()
    if user_model.hit_points > 0:
        raise RuntimeError("Medpacks can only be used on dead players")
    user_interface.award_HP(1 - user_model.hit_points)
    user_interface.get_ticker().post_message(f"{user_model.name} was revived!")


def _handle_weapon(user_interface: "UserInterface", item: ItemModel):
    weapon_data = ItemDataWeapon(**item.data)
    user_model: UserModel = user_interface.get_user_model()

    _check_alive(user_model)

    if (user_model.shot_damage == weapon_data.shot_damage) and (
        user_model.shot_timeout == weapon_data.shot_timeout
    ):
        raise RuntimeError("You have already got this weapon")

    user_interface.set_weapon_data(weapon_data.shot_damage, weapon_data.shot_timeout)
    user_interface.get_ticker().post_message(f"{user_model.name} was revived!")


_ACTIONS = {
    (ItemType.AMMO, False): _handle_ammo_user,
    (ItemType.AMMO, True): _handle_ammo_team,
    (ItemType.ARMOUR, False): _handle_armour,
    (ItemType.MEDPACK, False): _handle_medpack,
    (ItemType.WEAPON, False): _handle_weapon,
}


def do_item_actions(user_interface: "UserInterface", item: ItemModel):
    key = (item.itype, item.collected_as_team)
    try:
        _ACTIONS[key](user_interface, item)
    except KeyError:
        raise NotImplementedError(f"Item collection for {key} has not been implemented")
