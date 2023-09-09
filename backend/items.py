import base64
import hashlib
import json
import logging
import os
from typing import Dict
from typing import Optional
from uuid import UUID
from .model import ItemType

import pydantic
from dotenv import find_dotenv
from dotenv import load_dotenv


logger = logging.getLogger(__name__)

load_dotenv(find_dotenv())


class _UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # if the obj is uuid, we simply return the value of uuid
            return obj.hex
        return json.JSONEncoder.default(self, obj)


class DecodedItem(pydantic.BaseModel):
    id: UUID
    item_type: ItemType
    data: Dict
    signature: Optional[str]
    salt: Optional[str]

    @classmethod
    def from_base64(cls, encoded_string: str):
        assert isinstance(encoded_string, str)

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
        json_encoded_obj = json.dumps(self.dict(), cls=_UUIDEncoder)
        return base64.b64encode(json_encoded_obj.encode("utf-8")).decode("utf-8")

    def sign(self):
        self.signature = self.get_signature()
        logger.debug("Signed item %s with signature %s", self, self.signature)

        return self

    def validate_signature(self):
        if self.signature is None:
            return "Item not signed"

        valid_signature = self.get_signature()

        logger.debug("Correct sig=%s, current sig=%s", valid_signature, self.signature)

        if valid_signature != self.signature:
            return "Signature mismatch"

        return None

    def data_as_json(self) -> str:
        return json.dumps(self.data)

    def get_signature(self) -> str:
        secret_key = os.environ["SECRET_KEY"]

        # Input password to be hashed
        payload = str(self.id) + self.item_type + self.data_as_json() + secret_key

        # Generate a random salt
        if not self.salt:
            self.salt = os.urandom(16).hex()

        # Parameters for scrypt (adjust these as needed)
        n = 16384  # CPU/memory cost factor
        r = 8  # Block size
        p = 1  # Parallelization factor

        # Hash the password using scrypt
        hashed_payload = hashlib.scrypt(
            payload.encode("utf-8"),
            salt=self.salt.encode("utf-8"),
            n=n,
            r=r,
            p=p,
            dklen=64,
        )

        # Convert the hashed password to hexadecimal representation
        hashed_password_hex = hashed_payload.hex()

        logger.debug(
            "Hash of payload %s, salt=%s is %s", payload, self.salt, hashed_password_hex
        )

        return hashed_password_hex
