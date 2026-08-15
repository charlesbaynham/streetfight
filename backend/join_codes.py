"""Signed "join by QR" codes: ``(game_id, team_id, slot)`` payloads.

A join code is printed as a QR of ``{WEBSITE_URL}?j=<b64>``; scanning one
joins you to that team and claims that identity slot (see
:func:`backend.identity_admin.claim_join_slot`). Encoding and signing mirror
:class:`backend.items.ItemModel`, sharing the one HMAC helper in
``backend/qr_signing.py``.
"""

import base64
import binascii
import json
import logging
import os
import re
from typing import Optional
from urllib.parse import parse_qs
from urllib.parse import urlparse
from uuid import UUID

import pydantic

from .dotenv import load_env_vars
from .items import _UUIDEncoder
from .qr_signing import sign_payload
from .utils import add_params_to_url

logger = logging.getLogger(__name__)


load_env_vars()


class JoinCodeModel(pydantic.BaseModel):
    game_id: UUID
    team_id: UUID
    slot: int

    sig: Optional[str] = None

    @classmethod
    def from_base64(cls, encoded_string: str):
        assert isinstance(encoded_string, str)

        logger.debug("Decoding join code %s", encoded_string)

        # Parse from URL if present
        if re.match(r"http", encoded_string):
            parsed_url = urlparse(encoded_string)
            query_params = parse_qs(parsed_url.query)
            try:
                encoded_string = query_params["j"][0]
            except KeyError:
                raise ValueError(f"URL carries no join code: {encoded_string}")

        try:
            decoded_bytes = base64.b64decode(encoded_string)
            decoded_str = decoded_bytes.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            raise ValueError(f"Badly formatted join code string: {encoded_string}")

        logger.debug("Raw decoded base64: %s", decoded_str)

        decoded_dict = json.loads(decoded_str)

        logger.debug("Decoded result: %s", decoded_dict)

        return cls(**decoded_dict)

    def to_base64(self):
        json_encoded_obj = json.dumps(self.model_dump(), cls=_UUIDEncoder)
        logger.debug("JSON encoded: %s", json_encoded_obj)
        return base64.b64encode(json_encoded_obj.encode("utf-8")).decode("utf-8")

    def get_signature(self) -> str:
        return sign_payload("join", self.game_id, self.team_id, self.slot)

    def sign(self):
        self.sig = self.get_signature()
        logger.debug("Signed join code %s with signature %s", self, self.sig)

        return self

    def validate_signature(self) -> Optional[str]:
        if self.sig is None:
            return "Join code not signed"

        valid_signature = self.get_signature()

        logger.debug("Correct sig=%s, current sig=%s", valid_signature, self.sig)

        if valid_signature != self.sig:
            return "Signature mismatch"

        return None


def make_join_url(game_id: UUID, team_id: UUID, slot: int) -> str:
    """A signed ``{WEBSITE_URL}?j=<b64>`` join URL, ready for a QR code."""
    code = JoinCodeModel(game_id=game_id, team_id=team_id, slot=slot).sign()
    return add_params_to_url(os.environ["WEBSITE_URL"], {"j": code.to_base64()})
