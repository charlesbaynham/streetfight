import crypt
import os

import pydantic
from dotenv import find_dotenv
from dotenv import load_dotenv


def collect_item(encoded_item: str, user_id: UUID) -> int:
    """Add the scanned item into a user's inventory"""

    item = decode_item(encoded_item)

    item_validation_error = item.validate_signature()
    if item_validation_error:
        raise HTTPException(402, f"The scanned item is invalid - error {error}")

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

    def validate_signature(self):
        valid_signature = sign_item(self.item_type, self.data, self.salt)
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
