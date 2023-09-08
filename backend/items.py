import crypt
import logging
import json
from fastapi.exceptions import HTTPException
from uuid import UUID
import os

import pydantic
from dotenv import find_dotenv
import base64
from dotenv import load_dotenv
from typing import Optional
from typing import List

logger = logging.getLogger(__name__)


def sign_strings(strings: List[str]) -> str:
    """Concatenate a list of strings with a private secret and hash the outcome

    Args:
        strings (List[str]): Strings to hash

    Returns:
        str: Hash of the inputs
    """


def collect_item(encoded_item: str, user_id: UUID) -> int:
    """Add the scanned item into a user's inventory"""

    item = DecodedItem.from_base64(encoded_item)

    item_validation_error = item.validate_signature()
    if item_validation_error:
        raise HTTPException(
            402, f"The scanned item is invalid - error {item_validation_error}"
        )

    if item.is_in_database():
        raise HTTPException(403, "Item has already been collected")

    # TODO: Check here if the user is in a team, can collect the item, etc
    item.do_actions(user_id)

    return item.store(user_id)


class DecodedItem(pydantic.BaseModel):
    item_type: str
    data: str
    signature: str
    salt: Optional[str]

    @classmethod
    def from_base64(cls, encoded_string: str):
        logger.debug("Decoding item %s", encoded_string)

        # Decode the base64 string
        decoded_bytes = base64.b64decode(encoded_string)

        # Convert bytes to a string
        decoded_str = decoded_bytes.decode("utf-8")

        # Parse the JSON string into a Python dictionary
        decoded_dict = json.loads(decoded_str)

        logger.debug("Decoded result: %s", decoded_dict)

        return cls(**decoded_dict)

    def to_base64(self):
        return base64.b64encode(json.dumps(self.dict()).encode("utf-8"))

    def validate_signature(self):
        valid_signature = self.get_signature()
        if valid_signature != self.signature:
            return "Signature mismatch"

        return None

    def get_signature(self) -> str:
        load_dotenv(find_dotenv())
        secret_key = os.environ["SECRET_KEY"]

        if not self.salt:
            self.salt = crypt.mksalt()

        payload = self.item_type + self.data + secret_key

        return crypt.crypt(payload, salt=self.salt)
