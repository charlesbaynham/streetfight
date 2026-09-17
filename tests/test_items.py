import os
from uuid import UUID
from uuid import uuid4 as get_uuid

import pydantic
import pytest
from fastapi.exceptions import HTTPException

from backend.admin_interface import AdminInterface
from backend.items import ItemDataArmour
from backend.items import ItemModel
from backend.model import Item
from backend.model import ItemType
from backend.model import User
from backend.model import UserState
from backend.ticker_message_dispatcher import TickerMessageType
from backend.user_interface import UserInterface

# Mocking the environment variable for testing
os.environ["SECRET_KEY"] = "test_secret_key"

# The item types whose cards are printed before their handlers are written
# (M0.3 freezes the encoding; M6 writes the effects). Scanning one is a 403
# until then, which is what an unmapped type has always done.
AWAITING_HANDLERS = {ItemType.RADAR, ItemType.CIRCLE_WARNING}


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
    assert UserInterface(user_in_team).get_user_model().hit_points == 1
    UserInterface(user_in_team).collect_item(valid_encoded_signed_lv1_armour)
    assert UserInterface(user_in_team).get_user_model().hit_points == 2


def test_collecting_armour_when_dead(valid_encoded_signed_lv1_armour, user_in_team):
    UserInterface(user_in_team).hit(1)
    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_encoded_signed_lv1_armour)


def test_collecting_armour_doesnt_stack(user_in_team):
    armour_lv1 = ItemModel(**SAMPLE_ARMOUR_DATA).sign()

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
    assert UserInterface(user_in_team).get_user_model().hit_points == 1
    with pytest.raises(HTTPException):
        UserInterface(user_in_team).collect_item(valid_encoded_medpack)
    assert UserInterface(user_in_team).get_user_model().hit_points == 1


def test_collecting_revive_while_knocked_out(valid_encoded_medpack, user_in_team):
    assert UserInterface(user_in_team).get_user_model().state == UserState.ALIVE
    UserInterface(user_in_team).hit(1)
    assert UserInterface(user_in_team).get_user_model().state == UserState.KNOCKED_OUT
    assert UserInterface(user_in_team).get_user_model().hit_points == 0
    UserInterface(user_in_team).collect_item(valid_encoded_medpack)
    assert UserInterface(user_in_team).get_user_model().state == UserState.ALIVE
    assert UserInterface(user_in_team).get_user_model().hit_points == 1


def test_collecting_revive_while_dead(db_session, valid_encoded_medpack, user_in_team):
    from backend.user_interface import TIME_KNOCKED_OUT

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


def test_an_item_with_no_handler_yet_is_refused_rather_than_crashing(user_in_team):
    """Until M6 lands, scanning one of the new cards is a 403 - the same
    answer an unmapped type has always given."""
    radar = ItemModel(**{**SAMPLE_AMMO_DATA, "itype": "radar", "data": {}}).sign()

    with pytest.raises(HTTPException) as refusal:
        UserInterface(user_in_team).collect_item(radar.to_base64())

    assert refusal.value.status_code == 403


def test_all_items_handled():
    from backend.item_actions import _ACTIONS
    from backend.model import ItemType

    for itype in ItemType:
        if itype in AWAITING_HANDLERS:
            continue
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
