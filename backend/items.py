import base64
import binascii
import json
import logging
import re
from typing import Dict
from typing import List
from typing import Optional
from urllib.parse import parse_qs
from urllib.parse import urlparse
from uuid import UUID

import pydantic

from .dotenv import load_env_vars
from .model import ItemType
from .qr_signing import sign_payload

logger = logging.getLogger(__name__)


load_env_vars()


class _UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # if the obj is uuid, we simply return the value of uuid
            return obj.hex
        return json.JSONEncoder.default(self, obj)


class ItemDataAmmo(pydantic.BaseModel):
    num: int


class ItemDataArmour(pydantic.BaseModel):
    num: int


class ItemDataMedpack(pydantic.BaseModel):
    pass


class ItemDataWeapon(pydantic.BaseModel):
    shot_damage: int
    shot_timeout: float


class ItemDataRadar(pydantic.BaseModel):
    minutes: int = 5


class ItemDataCircleWarning(pydantic.BaseModel):
    minutes: int = 10


ITEM_TYPE_VALIDATORS = {
    ItemType.AMMO: ItemDataAmmo,
    ItemType.ARMOUR: ItemDataArmour,
    ItemType.MEDPACK: ItemDataMedpack,
    ItemType.WEAPON: ItemDataWeapon,
    ItemType.RADAR: ItemDataRadar,
    ItemType.CIRCLE_WARNING: ItemDataCircleWarning,
}


class ItemModel(pydantic.BaseModel):
    id: UUID
    itype: ItemType
    data: Dict
    collected_only_once: bool
    collected_as_team: bool

    batch: Optional[str] = None
    """A label minted into the payload so a set of codes can be withdrawn
    together. ``None`` on every code printed before it existed."""

    unlimited: bool = False
    """Scannable any number of times by the same player - what the sandbox's
    wall posters need, since ``collected_only_once=False`` still blocks a
    second scan by the same person. Real codes never set it."""

    sig: Optional[str] = None
    # Pre-HMAC items were scrypt-signed with a salt. The field is kept only so
    # old URLs still parse - their signatures then fail validation (403).
    salt: Optional[str] = None

    @classmethod
    def from_base64(cls, encoded_string: str):
        assert isinstance(encoded_string, str)

        logger.debug("Decoding item %s", encoded_string)

        # Parse from URL if present
        if re.match(r"http", encoded_string):
            parsed_url = urlparse(encoded_string)
            query_params = parse_qs(parsed_url.query)
            try:
                encoded_string = query_params["d"][0]
            except KeyError:
                # A ValueError, as JoinCodeModel.from_base64 already raises
                # here: a KeyError escaped every caller's "not one of mine"
                # handling, so scanning any other http QR code - a team card,
                # a pub's wifi - was a 500 and a player's screen doing
                # nothing at all.
                raise ValueError(f"URL carries no item code: {encoded_string}")

        try:
            # Decode the base64 string
            decoded_bytes = base64.b64decode(encoded_string)

            # Convert bytes to a string
            decoded_str = decoded_bytes.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            raise ValueError(f"Badly formatted item string: {encoded_string}")

        logger.debug("Raw decoded base64: %s", decoded_str)

        # Parse the JSON string into a Python dictionary
        decoded_dict = json.loads(decoded_str)

        logger.debug("Decoded result: %s", decoded_dict)

        return cls(**decoded_dict)

    def to_base64(self):
        # Fields at their default are left out of the encoding, not just out
        # of the signature. Every character here is a character the QR has to
        # carry, and the pub certificate's code is already at the size where
        # one more version means modules too fine to print
        # (tests/test_generate_pub_pages.py). Dropping them costs nothing:
        # they parse straight back to the defaults they were left out for,
        # so an unbatched code encodes byte for byte as it did before batches
        # existed.
        json_encoded_obj = json.dumps(
            self.model_dump(exclude_defaults=True), cls=_UUIDEncoder
        )
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
        return sign_payload(
            "item",
            self.id,
            self.itype,
            self.data_as_json(),
            self.collected_only_once,
            self.collected_as_team,
            *self._late_signed_parts(),
        )

    def _late_signed_parts(self) -> List[str]:
        """The fields added after codes were already in people's pockets.

        A code is an HMAC over its payload and nothing else, which is what
        decouples the print run from the deploy - but only as long as a
        payload keeps signing the way it did when it was printed. Each late
        field therefore joins the signed message **only when it is not at its
        default**: a code minted before ``batch`` and ``unlimited`` existed
        yields byte for byte the message it always did, and still validates.
        They are named rather than positional so that setting one can never be
        read as the other.
        """
        parts: List[str] = []
        if self.batch is not None:
            parts.append(f"batch={self.batch}")
        if self.unlimited:
            parts.append("unlimited=True")
        return parts

    @pydantic.field_validator("batch")
    @classmethod
    def blank_batch_is_no_batch(cls, v):
        """An empty text field means "unbatched", not a batch named "".

        Otherwise a cleared box on the Printables page would mint codes into a
        batch nobody can withdraw by name, and one that signs differently from
        an unbatched code minted a minute earlier.
        """
        return v or None

    @pydantic.field_validator("data")
    @classmethod
    def parse_item_data(cls, v, info: pydantic.ValidationInfo):
        # "itype" is declared before "data", so it is present in info.data
        # unless it failed its own validation
        if "itype" not in info.data:
            raise ValueError("Cannot validate item data without a valid item type")

        item_type: ItemType = info.data["itype"]

        return ITEM_TYPE_VALIDATORS[item_type](**v).model_dump()
