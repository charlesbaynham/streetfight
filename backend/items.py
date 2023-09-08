from .user_interface import UserInterface


def collect_item(encoded_item: str, user_id:UUID) -> int:
    """Add the scanned item into a user's inventory"""
    
    item = decode_item(encoded_item)

    item_validation_error = item.validate()
    if item_validation_error:
        raise HTTPException(402, f"The scanned item is invalid - error {error}")

    if item.is_in_database():
        raise HTTPException(403, "Item has already been collected")
    
    # TODO: Check here if the user is in a team, can collect the item, etc
    item.do_actions(user_id)

    return item.store(user_id)
