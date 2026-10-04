"""A shot of a QR code is a player who meant to scan it, and is refunded
before any vision call is spent on it."""

import base64
from io import BytesIO

import pytest
from PIL import Image

from backend import ai_shot_review
from backend import shot_qr
from backend.admin_interface import AdminInterface
from backend.generate_pub_pages import make_qr
from backend.image_processing import load_image
from backend.items import ItemModel
from backend.join_codes import make_game_join_url
from backend.model import Shot
from backend.model import User
from backend.user_interface import UserInterface
from backend.vision_client import FakeVisionClient
from tests.shared_fixtures import NO_FIRE_DELAY


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def photo_with_qr(test_image_string, url, size=400):
    """The sample shot photograph with ``url`` as a printed card held up in
    it: the QR on white paper, quiet zone and all."""
    image, _ = load_image(test_image_string)
    image = image.convert("RGB")
    card = Image.new("RGB", (size + 80, size + 80), "white")
    card.paste(make_qr(url, size), (40, 40))
    image.paste(card, (20, 20))
    out = BytesIO()
    image.save(out, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def an_item_url():
    return AdminInterface().make_new_item("ammo", {"num": 5})


def a_forged_item_url():
    url = an_item_url()
    item = ItemModel.from_base64(url)
    item.data = {"num": 500}
    return f"https://example.com/?d={item.to_base64()}"


def fire(user_id, image):
    ui = UserInterface(user_id)
    ui.award_ammo(1)
    ui.set_weapon_data(1, NO_FIRE_DELAY)
    ui.submit_shot(image)
    return AdminInterface().get_shots_ids()[0]


def bullets(db_session, user_id):
    db_session.expire_all()
    return db_session.query(User).filter_by(id=user_id).one().num_bullets


def test_a_printed_item_code_is_found(db_session, test_image_string):
    url = an_item_url()
    assert shot_qr.streetfight_code_in(photo_with_qr(test_image_string, url)) == url


def test_a_join_code_is_found(db_session, one_game, test_image_string):
    url = make_game_join_url(one_game)
    assert shot_qr.streetfight_code_in(photo_with_qr(test_image_string, url)) == url


def test_the_refund_note_says_what_the_code_was(db_session, one_game):
    note = shot_qr.refund_note(an_item_url())
    assert "ammo" in note and '"num": 5' in note
    assert "join code" in shot_qr.refund_note(make_game_join_url(one_game))


def test_somebody_elses_qr_code_is_not_ours(test_image_string):
    image = photo_with_qr(test_image_string, "https://example.com/pub-wifi")
    assert shot_qr.streetfight_code_in(image) is None


def test_a_forged_code_is_not_ours(db_session, test_image_string):
    image = photo_with_qr(test_image_string, a_forged_item_url())
    assert shot_qr.streetfight_code_in(image) is None


def test_a_photo_with_no_qr_code_has_none(test_image_string):
    assert shot_qr.streetfight_code_in(test_image_string) is None


def test_an_undecodable_photo_has_none():
    assert shot_qr.streetfight_code_in("data:,") is None


@pytest.mark.asyncio
async def test_a_shot_of_a_game_code_is_refunded_without_asking_the_model(
    db_session, user_in_team, test_image_string
):
    shot_id = fire(user_in_team, photo_with_qr(test_image_string, an_item_url()))
    assert bullets(db_session, user_in_team) == 0
    client = FakeVisionClient(reply={})

    await ai_shot_review.review_shot(shot_id, client)

    assert client.images_sent == []
    shot = db_session.query(Shot).filter_by(id=shot_id).one()
    assert shot.checked
    assert shot.result == "refunded"
    assert bullets(db_session, user_in_team) == 1
    # The admin can see why in the queue, under the photograph
    assert "QR code" in AdminInterface().get_shot_notes(shot_id)


@pytest.mark.asyncio
async def test_a_shot_of_somebody_elses_qr_code_is_reviewed_as_normal(
    db_session, user_in_team, test_image_string
):
    image = photo_with_qr(test_image_string, "https://example.com/pub-wifi")
    shot_id = fire(user_in_team, image)
    client = FakeVisionClient(reply={"shot_hit_a_person": False, "reasoning": "x"})

    await ai_shot_review.review_shot(shot_id, client)

    assert client.images_sent
    assert db_session.query(Shot).filter_by(id=shot_id).one().result != "refunded"


@pytest.mark.asyncio
async def test_a_shot_already_ruled_on_is_left_alone(
    db_session, user_in_team, test_image_string
):
    shot_id = fire(user_in_team, photo_with_qr(test_image_string, an_item_url()))
    AdminInterface().mark_shot_missed(shot_id)

    await ai_shot_review.review_shot(shot_id, FakeVisionClient(reply={}))

    assert db_session.query(Shot).filter_by(id=shot_id).one().result == "miss"
    assert bullets(db_session, user_in_team) == 0
