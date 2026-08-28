from pathlib import Path

import pytest
from PIL import ImageChops
from PIL import ImageStat

from backend.image_processing import annotate_image_with_stats
from backend.image_processing import draw_aim_marker
from backend.image_processing import draw_cross_on_image
from backend.image_processing import load_image
from backend.image_processing import prepare_for_vision
from backend.image_processing import zoom_image


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


def as_jpeg(base64_image, quality=85):
    """The same picture, encoded the way a phone camera uploads it."""
    import base64
    from io import BytesIO

    image, _ = load_image(base64_image)
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_markup_declares_the_format_it_encoded(test_image_string):
    # The prefix used to be carried over from the input while the payload was
    # re-encoded, so an uploaded JPEG came back as PNG bytes still labelled
    # image/jpeg.
    import base64

    for marked_up in (
        draw_cross_on_image(test_image_string),
        annotate_image_with_stats(test_image_string, {"Result": "Unchecked"}),
        draw_aim_marker(test_image_string),
    ):
        prefix, payload = marked_up.split(",", 1)

        assert prefix == "data:image/jpeg;base64"
        assert base64.b64decode(payload[:8]).startswith(b"\xff\xd8")


def test_markup_does_not_inflate_a_photo(test_image_string):
    # draw_cross_on_image runs on every admin queue fetch, so what it returns is
    # what the admin waits to download. Re-encoding to PNG made a phone JPEG
    # roughly five times bigger.
    photo = as_jpeg(test_image_string)

    assert len(draw_cross_on_image(photo)) < 1.5 * len(photo)


def test_annotating_stats_does_not_crash_on_current_pillow(test_image_string):
    # The stats box is anchored to the bottom edge, and Pillow >= 10 rejects a
    # rectangle given bottom corner first.
    annotate_image_with_stats(test_image_string, {"Shooter": "someone", "Damage": 1})


# -- preparing a shot for the vision model ----------------------------------


def test_aim_marker_keeps_the_image_the_same_size(test_image_string):
    original, _ = load_image(test_image_string)
    marked, _ = load_image(draw_aim_marker(test_image_string))

    assert marked.size == original.size


def test_aim_marker_does_not_duplicate_the_target(test_image_string):
    # draw_cross_on_image pastes a magnified copy of the centre into the corner;
    # the aim marker must not, or the model sees two of the same person.
    # Compared by mean difference rather than exactly, because the re-encode is
    # lossy: JPEG noise scores under 1 here, a pasted crop scores over 100.
    original, _ = load_image(test_image_string)
    marked, _ = load_image(draw_aim_marker(test_image_string))

    width, height = original.size
    corner = (0, 0, width // 4, height // 4)
    difference = ImageChops.difference(
        marked.crop(corner).convert("RGB"), original.crop(corner).convert("RGB")
    )

    assert max(ImageStat.Stat(difference).mean) < 5


def test_aim_marker_draws_something_in_the_middle(test_image_string):
    original, _ = load_image(test_image_string)
    marked, _ = load_image(draw_aim_marker(test_image_string))

    width, height = original.size
    middle = (width // 3, height // 3, 2 * width // 3, 2 * height // 3)
    assert marked.crop(middle).tobytes() != original.crop(middle).tobytes()


def test_aim_marker_lines_reach_the_edges_of_the_frame():
    # The guide lines must span the whole photo, not just a short arm near the
    # centre, so they stay visible after downsizing even far from the aim
    # point.
    import base64
    from io import BytesIO

    from PIL import Image

    flat = Image.new("RGB", (800, 600), (128, 128, 128))
    buffer = BytesIO()
    flat.save(buffer, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    marked, _ = load_image(draw_aim_marker(data_url))
    width, height = marked.size
    centre_x, centre_y = width // 2, height // 2

    near_left_edge = marked.getpixel((5, centre_y))
    assert near_left_edge[0] > near_left_edge[1] + 20
    assert near_left_edge[0] > near_left_edge[2] + 20

    near_top_edge = marked.getpixel((centre_x, 5))
    assert near_top_edge[0] > near_top_edge[1] + 20
    assert near_top_edge[0] > near_top_edge[2] + 20


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


# -- the zoom the model can ask for -----------------------------------------


def detailed_image(width=2048, height=1536, stripe=2):
    """An image with fine detail in the middle, too fine to survive a downsize."""
    import base64
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (width, height), (128, 128, 128))
    pixels = image.load()
    # Thin vertical stripes across the central quarter, which is what a zoom
    # keeps and a whole-frame downsize smears into flat grey.
    for x in range(width * 3 // 8, width * 5 // 8):
        for y in range(height * 3 // 8, height * 5 // 8):
            pixels[x, y] = (255, 255, 255) if (x // stripe) % 2 else (0, 0, 0)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_zoom_crops_the_centre_and_scales_back_up():
    zoomed, _ = load_image(zoom_image(detailed_image(2048, 1536), max_dimension=1024))

    # 2048/8 = 256 wide before rescaling, then scaled so the longest side is 1024
    assert max(zoomed.size) == 1024
    # Aspect ratio is preserved by the crop
    assert zoomed.size[0] / zoomed.size[1] == pytest.approx(2048 / 1536, rel=0.01)


def test_zoom_keeps_detail_that_the_plain_downsize_loses():
    original = detailed_image()

    plain, _ = load_image(prepare_for_vision(original, max_dimension=1024))
    zoomed, _ = load_image(zoom_image(original, max_dimension=1024))

    # Contrast across a band near the middle: the stripes survive the zoom but
    # are averaged away by the whole-frame downsize. Offset from the exact
    # centre row, which the aim marker's full-width horizontal line now paints
    # solid, obscuring the stripe detail that row would otherwise show.
    def middle_contrast(image):
        grey = image.convert("L")
        row = grey.height // 2 - 20
        values = [grey.getpixel((x, row)) for x in range(grey.width)]
        return max(values) - min(values)

    assert middle_contrast(zoomed) > middle_contrast(plain)


def test_zoom_keeps_the_centre_not_some_other_part_of_the_frame():
    # The detail sits exactly in the central quarter, which is what a factor-4
    # crop keeps, so the zoomed frame should be striped right out to its edges.
    zoomed, _ = load_image(zoom_image(detailed_image(), max_dimension=1024))
    grey = zoomed.convert("L")

    # A row offset from centre, clear of the aim marker's horizontal line.
    row = grey.height // 2 - 20
    near_left = [grey.getpixel((x, row)) for x in range(10, 60)]

    assert max(near_left) - min(near_left) > 100


def test_zoom_marks_the_aim_point():
    import base64
    from io import BytesIO

    from PIL import Image

    # A flat grey frame, so anything that is not grey afterwards is the marker
    flat = Image.new("RGB", (800, 600), (128, 128, 128))
    buffer = BytesIO()
    flat.save(buffer, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    zoomed, _ = load_image(zoom_image(data_url, max_dimension=400))
    width, height = zoomed.size
    centre_x, centre_y = width // 2, height // 2

    # Sampled away from the exact centre, so this checks each line's colour
    # rather than their intersection.
    horizontal_line = zoomed.getpixel((width // 4, centre_y))
    assert horizontal_line[0] > horizontal_line[1] + 20
    assert horizontal_line[0] > horizontal_line[2] + 20

    vertical_line = zoomed.getpixel((centre_x, height // 4))
    assert vertical_line[0] > vertical_line[1] + 20
    assert vertical_line[0] > vertical_line[2] + 20


def test_zoom_rejects_a_nonsense_factor():
    with pytest.raises(ValueError):
        zoom_image(detailed_image(), factor=0)


def test_zoom_handles_transparency():
    import base64
    from io import BytesIO

    from PIL import Image

    rgba = Image.new("RGBA", (800, 600), (0, 128, 255, 128))
    buffer = BytesIO()
    rgba.save(buffer, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    image, _ = load_image(zoom_image(data_url, max_dimension=256))

    assert image.mode == "RGB"
    assert max(image.size) == 256
