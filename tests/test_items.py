import os
from uuid import UUID

import pydantic
import pytest
from fastapi.exceptions import HTTPException

from backend.items import DecodedItem
from backend.user_interface import UserInterface

# Mocking the environment variable for testing

os.environ["SECRET_KEY"] = "test_secret_key"

SAMPLE_SIGNED_ARMOUR_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "armour",
    "data": {"num": 1},
    "sig": "1ffe1639435c5cb1e5280d3b56a768ef",
    "salt": "test_salt",
}


SAMPLE_MEDPACK_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "medpack",
    "data": {},
}

SAMPLE_AMMO_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "ammo",
    "data": {"num": 1},
}

SAMPLE_INVALID_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "random",
    "data": {"num": 1},
}


@pytest.fixture
def valid_encoded_signed_armour():
    return DecodedItem(**SAMPLE_SIGNED_ARMOUR_DATA).to_base64()


@pytest.fixture
def valid_encoded_ammo():
    return DecodedItem(**SAMPLE_AMMO_DATA).sign().to_base64()


@pytest.fixture
def valid_encoded_medpack():
    return DecodedItem(**SAMPLE_MEDPACK_DATA).sign().to_base64()


def test_valid_encoded_armour(valid_encoded_signed_armour):
    print(valid_encoded_signed_armour)


def test_decoded_item_from_base64(valid_encoded_signed_armour):
    item = DecodedItem.from_base64(valid_encoded_signed_armour)

    print(f"Encoded: {valid_encoded_signed_armour}")
    print(f"Decoded: {item.dict()}")

    assert item.id == SAMPLE_SIGNED_ARMOUR_DATA["id"]
    assert item.itype == SAMPLE_SIGNED_ARMOUR_DATA["itype"]
    assert item.data == SAMPLE_SIGNED_ARMOUR_DATA["data"]
    assert item.sig == SAMPLE_SIGNED_ARMOUR_DATA["sig"]
    assert item.salt == SAMPLE_SIGNED_ARMOUR_DATA["salt"]


def test_decoded_item_to_base64(valid_encoded_signed_armour):
    item = DecodedItem.from_base64(valid_encoded_signed_armour)
    reencoded_item = item.to_base64()
    assert reencoded_item == valid_encoded_signed_armour


def test_valid_signature(valid_encoded_signed_armour):
    item = DecodedItem.from_base64(valid_encoded_signed_armour)
    assert item.validate_signature() is None


def test_signature_changes(valid_encoded_signed_armour):
    item = DecodedItem.from_base64(valid_encoded_signed_armour)
    assert item.validate_signature() is None
    item.itype = "armour1"
    assert item.validate_signature() is not None


def test_invalid_signature(valid_encoded_signed_armour):
    item = DecodedItem.from_base64(valid_encoded_signed_armour)
    item.sig = "invalid_signature"
    assert item.validate_signature() == "Signature mismatch"


def test_no_signature(valid_encoded_signed_armour):
    item = DecodedItem.from_base64(valid_encoded_signed_armour)
    item.sig = None
    assert item.validate_signature() == "Item not signed"


def test_can_sign(valid_encoded_signed_armour):
    item = DecodedItem.from_base64(valid_encoded_signed_armour)
    item.sig = None
    item.salt = None

    item.sign()

    assert item.validate_signature() == None


def test_collect_item_valid(valid_encoded_signed_armour, user_in_team):
    UserInterface(user_in_team).collect_item(valid_encoded_signed_armour)


def test_collect_item_invalid_signature(valid_encoded_signed_armour, user_in_team):
    item = DecodedItem.from_base64(valid_encoded_signed_armour)
    item.sig = "invalid_signature"
    invalid_encoded_item = item.to_base64()

    with pytest.raises(HTTPException, match="The scanned item is invalid"):
        UserInterface(user_in_team).collect_item(invalid_encoded_item)


def test_collect_item_duplicate_item(valid_encoded_signed_armour, user_in_team):
    UserInterface(user_in_team).collect_item(valid_encoded_signed_armour)

    with pytest.raises(HTTPException, match="Item has already been collected"):
        UserInterface(user_in_team).collect_item(valid_encoded_signed_armour)


def test_can_generate_valid_item():
    assert DecodedItem(**SAMPLE_AMMO_DATA).sign().validate_signature() is None


def test_can_encode_valid_item():
    DecodedItem(**SAMPLE_AMMO_DATA).sign().to_base64()


def test_can_encode_and_decode_valid_item():
    encoded = DecodedItem(**SAMPLE_AMMO_DATA).sign().to_base64()

    decoded = DecodedItem.from_base64(encoded)

    assert isinstance(encoded, str)

    assert decoded.validate_signature() is None


def test_cannot_construct_invalid_item():
    with pytest.raises(pydantic.ValidationError):
        DecodedItem(**SAMPLE_INVALID_DATA)


def test_collecting_armour_when_alive(valid_encoded_signed_armour, user_in_team):
    assert UserInterface(user_in_team).get_user_model().hit_points == 1
    UserInterface(user_in_team).collect_item(valid_encoded_signed_armour)
    assert UserInterface(user_in_team).get_user_model().hit_points == 2


def test_collecting_armour_when_dead(valid_encoded_signed_armour, user_in_team):
    UserInterface(user_in_team).award_HP(-1)
    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_encoded_signed_armour)


def test_collecting_ammo_when_alive(valid_encoded_ammo, user_in_team):
    assert UserInterface(user_in_team).get_user_model().num_bullets == 0
    UserInterface(user_in_team).collect_item(valid_encoded_ammo)
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_collecting_revive_while_alive(valid_encoded_medpack, user_in_team):
    assert UserInterface(user_in_team).get_user_model().hit_points == 1
    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_encoded_medpack)
    assert UserInterface(user_in_team).get_user_model().hit_points == 1


def test_collecting_revive_while_dead(valid_encoded_medpack, user_in_team):
    UserInterface(user_in_team).award_HP(-1)
    assert UserInterface(user_in_team).get_user_model().hit_points == 0
    UserInterface(user_in_team).collect_item(valid_encoded_medpack)
    assert UserInterface(user_in_team).get_user_model().hit_points == 1


def test_user_collect_item(api_client, team_factory):
    user_id = api_client.get(
        "/api/my_id",
    ).json()

    UserInterface(user_id).join_team(team_factory())

    item = DecodedItem(**SAMPLE_AMMO_DATA)
    item.data = {"num": 10}
    item.sign()
    valid_encoded_ammo = item.to_base64()

    assert UserInterface(user_id).get_user_model().num_bullets == 0

    r = api_client.post(
        "/api/collect_item",
        json={"data": valid_encoded_ammo},
    )

    print(r.json())
    assert r.ok

    assert UserInterface(user_id).get_user_model().num_bullets == 10


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://example.com",
        "https://example.com/subpath",
        "https://example.com/subpath/subpath2",
        "https://10.0.0.1/",
    ],
)
def test_user_collect_url(api_client, team_factory, url):
    from backend.main import _add_params_to_url

    user_id = api_client.get(
        "/api/my_id",
    ).json()

    UserInterface(user_id).join_team(team_factory())

    item = DecodedItem(**SAMPLE_AMMO_DATA)
    item.data = {"num": 10}
    item.sign()
    valid_encoded_ammo = item.to_base64()

    sample_url = _add_params_to_url(url, {"d": valid_encoded_ammo})

    assert UserInterface(user_id).get_user_model().num_bullets == 0

    r = api_client.post(
        "/api/collect_item",
        json={"data": sample_url},
    )

    print(r.json())
    assert r.ok

    assert UserInterface(user_id).get_user_model().num_bullets == 10


def test_user_collect_item_gives_message(api_user_id, api_client, team_factory):
    UserInterface(api_user_id).join_team(team_factory())

    item = DecodedItem(**SAMPLE_AMMO_DATA)
    item.data = {"num": 10}
    item.sign()
    valid_encoded_ammo = item.to_base64()

    assert UserInterface(api_user_id).get_ticker().get_messages(3) == []

    api_client.post(
        "/api/collect_item",
        json={"data": valid_encoded_ammo},
    )

    messages = UserInterface(api_user_id).get_ticker().get_messages(3)
    assert len(messages) == 1

    assert "ammo" in messages[0]
