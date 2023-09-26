from .items import DecodedItem
from .model import ItemType
from .user_interface import UserInterface


def _handle_ammo(user_interface: UserInterface, item: DecodedItem):
    pass


_ACTIONS = {
    ItemType.AMMO: _handle_ammo,
}


def do_item_actions(user_interface: UserInterface, item: DecodedItem):
    return _ACTIONS[item.itype](user_interface, item)
