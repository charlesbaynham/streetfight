from .items import ItemModel
from .model import ItemType
from .user_interface import UserInterface


def _handle_ammo(user_interface: UserInterface, item: ItemModel):
    pass


_ACTIONS = {
    ItemType.AMMO: _handle_ammo,
}


def do_item_actions(user_interface: UserInterface, item: ItemModel):
    return _ACTIONS[item.itype](user_interface, item)
