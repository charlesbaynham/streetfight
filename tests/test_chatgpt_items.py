from backend.user_interface import UserInterface
import pytest
from uuid import UUID
from backend.items import DecodedItem
from fastapi.exceptions import HTTPException

# Mocking the environment variable for testing
import os

os.environ["SECRET_KEY"] = "test_secret_key"


@pytest.fixture
def valid_encoded_item():
    # Create a valid base64-encoded item
    item_data = {
        "id": "00000000-0000-0000-0000-000000000002",
        "item_type": "test_item",
        "data": "test_data",
        "signature": "tevQXfO6j64ng",
        "salt": "test_salt",
    }
    return DecodedItem(**item_data).to_base64()


def test_fixture(valid_encoded_item):
    print(valid_encoded_item)


def test_decoded_item_from_base64(valid_encoded_item):
    item = DecodedItem.from_base64(valid_encoded_item)
    assert item.item_type == "test_item"
    assert item.data == "test_data"
    assert item.signature == "tevQXfO6j64ng"
    assert item.salt == "test_salt"


def test_decoded_item_to_base64(valid_encoded_item):
    item = DecodedItem.from_base64(valid_encoded_item)
    reencoded_item = item.to_base64()
    assert reencoded_item == valid_encoded_item


def test_valid_signature(valid_encoded_item):
    item = DecodedItem.from_base64(valid_encoded_item)
    assert item.validate_signature() is None


def test_invalid_signature(valid_encoded_item):
    item = DecodedItem.from_base64(valid_encoded_item)
    item.signature = "invalid_signature"
    assert item.validate_signature() == "Signature mismatch"


def test_collect_item_valid(valid_encoded_item):
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    result = UserInterface(user_id).collect_item(valid_encoded_item, user_id)
    assert isinstance(result, int)


def test_collect_item_invalid_signature(valid_encoded_item):
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    item = DecodedItem.from_base64(valid_encoded_item)
    item.signature = "invalid_signature"
    invalid_encoded_item = item.to_base64()

    with pytest.raises(HTTPException, match="The scanned item is invalid"):
        UserInterface(user_id).collect_item(invalid_encoded_item, user_id)


def test_collect_item_duplicate_item(valid_encoded_item, monkeypatch):
    user_id = UUID("00000000-0000-0000-0000-000000000001")

    # Mock the is_in_database() method to return True (duplicate item)
    def mock_is_in_database():
        return True

    monkeypatch.setattr(DecodedItem, "is_in_database", mock_is_in_database)

    with pytest.raises(HTTPException, match="Item has already been collected"):
        UserInterface(user_id).collect_item(valid_encoded_item, user_id)
