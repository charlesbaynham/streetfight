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


class _ItemDataAmmo(pydantic.BaseModel):
    num: int


class _ItemDataArmour(pydantic.BaseModel):
    num: int


class _ItemDataMedpack(pydantic.BaseModel):
    pass


ITEM_TYPE_VALIDATORS = {
    ItemType.AMMO: _ItemDataAmmo,
    ItemType.ARMOUR: _ItemDataArmour,
    ItemType.MEDPACK: _ItemDataMedpack,
}


class DecodedItem(pydantic.BaseModel):
    id: UUID
    itype: ItemType
    data: Dict
    sig: Optional[str]
    salt: Optional[str]

    @classmethod
    def from_base64(cls, encoded_string: str):
        assert isinstance(encoded_string, str)

        logger.debug("Decoding item %s", encoded_string)

        # Decode the base64 string
        decoded_bytes = base64.b64decode(encoded_string)

        # Convert bytes to a string
        decoded_str = decoded_bytes.decode("utf-8")

        logger.debug("Raw decoded base64: %s", decoded_str)

        # Parse the JSON string into a Python dictionary
        decoded_dict = json.loads(decoded_str)

        logger.debug("Decoded result: %s", decoded_dict)

        return cls(**decoded_dict)

    def to_base64(self):
        json_encoded_obj = json.dumps(self.dict(), cls=_UUIDEncoder)
        logger.debug("JSON encoded: %s", json_encoded_obj)
        return base64.b64encode(json_encoded_obj.encode("utf-8")).decode("utf-8")

    def sign(self):
        self.sig = self.get_signature()
        logger.debug("Signed item %s with signature %s", self, self.sig)

        return self

    def validate_signature(self):
        if self.sig is None:
            return "Item not signed"

        valid_signature = self.get_signature()

        logger.debug("Correct sig=%s, current sig=%s", valid_signature, self.sig)

        if valid_signature != self.sig:
            return "Signature mismatch"

        return None

    def data_as_json(self) -> str:
        return json.dumps(self.data)

    def get_signature(self) -> str:
        secret_key = os.environ["SECRET_KEY"]

        # Input password to be hashed
        payload = str(self.id) + self.itype + self.data_as_json() + secret_key

        # Generate a random salt
        if not self.salt:
            self.salt = os.urandom(8).hex()

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
            dklen=16,
        )

        # Convert the hashed password to hexadecimal representation
        hashed_password_hex = hashed_payload.hex()

        logger.debug(
            "Hash of payload %s, salt=%s is %s", payload, self.salt, hashed_password_hex
        )

        return hashed_password_hex

    @pydantic.validator("data")
    def parse_item_data(cls, v, values):
        if "itype" not in values:
            raise pydantic.ValidationError

        item_type: ItemType = values["itype"]

        ITEM_TYPE_VALIDATORS[item_type](**v)

        return v
