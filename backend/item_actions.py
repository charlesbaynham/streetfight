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


def _handle_ammo(user_interface: "UserInterface", item: ItemModel):
    user_model: UserModel = user_interface.get_user_model()
    _check_alive(user_model)
    user_interface.award_ammo(item.data["num"])
    user_interface.get_ticker().post_message(
        f"{user_model.name} collected {item.data['num']}x ammo"
    )


def _handle_armour(user_interface: "UserInterface", item: ItemModel):
    user_model: UserModel = user_interface.get_user_model()
    current_HP = user_model.hit_points

    _check_alive(user_model)

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

    if (user_model.shot_damage == weapon_data.damage) and (
        user_model.shot_timeout == weapon_data.fire_delay
    ):
        raise RuntimeError("You have already got this weapon")

    user_interface.set_weapon_data(weapon_data.damage, weapon_data.fire_delay)
    user_interface.get_ticker().post_message(f"{user_model.name} was revived!")


_ACTIONS = {
    ItemType.AMMO: _handle_ammo,
    ItemType.ARMOUR: _handle_armour,
    ItemType.MEDPACK: _handle_medpack,
    ItemType.WEAPON: _handle_weapon,
}


def do_item_actions(user_interface: "UserInterface", item: ItemModel):
    return _ACTIONS[item.itype](user_interface, item)
