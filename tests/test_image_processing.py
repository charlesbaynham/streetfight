from pathlib import Path

import pytest

from backend.image_processing import draw_aim_marker
from backend.image_processing import draw_cross_on_image
from backend.image_processing import load_image
from backend.image_processing import prepare_for_vision


@pytest.fixture
def test_image_string():
    return Path(__file__, "../sample_base64_image.txt").resolve().read_text()


def test_image_loading():
    test_image_string = (
        Path(__file__, "../sample_base64_image.txt").resolve().read_text()
    )

    load_image(test_image_string)


def test_image_processsing():
    test_image_string = (
        Path(__file__, "../sample_base64_image.txt").resolve().read_text()
    )
    draw_cross_on_image(test_image_string)


def test_image_processsing_save_output():
    test_image_string = (
        Path(__file__, "../sample_base64_image.txt").resolve().read_text()
    )

    image_out = draw_cross_on_image(test_image_string)
    image, _ = load_image(image_out)
    image.save(Path(__file__, "../../logs/test_output.png").resolve())


# -- preparing a shot for the vision model ----------------------------------


def test_aim_marker_keeps_the_image_the_same_size(test_image_string):
    original, _ = load_image(test_image_string)
    marked, _ = load_image(draw_aim_marker(test_image_string))

    assert marked.size == original.size


def test_aim_marker_does_not_duplicate_the_target(test_image_string):
    # draw_cross_on_image pastes a magnified copy of the centre into the corner;
    # the aim marker must not, or the model sees two of the same person.
    original, _ = load_image(test_image_string)
    marked, _ = load_image(draw_aim_marker(test_image_string))

    width, height = original.size
    corner = (0, 0, width // 4, height // 4)
    assert marked.crop(corner).tobytes() == original.crop(corner).tobytes()


def test_aim_marker_draws_something_in_the_middle(test_image_string):
    original, _ = load_image(test_image_string)
    marked, _ = load_image(draw_aim_marker(test_image_string))

    width, height = original.size
    middle = (width // 3, height // 3, 2 * width // 3, 2 * height // 3)
    assert marked.crop(middle).tobytes() != original.crop(middle).tobytes()


def test_prepare_for_vision_downsizes_large_images(test_image_string):
    prepared = prepare_for_vision(test_image_string, max_dimension=64)
    image, _ = load_image(prepared)

    assert max(image.size) == 64
    assert prepared.startswith("data:image/jpeg;base64,")


def test_prepare_for_vision_does_not_upscale(test_image_string):
    original, _ = load_image(test_image_string)
    image, _ = load_image(prepare_for_vision(test_image_string, max_dimension=100_000))

    assert image.size == original.size


def test_prepare_for_vision_shrinks_the_payload(test_image_string):
    prepared = prepare_for_vision(test_image_string, max_dimension=256)

    assert len(prepared) < len(test_image_string)


def test_prepare_for_vision_handles_transparency(test_image_string):
    # JPEG has no alpha channel, so an RGBA source must be converted, not crash
    import base64
    from io import BytesIO

    from PIL import Image

    rgba = Image.new("RGBA", (300, 200), (255, 0, 0, 128))
    buffer = BytesIO()
    rgba.save(buffer, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    image, _ = load_image(prepare_for_vision(data_url, max_dimension=150))
    assert image.mode == "RGB"
    assert max(image.size) == 150
