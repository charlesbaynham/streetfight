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


class DecodedItem(pydantic.BaseModel):
    item_type: str
    data: str
    signature: str
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
        return base64.b64encode(json.dumps(self.dict()).encode("utf-8")).decode("utf-8")

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
