import os
import time
from uuid import UUID
from uuid import uuid4 as get_uuid

import pydantic
import pytest
from fastapi.exceptions import HTTPException

from backend.admin_interface import AdminInterface
from backend.admin_interface import CircleTypes
from backend.items import ItemDataArmour
from backend.items import ItemModel
from backend.model import STARTING_HIT_POINTS
from backend.model import Item
from backend.model import User
from backend.model import UserState
from backend.ticker_message_dispatcher import TickerMessageType
from backend.user_interface import UserInterface

from .shared_fixtures import strip_armour

# Mocking the environment variable for testing
os.environ["SECRET_KEY"] = "test_secret_key"


# Mock "schedule_update_event" since we don't have an asyncio loop
@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


# An item signed with the retired scrypt scheme (sig/salt as an old printed
# URL would carry them). It must still parse, but its signature must fail.
OLD_SCRYPT_SIGNED_ARMOUR_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "armour",
    "data": {"num": 1},
    "collected_only_once": True,
    "collected_as_team": False,
    "sig": "db6a08d4acd56b636e532d7b1560f658",
    "salt": "test_salt",
}


SAMPLE_MEDPACK_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "medpack",
    "data": {},
    "collected_only_once": True,
    "collected_as_team": False,
}

SAMPLE_ARMOUR_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "armour",
    "data": {"num": 1},
    "collected_only_once": True,
    "collected_as_team": False,
}

SAMPLE_AMMO_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "ammo",
    "data": {"num": 1},
    "collected_only_once": True,
    "collected_as_team": False,
}

SAMPLE_WEAPON_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "weapon",
    "data": {"shot_damage": 3, "shot_timeout": 6.0},
    "collected_only_once": True,
    "collected_as_team": False,
}

SAMPLE_LV1_WEAPON_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "weapon",
    "data": {"shot_damage": 1, "shot_timeout": 6.0},
    "collected_only_once": True,
    "collected_as_team": False,
}

SAMPLE_INVALID_DATA = {
    "id": UUID("00000000-0000-0000-0000-000000000002"),
    "itype": "random",
    "data": {"num": 1},
    "collected_only_once": True,
    "collected_as_team": False,
}


@pytest.fixture
def valid_encoded_signed_lv1_armour():
    return ItemModel(**SAMPLE_ARMOUR_DATA).sign().to_base64()


@pytest.fixture
def valid_encoded_ammo():
    return ItemModel(**SAMPLE_AMMO_DATA).sign().to_base64()


@pytest.fixture
def valid_encoded_medpack():
    return ItemModel(**SAMPLE_MEDPACK_DATA).sign().to_base64()


def test_valid_encoded_armour(valid_encoded_signed_lv1_armour):
    print(valid_encoded_signed_lv1_armour)


def test_encoded_weapon():
    ItemModel(**SAMPLE_WEAPON_DATA)


def test_decoded_item_from_base64(valid_encoded_signed_lv1_armour):
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)

    print(f"Encoded: {valid_encoded_signed_lv1_armour}")
    print(f"Decoded: {item.model_dump()}")

    assert item.id == SAMPLE_ARMOUR_DATA["id"]
    assert item.itype == SAMPLE_ARMOUR_DATA["itype"]
    assert item.data == SAMPLE_ARMOUR_DATA["data"]
    assert item.sig == item.get_signature()
    assert item.salt is None


def test_decoded_item_to_base64(valid_encoded_signed_lv1_armour):
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)
    reencoded_item = item.to_base64()
    assert reencoded_item == valid_encoded_signed_lv1_armour


def test_valid_signature(valid_encoded_signed_lv1_armour):
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)
    assert item.validate_signature() is None


def test_signature_changes(valid_encoded_signed_lv1_armour):
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)
    assert item.validate_signature() is None
    item.itype = "armour1"
    assert item.validate_signature() is not None


def test_invalid_signature(valid_encoded_signed_lv1_armour):
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)
    item.sig = "invalid_signature"
    assert item.validate_signature() == "Signature mismatch"


def test_no_signature(valid_encoded_signed_lv1_armour):
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)
    item.sig = None
    assert item.validate_signature() == "Item not signed"


def test_can_sign(valid_encoded_signed_lv1_armour):
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)
    item.sig = None
    item.salt = None

    item.sign()

    assert item.validate_signature() == None


def test_signing_is_deterministic_and_uses_shared_helper():
    from backend.qr_signing import sign_payload

    item_a = ItemModel(**SAMPLE_ARMOUR_DATA).sign()
    item_b = ItemModel(**SAMPLE_ARMOUR_DATA).sign()

    # No salt: reprints yield identical URLs
    assert item_a.sig == item_b.sig
    assert item_a.salt is None

    assert item_a.sig == sign_payload(
        "item",
        item_a.id,
        item_a.itype,
        item_a.data_as_json(),
        item_a.collected_only_once,
        item_a.collected_as_team,
    )


# The exact signature the scheme produced before `batch` and `unlimited`
# existed, over SAMPLE_ARMOUR_DATA and the SECRET_KEY set at the top of this
# file. Every drop card, pub poster and WhatsApp link already in circulation
# was signed by that scheme, so this literal is the print freeze written down:
# if a change to the payload moves it, codes that are already out stop
# scanning.
FROZEN_ARMOUR_SIGNATURE = (
    "d06957d3a7b16c690b243fe57b3267e8c4434b688eed66be70ea00d9f9e361e2"
)


def test_a_payload_without_the_late_fields_signs_exactly_as_it_always_did():
    item = ItemModel(**SAMPLE_ARMOUR_DATA).sign()

    assert item.batch is None
    assert item.unlimited is False
    assert item.sig == FROZEN_ARMOUR_SIGNATURE


def test_an_already_printed_code_still_validates(valid_encoded_signed_lv1_armour):
    """The same thing from the scanner's end: a card carrying a signature made
    before the fields existed is still good."""
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)
    item.sig = FROZEN_ARMOUR_SIGNATURE

    assert item.validate_signature() is None


@pytest.mark.parametrize("field, value", [("batch", "sandbox"), ("unlimited", True)])
def test_setting_a_late_field_changes_the_signature(field, value):
    """They are left out of the message at their defaults, not ignored: a code
    that claims a batch it was not minted with must fail."""
    item = ItemModel(**SAMPLE_ARMOUR_DATA, **{field: value}).sign()

    assert item.sig != FROZEN_ARMOUR_SIGNATURE

    tampered = ItemModel(**SAMPLE_ARMOUR_DATA, **{field: value})
    tampered.sig = FROZEN_ARMOUR_SIGNATURE
    assert tampered.validate_signature() == "Signature mismatch"


def test_the_two_late_fields_cannot_be_confused_for_each_other():
    """They are named in the signed message, so a batch literally called
    "unlimited=True" is not the same payload as an unlimited code."""
    batched = ItemModel(**SAMPLE_ARMOUR_DATA, batch="unlimited=True").sign()
    unlimited = ItemModel(**SAMPLE_ARMOUR_DATA, unlimited=True).sign()

    assert batched.sig != unlimited.sig


def test_an_empty_batch_is_no_batch_at_all():
    """A cleared text field on the Printables page must not mint codes into a
    batch that cannot be named - and must sign as an unbatched code does."""
    item = ItemModel(**SAMPLE_ARMOUR_DATA, batch="").sign()

    assert item.batch is None
    assert item.sig == FROZEN_ARMOUR_SIGNATURE


def test_old_scrypt_signed_item_parses_but_fails_validation():
    encoded = ItemModel(**OLD_SCRYPT_SIGNED_ARMOUR_DATA).to_base64()

    # Old URLs still parse (the salt field is tolerated)...
    item = ItemModel.from_base64(encoded)
    assert item.salt == OLD_SCRYPT_SIGNED_ARMOUR_DATA["salt"]

    # ...but their scrypt signatures no longer validate
    assert item.validate_signature() == "Signature mismatch"


def test_old_scrypt_signed_item_cannot_be_collected(user_in_team):
    encoded = ItemModel(**OLD_SCRYPT_SIGNED_ARMOUR_DATA).to_base64()

    with pytest.raises(HTTPException, match="The scanned item is invalid"):
        UserInterface(user_in_team).collect_item(encoded)


def test_collect_item_valid(valid_encoded_signed_lv1_armour, user_in_team):
    # Level-1 armour is worth nothing to a player who still has their starting
    # armour (M1.2), and _handle_armour refuses it - so this test, which is
    # about collecting an item at all, hands the card to somebody who can use
    # it. See test_starting_armour_makes_a_level_1_card_useless below.
    strip_armour(user_in_team)
    UserInterface(user_in_team).collect_item(valid_encoded_signed_lv1_armour)


def test_collect_lv1_weapon_valid(user_in_team):
    item = ItemModel(**SAMPLE_LV1_WEAPON_DATA)
    item.sig = None
    item.salt = None

    item.sign()

    encoded_item = item.to_base64()

    UserInterface(user_in_team).collect_item(encoded_item)


def test_collect_item_invalid_signature(valid_encoded_signed_lv1_armour, user_in_team):
    item = ItemModel.from_base64(valid_encoded_signed_lv1_armour)
    item.sig = "invalid_signature"
    invalid_encoded_item = item.to_base64()

    with pytest.raises(HTTPException, match="The scanned item is invalid"):
        UserInterface(user_in_team).collect_item(invalid_encoded_item)


def test_collect_item_duplicate_item(valid_encoded_signed_lv1_armour, user_in_team):
    strip_armour(user_in_team)
    UserInterface(user_in_team).collect_item(valid_encoded_signed_lv1_armour)

    with pytest.raises(HTTPException, match="Item has already been collected"):
        UserInterface(user_in_team).collect_item(valid_encoded_signed_lv1_armour)


def test_can_generate_valid_item():
    assert ItemModel(**SAMPLE_AMMO_DATA).sign().validate_signature() is None


def test_can_encode_valid_item():
    ItemModel(**SAMPLE_AMMO_DATA).sign().to_base64()


def test_can_encode_and_decode_valid_item():
    encoded = ItemModel(**SAMPLE_AMMO_DATA).sign().to_base64()

    decoded = ItemModel.from_base64(encoded)

    assert isinstance(encoded, str)

    assert decoded.validate_signature() is None


def test_cannot_construct_invalid_item():
    with pytest.raises(pydantic.ValidationError):
        ItemModel(**SAMPLE_INVALID_DATA)


def test_cannot_collect_same_weapon_twice(user_in_team):
    valid_weapon = ItemModel(**SAMPLE_WEAPON_DATA).sign()

    UserInterface(user_in_team).collect_item(valid_weapon.to_base64())

    # Change ID
    valid_weapon.id = get_uuid()
    valid_weapon.sign()
    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_weapon.to_base64())


def test_collecting_armour_when_alive(valid_encoded_signed_lv1_armour, user_in_team):
    strip_armour(user_in_team)
    assert UserInterface(user_in_team).get_user_model().hit_points == 1
    UserInterface(user_in_team).collect_item(valid_encoded_signed_lv1_armour)
    assert UserInterface(user_in_team).get_user_model().hit_points == 2


def test_collecting_armour_when_dead(valid_encoded_signed_lv1_armour, user_in_team):
    strip_armour(user_in_team)
    UserInterface(user_in_team).hit(1)
    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_encoded_signed_lv1_armour)


def test_collecting_armour_doesnt_stack(user_in_team):
    armour_lv1 = ItemModel(**SAMPLE_ARMOUR_DATA).sign()

    strip_armour(user_in_team)
    assert UserInterface(user_in_team).get_user_model().hit_points == 1

    UserInterface(user_in_team).collect_item(armour_lv1.to_base64())
    assert UserInterface(user_in_team).get_user_model().hit_points == 2

    armour_lv1.id = get_uuid()
    armour_lv1.sign()
    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(armour_lv1.to_base64())
    assert UserInterface(user_in_team).get_user_model().hit_points == 2


def test_collecting_better_armour_works_and_worse_armour_fails(user_in_team):
    armour_lv1 = ItemModel(**SAMPLE_ARMOUR_DATA).sign()

    strip_armour(user_in_team)
    assert UserInterface(user_in_team).get_user_model().hit_points == 1

    UserInterface(user_in_team).collect_item(armour_lv1.to_base64())
    assert UserInterface(user_in_team).get_user_model().hit_points == 2

    armour_lv2 = armour_lv1.model_copy()
    armour_lv2.id = get_uuid()
    armour_lv2.data = ItemDataArmour(num=2).model_dump()
    armour_lv2.sign()

    UserInterface(user_in_team).collect_item(armour_lv2.to_base64())
    assert UserInterface(user_in_team).get_user_model().hit_points == 3

    armour_lv1_dup = armour_lv1.model_copy()
    armour_lv1_dup.id = get_uuid()
    armour_lv1_dup.data = ItemDataArmour(num=1).model_dump()
    armour_lv1_dup.sign()

    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(armour_lv1_dup.to_base64())
    assert UserInterface(user_in_team).get_user_model().hit_points == 3


def test_collecting_ammo_when_alive(valid_encoded_ammo, user_in_team):
    assert UserInterface(user_in_team).get_user_model().num_bullets == 0
    UserInterface(user_in_team).collect_item(valid_encoded_ammo)
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_collecting_revive_while_alive(valid_encoded_medpack, user_in_team):
    strip_armour(user_in_team)
    assert UserInterface(user_in_team).get_user_model().hit_points == 1
    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_encoded_medpack)
    assert UserInterface(user_in_team).get_user_model().hit_points == 1


def test_collecting_revive_while_knocked_out(valid_encoded_medpack, user_in_team):
    strip_armour(user_in_team)
    assert UserInterface(user_in_team).get_user_model().state == UserState.ALIVE
    UserInterface(user_in_team).hit(1)
    assert UserInterface(user_in_team).get_user_model().state == UserState.KNOCKED_OUT
    assert UserInterface(user_in_team).get_user_model().hit_points == 0
    UserInterface(user_in_team).collect_item(valid_encoded_medpack)
    assert UserInterface(user_in_team).get_user_model().state == UserState.ALIVE
    assert UserInterface(user_in_team).get_user_model().hit_points == 1


def test_collecting_revive_while_dead(db_session, valid_encoded_medpack, user_in_team):
    from backend.user_interface import TIME_KNOCKED_OUT

    strip_armour(user_in_team)
    assert UserInterface(user_in_team).get_user_model().state == UserState.ALIVE
    UserInterface(user_in_team).hit(1)

    assert UserInterface(user_in_team).get_user_model().state == UserState.KNOCKED_OUT

    # Set time of death to the timeout + 10s ago
    db_session.get(User, user_in_team).time_of_death -= TIME_KNOCKED_OUT + 10
    db_session.commit()

    assert UserInterface(user_in_team).get_user_model().state == UserState.DEAD
    assert UserInterface(user_in_team).get_user_model().hit_points == 0

    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_encoded_medpack)

    assert UserInterface(user_in_team).get_user_model().state == UserState.DEAD
    assert UserInterface(user_in_team).get_user_model().hit_points == 0


def test_user_collect_item(api_client, team_factory, db_session):
    user_id = api_client.get(
        "/api/my_id",
    ).json()

    UserInterface(user_id).join_team(team_factory())

    item_model = ItemModel(**SAMPLE_AMMO_DATA)
    item_model.data = {"num": 10}
    item_model.sign()
    valid_encoded_ammo = item_model.to_base64()

    assert UserInterface(user_id).get_user_model().num_bullets == 0

    r = api_client.post(
        "/api/collect_item",
        json={"data": valid_encoded_ammo},
    )

    print(r.json())
    assert r.is_success

    assert UserInterface(user_id).get_user_model().num_bullets == 10

    user = db_session.get(User, user_id)
    item = db_session.get(Item, item_model.id)

    assert user in item.users
    assert item in user.items


def test_different_users_collect_repeat_item(two_users_in_different_teams):
    user_a, user_b = two_users_in_different_teams

    repeatable_item = ItemModel(**SAMPLE_AMMO_DATA)
    repeatable_item.collected_only_once = False
    encoded_repeatable_item = repeatable_item.sign().to_base64()

    assert UserInterface(user_a).get_user_model().num_bullets == 0
    UserInterface(user_a).collect_item(encoded_repeatable_item)
    assert UserInterface(user_a).get_user_model().num_bullets == 1

    assert UserInterface(user_b).get_user_model().num_bullets == 0
    UserInterface(user_b).collect_item(encoded_repeatable_item)
    assert UserInterface(user_b).get_user_model().num_bullets == 1


def test_same_users_collect_repeat_item(two_users_in_different_teams):
    user_a, _ = two_users_in_different_teams

    repeatable_item = ItemModel(**SAMPLE_AMMO_DATA)
    repeatable_item.collected_only_once = False
    encoded_repeatable_item = repeatable_item.sign().to_base64()

    assert UserInterface(user_a).get_user_model().num_bullets == 0
    UserInterface(user_a).collect_item(encoded_repeatable_item)
    assert UserInterface(user_a).get_user_model().num_bullets == 1

    with pytest.raises(HTTPException):
        UserInterface(user_a).collect_item(encoded_repeatable_item)
    assert UserInterface(user_a).get_user_model().num_bullets == 1


def test_unlimited_item_can_be_collected_again_by_the_same_user(
    two_users_in_different_teams,
):
    """What a sandbox wall poster is. collected_only_once=False is not enough
    on its own - that lets the *next* player claim it, not the same one
    twice."""
    user_a, _ = two_users_in_different_teams

    poster = ItemModel(**SAMPLE_AMMO_DATA)
    poster.collected_only_once = False
    poster.unlimited = True
    encoded = poster.sign().to_base64()

    for expected in (1, 2, 3):
        UserInterface(user_a).collect_item(encoded)
        assert UserInterface(user_a).get_user_model().num_bullets == expected


def test_an_unlimited_item_is_recorded_once(db_session, two_users_in_different_teams):
    """Rescanning must not pile up association rows for the one item."""
    user_a, _ = two_users_in_different_teams

    poster = ItemModel(**SAMPLE_AMMO_DATA)
    poster.unlimited = True
    encoded = poster.sign().to_base64()

    UserInterface(user_a).collect_item(encoded)
    UserInterface(user_a).collect_item(encoded)

    items = db_session.query(User).filter_by(id=user_a).one().items
    assert [item.id for item in items] == [SAMPLE_AMMO_DATA["id"]]


def test_a_withdrawn_batch_cannot_be_collected(valid_encoded_ammo, user_in_team):
    """The only recall a printed code has: the card is still in somebody's
    hand, so the refusal has to come from the server."""
    batched = ItemModel(**SAMPLE_AMMO_DATA, batch="sandbox").sign().to_base64()

    AdminInterface().withdraw_batch("sandbox")

    with pytest.raises(HTTPException) as refusal:
        UserInterface(user_in_team).collect_item(batched)

    assert refusal.value.status_code == 403
    assert "withdrawn" in refusal.value.detail
    assert UserInterface(user_in_team).get_user_model().num_bullets == 0


def test_withdrawing_one_batch_leaves_the_others_alone(user_in_team):
    """The whole reason a batch exists: the sandbox closes at 16:00 and the
    game's own cards carry on."""
    sandbox = ItemModel(**SAMPLE_AMMO_DATA, batch="sandbox").sign().to_base64()
    game = (
        ItemModel(**{**SAMPLE_AMMO_DATA, "id": get_uuid()}, batch="game")
        .sign()
        .to_base64()
    )

    AdminInterface().withdraw_batch("sandbox")

    UserInterface(user_in_team).collect_item(game)
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1

    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(sandbox)


def test_a_code_minted_before_batches_existed_is_untouched(
    valid_encoded_ammo, user_in_team
):
    """An unbatched code has nothing to name it by, so no press can withdraw
    it - and a withdrawal must not catch it by accident either."""
    AdminInterface().withdraw_batch("sandbox")

    UserInterface(user_in_team).collect_item(valid_encoded_ammo)

    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_a_batch_can_be_allowed_again(user_in_team):
    """The undo for a press of the wrong button at 16:00."""
    batched = ItemModel(**SAMPLE_AMMO_DATA, batch="sandbox").sign().to_base64()

    AdminInterface().withdraw_batch("sandbox")
    AdminInterface().restore_batch("sandbox")

    UserInterface(user_in_team).collect_item(batched)

    assert UserInterface(user_in_team).get_user_model().num_bullets == 1
    assert AdminInterface().get_revoked_batches() == []


def test_withdrawing_twice_is_the_same_as_withdrawing_once():
    """An admin pressing it again means the same thing as pressing it once."""
    AdminInterface().withdraw_batch("sandbox")
    revoked = AdminInterface().withdraw_batch("sandbox")

    assert [entry["batch"] for entry in revoked] == ["sandbox"]


def test_a_batch_has_to_be_named_to_be_withdrawn():
    """A cleared text field would otherwise withdraw a batch called "", which
    is nothing - and mints no evidence that the press did nothing."""
    with pytest.raises(HTTPException) as refusal:
        AdminInterface().withdraw_batch("   ")

    assert refusal.value.status_code == 400


# Switching off one printed code. The batch above is the blunt instrument --
# the whole warm-up room at once -- and these are the scalpel: a card scanned
# back in by an admin, then turned off on its own.


def test_a_code_nobody_has_scanned_is_collectable(valid_encoded_ammo, user_in_team):
    """The default has to be "on": a code is an HMAC over its payload, so the
    server cannot enumerate what was printed and absence cannot mean no."""
    assert AdminInterface().get_known_codes() == []

    UserInterface(user_in_team).collect_item(valid_encoded_ammo)

    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_registering_a_code_says_what_it_is(valid_encoded_ammo):
    """The list is read on a phone by somebody holding a box of cards, so it
    has to say what a code hands out rather than just its id."""
    result = AdminInterface().register_code(valid_encoded_ammo)

    assert result["new"] is True
    assert result["code"]["description"] == "1 bullet"
    assert result["code"]["enabled"] is True
    assert [code["id"] for code in result["codes"]] == [str(SAMPLE_AMMO_DATA["id"])]


def test_registering_a_code_does_not_switch_it_off(valid_encoded_ammo, user_in_team):
    """Scanning a card onto the list is how you find it, not how you kill it -
    an admin checking what a card is must not disable it by looking."""
    AdminInterface().register_code(valid_encoded_ammo)

    UserInterface(user_in_team).collect_item(valid_encoded_ammo)

    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_a_switched_off_code_cannot_be_collected(valid_encoded_ammo, user_in_team):
    """The point of the whole feature: an infinite poster taken off the wall
    of the warm-up room without withdrawing the rest of the room."""
    AdminInterface().register_code(valid_encoded_ammo)
    AdminInterface().set_code_enabled(SAMPLE_AMMO_DATA["id"], False)

    with pytest.raises(HTTPException) as refusal:
        UserInterface(user_in_team).collect_item(valid_encoded_ammo)

    assert refusal.value.status_code == 403
    assert "switched off" in refusal.value.detail
    assert UserInterface(user_in_team).get_user_model().num_bullets == 0


def test_a_switched_off_code_can_be_switched_back_on(valid_encoded_ammo, user_in_team):
    AdminInterface().register_code(valid_encoded_ammo)
    AdminInterface().set_code_enabled(SAMPLE_AMMO_DATA["id"], False)
    codes = AdminInterface().set_code_enabled(SAMPLE_AMMO_DATA["id"], True)

    assert [code["enabled"] for code in codes] == [True]

    UserInterface(user_in_team).collect_item(valid_encoded_ammo)
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_switching_off_one_code_leaves_its_batch_alone(user_in_team):
    """A sandbox poster taken down mid-hour while the rest of the room runs."""
    switched_off = ItemModel(**SAMPLE_AMMO_DATA, batch="sandbox").sign().to_base64()
    sibling = (
        ItemModel(**{**SAMPLE_AMMO_DATA, "id": get_uuid()}, batch="sandbox")
        .sign()
        .to_base64()
    )

    AdminInterface().register_code(switched_off)
    AdminInterface().set_code_enabled(SAMPLE_AMMO_DATA["id"], False)

    UserInterface(user_in_team).collect_item(sibling)
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1

    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(switched_off)


def test_rescanning_a_code_keeps_the_decision_that_was_made_about_it(
    valid_encoded_ammo,
):
    """Scanning a card again is how an admin checks it is already handled, so
    the second scan must not undo the first one's switch."""
    AdminInterface().register_code(valid_encoded_ammo)
    AdminInterface().set_code_enabled(SAMPLE_AMMO_DATA["id"], False)

    result = AdminInterface().register_code(valid_encoded_ammo)

    assert result["new"] is False
    assert result["code"]["enabled"] is False
    assert len(result["codes"]) == 1


def test_an_unsigned_code_cannot_be_registered(user_in_team):
    """A switch that turns off nothing is worse than no switch: an unsigned
    code is refused at collection anyway, so it has no business on the list."""
    forged = ItemModel(**SAMPLE_AMMO_DATA).to_base64()

    with pytest.raises(HTTPException) as refusal:
        AdminInterface().register_code(forged)

    assert refusal.value.status_code == 403
    assert AdminInterface().get_known_codes() == []


def test_forgetting_a_code_puts_it_back_to_collectable(
    valid_encoded_ammo, user_in_team
):
    """Taking a row off the list means "back to the default", and the default
    is on - which is the way out of a card scanned in by mistake."""
    AdminInterface().register_code(valid_encoded_ammo)
    AdminInterface().set_code_enabled(SAMPLE_AMMO_DATA["id"], False)

    assert AdminInterface().forget_code(SAMPLE_AMMO_DATA["id"]) == []

    UserInterface(user_in_team).collect_item(valid_encoded_ammo)
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_a_code_nobody_has_scanned_cannot_be_switched_off():
    """There is nothing to switch: the server has never seen the payload, so
    it has no idea what an id names."""
    with pytest.raises(HTTPException) as refusal:
        AdminInterface().set_code_enabled(get_uuid(), False)

    assert refusal.value.status_code == 404


def test_collect_team_item(two_users_in_different_teams, user_factory):
    user_a1, user_b = two_users_in_different_teams

    user_a2 = user_factory()
    UserInterface(user_a2).join_team(UserInterface(user_a1).get_team_model().id)

    team_item = ItemModel(**SAMPLE_AMMO_DATA)
    team_item.collected_as_team = True
    team_item.collected_only_once = True
    encoded_team_item = team_item.sign().to_base64()

    assert UserInterface(user_a1).get_user_model().num_bullets == 0
    assert UserInterface(user_a2).get_user_model().num_bullets == 0
    UserInterface(user_a1).collect_item(encoded_team_item)
    assert UserInterface(user_a1).get_user_model().num_bullets == 1
    assert UserInterface(user_a2).get_user_model().num_bullets == 1

    with pytest.raises(HTTPException):
        UserInterface(user_a2).collect_item(encoded_team_item)
        UserInterface(user_b).collect_item(encoded_team_item)


def test_collect_team_item_twice(two_users_in_different_teams, user_factory):
    user_a1, user_b = two_users_in_different_teams

    user_a2 = user_factory()
    UserInterface(user_a2).join_team(UserInterface(user_a1).get_team_model().id)

    team_item = ItemModel(**SAMPLE_AMMO_DATA)
    team_item.collected_as_team = True
    team_item.collected_only_once = False
    encoded_team_repeatable_item = team_item.sign().to_base64()

    assert UserInterface(user_a1).get_user_model().num_bullets == 0
    assert UserInterface(user_a2).get_user_model().num_bullets == 0
    assert UserInterface(user_b).get_user_model().num_bullets == 0

    UserInterface(user_a1).collect_item(encoded_team_repeatable_item)
    UserInterface(user_b).collect_item(encoded_team_repeatable_item)

    assert UserInterface(user_a1).get_user_model().num_bullets == 1
    assert UserInterface(user_a2).get_user_model().num_bullets == 1
    assert UserInterface(user_b).get_user_model().num_bullets == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://example.com",
        "https://example.com/subpath",
        "https://example.com/subpath/subpath2",
        "https://10.0.0.1/",
    ],
)
def test_user_collect_url(api_client, team_factory, url):
    from backend.utils import add_params_to_url

    user_id = api_client.get(
        "/api/my_id",
    ).json()

    UserInterface(user_id).join_team(team_factory())

    item = ItemModel(**SAMPLE_AMMO_DATA)
    item.data = {"num": 10}
    item.sign()
    valid_encoded_ammo = item.to_base64()

    sample_url = add_params_to_url(url, {"d": valid_encoded_ammo})

    assert UserInterface(user_id).get_user_model().num_bullets == 0

    r = api_client.post(
        "/api/collect_item",
        json={"data": sample_url},
    )

    print(r.json())
    assert r.is_success

    assert UserInterface(user_id).get_user_model().num_bullets == 10


def test_collect_item_announces_message(valid_encoded_ammo, user_in_team, mocker):
    mock_send_ticker_message = mocker.patch(
        "backend.ticker_message_dispatcher.send_ticker_message"
    )

    UserInterface(user_in_team).collect_item(valid_encoded_ammo)

    mock_send_ticker_message.assert_called_once()
    assert (
        mock_send_ticker_message.call_args[0][0]
        is TickerMessageType.USER_COLLECTED_AMMO
    )


def test_radar_and_circle_warning_carry_a_duration():
    """M0.3 freezes what these two cards *say*; M6 writes the handlers. The
    payload has to be right now, because the cards are printed now."""
    radar = ItemModel(**{**SAMPLE_AMMO_DATA, "itype": "radar", "data": {}})
    warning = ItemModel(
        **{**SAMPLE_AMMO_DATA, "itype": "circle_warning", "data": {"minutes": 20}}
    )

    assert radar.data == {"minutes": 5}
    assert warning.data == {"minutes": 20}


def _radar_card(minutes=None):
    data = {} if minutes is None else {"minutes": minutes}
    return ItemModel(
        **{**SAMPLE_AMMO_DATA, "id": get_uuid(), "itype": "radar", "data": data}
    ).sign()


def test_radar_card_starts_the_radar(user_in_team):
    before = time.time()
    UserInterface(user_in_team).collect_item(_radar_card(minutes=5).to_base64())

    radar_until = UserInterface(user_in_team).get_user_model().radar_until

    assert before + 5 * 60 <= radar_until <= time.time() + 5 * 60


def test_a_second_radar_card_is_refused_while_the_first_runs(user_in_team, db_session):
    """Refusing keeps the card: the scan rolls back, so no Item row is written
    and the player can use it once the first one has run out."""
    UserInterface(user_in_team).collect_item(_radar_card(minutes=5).to_base64())

    second = _radar_card(minutes=5)
    with pytest.raises(HTTPException) as refusal:
        UserInterface(user_in_team).collect_item(second.to_base64())
    assert refusal.value.status_code == 403

    # Wind the first radar into the past, as five minutes of play would
    db_session.query(User).filter_by(id=user_in_team).update(
        {"radar_until": time.time() - 1}
    )
    db_session.commit()

    UserInterface(user_in_team).collect_item(second.to_base64())
    assert UserInterface(user_in_team).get_user_model().radar_until > time.time()


def test_radar_is_refused_until_a_card_is_scanned(user_in_team):
    with pytest.raises(HTTPException) as refusal:
        UserInterface(user_in_team).get_radar()

    assert refusal.value.status_code == 403


def test_radar_shows_everybody_else_and_how_old_their_fix_is(
    two_users_in_different_teams,
):
    me, them = two_users_in_different_teams

    UserInterface(me).set_location(51.0, -1.0, accuracy=8.0)
    UserInterface(them).set_location(51.1, -1.1, accuracy=12.0)

    UserInterface(me).collect_item(_radar_card(minutes=5).to_base64())

    contacts = UserInterface(me).get_radar()

    assert len(contacts) == 1
    (contact,) = contacts
    assert contact["lat"] == 51.1
    assert contact["long"] == -1.1
    assert contact["accuracy"] == 12.0
    assert contact["state"] == UserState.ALIVE
    # Last seen, never live: every row says how stale it is
    assert 0 <= contact["seconds_ago"] < 60


def test_radar_leaves_out_anybody_who_has_never_reported_a_fix(
    two_users_in_different_teams,
):
    me, _them = two_users_in_different_teams

    UserInterface(me).collect_item(_radar_card(minutes=5).to_base64())

    assert UserInterface(me).get_radar() == []


def _circle_warning_card(minutes=None):
    data = {} if minutes is None else {"minutes": minutes}
    return ItemModel(
        **{
            **SAMPLE_AMMO_DATA,
            "id": get_uuid(),
            "itype": "circle_warning",
            "data": data,
        }
    ).sign()


def test_a_circle_warning_card_shows_the_next_circle_early(user_in_team):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)

    # Placing it tells nobody: it is not public until the admin cues it
    assert UserInterface(user_in_team).get_circles()["next_circle_lat"] is None

    UserInterface(user_in_team).collect_item(
        _circle_warning_card(minutes=10).to_base64()
    )

    circles = UserInterface(user_in_team).get_circles()
    assert circles["next_circle_lat"] == 51.5
    assert circles["next_circle_radius"] == 0.42


def test_a_second_circle_warning_is_refused_while_the_first_runs(user_in_team):
    UserInterface(user_in_team).collect_item(
        _circle_warning_card(minutes=10).to_base64()
    )

    with pytest.raises(HTTPException) as refusal:
        UserInterface(user_in_team).collect_item(
            _circle_warning_card(minutes=10).to_base64()
        )

    assert refusal.value.status_code == 403


def test_an_expired_circle_warning_stops_showing_the_next_circle(
    user_in_team, db_session
):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)
    UserInterface(user_in_team).collect_item(
        _circle_warning_card(minutes=10).to_base64()
    )

    db_session.query(User).filter_by(id=user_in_team).update(
        {"circle_warning_until": time.time() - 1}
    )
    db_session.commit()

    assert UserInterface(user_in_team).get_circles()["next_circle_lat"] is None


def test_an_expired_radar_is_refused_like_no_radar_at_all(user_in_team, db_session):
    UserInterface(user_in_team).collect_item(_radar_card(minutes=5).to_base64())

    db_session.query(User).filter_by(id=user_in_team).update(
        {"radar_until": time.time() - 1}
    )
    db_session.commit()

    with pytest.raises(HTTPException) as refusal:
        UserInterface(user_in_team).get_radar()

    assert refusal.value.status_code == 403


def test_all_items_handled():
    from backend.item_actions import _ACTIONS
    from backend.model import ItemType

    for itype in ItemType:
        assert (itype, False) in _ACTIONS

    # Only check collected_as_team for ammo
    assert (ItemType.AMMO, True) in _ACTIONS


def test_all_items_validated():
    from backend.items import ITEM_TYPE_VALIDATORS
    from backend.model import ItemType

    for itype in ItemType:
        assert itype in ITEM_TYPE_VALIDATORS


def test_basic_weapon_is_the_pewster():
    """model.BASIC_WEAPON is what the 16:00 reset hands out, and it has to be
    a weapon the lookup can name - the two are written as separate literals
    (the lookup's are read by react-ui/src/weapons.test.js), so nothing else
    catches them drifting apart."""
    from backend.item_actions import WEAPON_NAME_LOOKUP
    from backend.model import BASIC_WEAPON
    from backend.model import DEFAULT_SHOT_TIMEOUT

    assert WEAPON_NAME_LOOKUP[BASIC_WEAPON] == "Pewster"
    assert BASIC_WEAPON == (1, DEFAULT_SHOT_TIMEOUT)

    # A fresh sign-up holds no weapon, at the same standard delay.
    from backend.user_interface import DEFAULT_SHOT_DAMAGE

    assert (
        WEAPON_NAME_LOOKUP[(DEFAULT_SHOT_DAMAGE, DEFAULT_SHOT_TIMEOUT)] == "No weapon"
    )


def test_starting_armour_makes_a_level_1_card_useless(
    valid_encoded_signed_lv1_armour, user_in_team
):
    """A consequence of M1.2 worth pinning down, because it decides what is
    worth printing: a player starts on STARTING_HIT_POINTS, which *is* level 1
    armour, so a level-1 armour card does nothing for anybody who has not been
    hit yet. Everything in the drop and sandbox sets is level 2
    (`printables.SANDBOX_CARDS`), which still works.
    """
    assert (
        UserInterface(user_in_team).get_user_model().hit_points == STARTING_HIT_POINTS
    )

    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_encoded_signed_lv1_armour)

    # ...and level 2 is still worth picking up.
    armour_lv2 = ItemModel(**SAMPLE_ARMOUR_DATA)
    armour_lv2.data = ItemDataArmour(num=2).model_dump()
    armour_lv2.sign()

    UserInterface(user_in_team).collect_item(armour_lv2.to_base64())
    assert UserInterface(user_in_team).get_user_model().hit_points == 3


# Reading a code without spending it (react-ui/src/AdminScanCode.js). The
# other two scanners in the app both change something - one collects the item,
# one writes a KnownCode row - so the whole point of these is that nothing
# moves.


def test_identifying_an_item_code_says_what_it_hands_out(
    db_session, valid_encoded_ammo
):
    identified = AdminInterface().identify_code(valid_encoded_ammo)

    assert identified["kind"] == "item"
    assert identified["headline"] == "1 bullet"
    assert identified["verdict"]["tone"] == "good"


def test_identifying_a_code_collects_nothing(valid_encoded_ammo, user_in_team):
    """The refusal this page exists to avoid: an admin working out what a card
    is must not spend it, and must not put it on the switch-off list either."""
    AdminInterface().identify_code(valid_encoded_ammo)

    assert UserInterface(user_in_team).get_user_model().num_bullets == 0
    assert AdminInterface().get_known_codes() == []

    UserInterface(user_in_team).collect_item(valid_encoded_ammo)
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_a_spent_code_identifies_as_spent(valid_encoded_ammo, user_in_team):
    """What the page is pulled out of a pocket for: this card is on the floor
    because somebody already had it."""
    UserInterface(user_in_team).collect_item(valid_encoded_ammo)

    identified = AdminInterface().identify_code(valid_encoded_ammo)

    assert identified["verdict"]["tone"] == "bad"
    assert "already collected" in identified["verdict"]["text"]


def test_a_withdrawn_batch_identifies_as_dead(user_in_team):
    card = ItemModel(**SAMPLE_AMMO_DATA, batch="sandbox").sign().to_base64()
    AdminInterface().withdraw_batch("sandbox")

    identified = AdminInterface().identify_code(card)

    assert identified["verdict"]["tone"] == "bad"
    assert "withdrawn" in identified["verdict"]["text"]


def test_a_switched_off_code_identifies_as_dead(db_session, valid_encoded_ammo):
    AdminInterface().register_code(valid_encoded_ammo)
    AdminInterface().set_code_enabled(SAMPLE_AMMO_DATA["id"], False)

    identified = AdminInterface().identify_code(valid_encoded_ammo)

    assert identified["verdict"]["tone"] == "bad"
    assert "switched off" in identified["verdict"]["text"]


def test_an_unsigned_code_identifies_as_forged(db_session):
    """Unlike registering one, identifying it answers rather than refusing:
    "that is not ours" is exactly what the admin is asking."""
    identified = AdminInterface().identify_code(
        ItemModel(**SAMPLE_AMMO_DATA).to_base64()
    )

    assert identified["kind"] == "item"
    assert identified["verdict"]["tone"] == "bad"


def test_identifying_something_that_is_not_a_code_at_all(db_session):
    identified = AdminInterface().identify_code("https://example.com/lunch")

    assert identified["kind"] == "unknown"
    assert identified["verdict"]["tone"] == "bad"
