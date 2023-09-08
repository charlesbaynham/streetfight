from typing import Dict
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


logger = logging.getLogger(__name__)


class _UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # if the obj is uuid, we simply return the value of uuid
            return obj.hex
        return json.JSONEncoder.default(self, obj)


class DecodedItem(pydantic.BaseModel):
    id: UUID
    item_type: str
    data: Dict
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
        json_encoded_obj = json.dumps(self.dict(), cls=_UUIDEncoder)
        return base64.b64encode(json_encoded_obj.encode("utf-8")).decode("utf-8")

    def validate_signature(self):
        valid_signature = self.get_signature()
        logger.debug("Correct sig=%s, current sig=%s", valid_signature, self.signature)
        if valid_signature != self.signature:
            return "Signature mismatch"

        return None

    def _json_data(self) -> str:
        return json.dumps(self.data)

    def get_signature(self) -> str:
        load_dotenv(find_dotenv())
        secret_key = os.environ["SECRET_KEY"]

        if not self.salt:
            self.salt = crypt.mksalt()

        payload = str(self.id) + self.item_type + self._json_data() + secret_key

        return crypt.crypt(payload, salt=self.salt)
