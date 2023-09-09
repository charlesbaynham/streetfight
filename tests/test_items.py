import pytest


import os
from uuid import UUID

import pytest
from fastapi.exceptions import HTTPException

from backend.items import DecodedItem
from backend.user_interface import UserInterface

# Mocking the environment variable for testing

os.environ["SECRET_KEY"] = "test_secret_key"

SAMPLE_SIGNED_ARMOUR_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "item_type": "armour",
    "data": {"num": 1},
    "signature": "1ffe1639435c5cb1e5280d3b56a768ef55ed9c747b0a3e08d933a68e37e7d3fc47b84bbe67e4d37f21a1f440e523f960e7788b8defa814cf48e3699cdaffd4d3",
    "salt": "test_salt",
}


SAMPLE_MEDPACK_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "item_type": "medpack",
    "data": {},
}

SAMPLE_HEALTH_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "item_type": "health",
    "data": {"num": 1},
}

SAMPLE_INVALID_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "item_type": "random",
    "data": {"num": 1},
}


@pytest.fixture
def valid_encoded_armour():
    # Create a valid base64-encoded item
    return DecodedItem(**SAMPLE_SIGNED_ARMOUR_DATA).to_base64()


def test_fixture(valid_encoded_armour):
    print(valid_encoded_armour)


def test_decoded_item_from_base64(valid_encoded_armour):
    item = DecodedItem.from_base64(valid_encoded_armour)
    assert item.id == SAMPLE_SIGNED_ARMOUR_DATA["id"]
    assert item.item_type == SAMPLE_SIGNED_ARMOUR_DATA["item_type"]
    assert item.data == SAMPLE_SIGNED_ARMOUR_DATA["data"]
    assert item.signature == SAMPLE_SIGNED_ARMOUR_DATA["signature"]
    assert item.salt == SAMPLE_SIGNED_ARMOUR_DATA["salt"]


def test_decoded_item_to_base64(valid_encoded_armour):
    item = DecodedItem.from_base64(valid_encoded_armour)
    reencoded_item = item.to_base64()
    assert reencoded_item == valid_encoded_armour


def test_valid_signature(valid_encoded_armour):
    item = DecodedItem.from_base64(valid_encoded_armour)
    assert item.validate_signature() is None


def test_signature_changes(valid_encoded_armour):
    item = DecodedItem.from_base64(valid_encoded_armour)
    assert item.validate_signature() is None
    item.item_type = "armour1"
    assert item.validate_signature() is not None


def test_invalid_signature(valid_encoded_armour):
    item = DecodedItem.from_base64(valid_encoded_armour)
    item.signature = "invalid_signature"
    assert item.validate_signature() == "Signature mismatch"


def test_no_signature(valid_encoded_armour):
    item = DecodedItem.from_base64(valid_encoded_armour)
    item.signature = None
    assert item.validate_signature() == "Item not signed"


def test_collect_item_valid(valid_encoded_armour, user_in_team):
    UserInterface(user_in_team).collect_item(valid_encoded_armour)


def test_collect_item_invalid_signature(valid_encoded_armour, user_in_team):
    item = DecodedItem.from_base64(valid_encoded_armour)
    item.signature = "invalid_signature"
    invalid_encoded_item = item.to_base64()

    with pytest.raises(HTTPException, match="The scanned item is invalid"):
        UserInterface(user_in_team).collect_item(invalid_encoded_item)


def test_collect_item_duplicate_item(valid_encoded_armour, user_in_team):
    UserInterface(user_in_team).collect_item(valid_encoded_armour)

    with pytest.raises(HTTPException, match="Item has already been collected"):
        UserInterface(user_in_team).collect_item(valid_encoded_armour)


def test_can_generate_valid_item():
    item = DecodedItem(**SAMPLE_HEALTH_DATA)


def test_collecting_armour_when_alive(valid_encoded_armour, user_in_team):
    UserInterface(user_in_team).collect_item(valid_encoded_armour)


# def test_collecting_armour_when_dead():
#     raise NotImplementedError


# def test_collecting_ammo():
#     raise NotImplementedError


# def test_collecting_revive():
#     raise NotImplementedError
