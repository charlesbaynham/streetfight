"""The parts of the test-world generator that would fail silently.

Deliberately not a test that the world "looks right" -- that is what the gates
are for. These cover the three things whose failure mode is quiet: a world
that stops being reproducible, an image that regenerates when it should have
been cached (or worse, does not when it should have been), and the guard that
keeps the generator away from the model being tested.
"""

import pytest

from backend.test_world import ids
from backend.test_world import scenarios
from backend.test_world import spec
from backend.test_world import store
from backend.test_world.personas import build_cast


@pytest.mark.parametrize("seed", [0, 7, 20260919])
def test_cast_always_satisfies_the_locked_mix(seed):
    """The seed decides who gets what; it can never change how many."""
    build_cast(seed)  # asserts the locked mix internally


def test_cast_is_reproducible_and_seed_sensitive():
    assert build_cast(7) == build_cast(7)
    assert build_cast(7) != build_cast(8)


def test_derived_ids_are_stable_across_processes():
    """UUID5, not a salted hash: printed join codes must survive a restart.

    ``hash()`` of a string is salted per process, so anything derived from it
    would change on every run - which is the bug that makes today's sample
    game's printed QR codes stop working when the server restarts.
    """
    assert ids.team_id(7, "pimlico") == ids.team_id(7, "pimlico")
    assert ids.team_id(7, "pimlico") != ids.team_id(8, "pimlico")
    assert ids.team_id(7, "pimlico") != ids.team_id(7, "millbank")


def test_scenarios_satisfy_the_required_distribution():
    scenarios.assert_distribution()


def test_locked_mixes_all_account_for_every_player():
    for mix in (
        spec.SEX_MIX,
        spec.AGE_MIX,
        spec.ETHNICITY_MIX,
        spec.PICKING_MIX,
        spec.PHONE_MIX,
    ):
        assert sum(mix.values()) == spec.N_PLAYERS


def test_image_id_changes_with_everything_that_changes_the_picture(tmp_path):
    """Absence from the store is the only trigger for spending money, so the
    id has to move when - and only when - the resulting image would differ."""
    one = tmp_path / "one.jpg"
    two = tmp_path / "two.jpg"
    one.write_bytes(b"first")
    two.write_bytes(b"second")

    base = store.image_id("shot", "P", [one], "model-a", {"seed": 1})

    assert base == store.image_id("shot", "P", [one], "model-a", {"seed": 1})
    assert base != store.image_id("shot", "Q", [one], "model-a", {"seed": 1})
    assert base != store.image_id("shot", "P", [one], "model-b", {"seed": 1})
    assert base != store.image_id("shot", "P", [one], "model-a", {"seed": 2})
    assert base != store.image_id("reference", "P", [one], "model-a", {"seed": 1})
    # The cascade that matters: an input image edited in place must change the
    # id of everything conditioned on it, or a stale background survives
    # silently in thirty reference photos.
    assert base != store.image_id("shot", "P", [two], "model-a", {"seed": 1})
    one.write_bytes(b"edited")
    assert base != store.image_id("shot", "P", [one], "model-a", {"seed": 1})


def test_generation_refuses_a_google_model():
    """The recogniser under test is Gemini, so generating its inputs with a
    Google model would make the benchmark circular. A convention cannot fail
    loudly, so this is a guard."""
    from backend.vision_client import ImageGenerationError
    from backend.vision_client import OpenRouterImageClient

    for model in ("google/gemini-2.5-flash", "GOOGLE/Gemini-Pro"):
        with pytest.raises(ImageGenerationError, match="circular"):
            OpenRouterImageClient(api_key="test-key", model=model)

    assert OpenRouterImageClient(api_key="test-key", model="openai/gpt-5.4-image-2")


# -- localisation, cropping and measurement ------------------------------------


def test_a_box_answered_in_pixels_is_converted_rather_than_discarded():
    """The localiser mostly answers in fractions and sometimes in pixels.

    Clamping a pixel answer to 0-1 turns every coordinate into 1.0 and the box
    into nothing, which reads as "no subject in the picture" -- so the shot is
    silently dropped from the fixture set rather than reported as a bad
    reading.
    """
    from backend.test_world.localise import _clean

    pixels = {"x0": 460, "y0": 553, "x1": 630, "y1": 999}
    converted = _clean(pixels, size=(2048, 2048))

    assert converted == pytest.approx(
        {"x0": 460 / 2048, "y0": 553 / 2048, "x1": 630 / 2048, "y1": 999 / 2048}
    )
    # Without a size there is nothing to convert by, so it stays refused.
    assert _clean(pixels) is None
    assert _clean({"x0": 0.5, "y0": 0.5, "x1": 0.5, "y1": 0.9}) is None
    assert _clean(None) is None


def test_the_crop_always_manages_to_point_at_the_aim_point():
    """A crop is where the phone was aimed, so the aim has to end up centred.

    The alternative -- keeping the band's framing and letting the rectangle
    slide off the aim -- puts the crosshair on the pavement beside the target,
    and a hit fixture whose crosshair misses is not testing what it says.
    """
    from backend.test_world.crop import LONG_EDGE
    from backend.test_world.crop import SHORT_EDGE
    from backend.test_world.crop import crop_box

    size = (2048, 2048)

    def centre_of(box):
        return ((box[0] + box[2]) / 2 / 2048, (box[1] + box[3]) / 2 / 2048)

    box = crop_box(size, (0.5, 0.5), "mid", portrait=True)
    assert centre_of(box) == pytest.approx((0.5, 0.5))
    assert (box[2] - box[0]) / (box[3] - box[1]) == pytest.approx(
        SHORT_EDGE / LONG_EDGE, rel=1e-3
    )

    # Near an edge it zooms in rather than losing the aim point, and keeps
    # its aspect ratio while doing so.
    cornered = crop_box(size, (0.12, 0.5), "distant", portrait=False)
    assert centre_of(cornered) == pytest.approx((0.12, 0.5), abs=0.002)
    # Loose because the rectangle is rounded to whole pixels, and a heavily
    # zoomed crop is small enough for that rounding to show in the ratio.
    assert (cornered[2] - cornered[0]) / (cornered[3] - cornered[1]) == pytest.approx(
        LONG_EDGE / SHORT_EDGE, rel=1e-2
    )
    wide = crop_box(size, (0.5, 0.5), "distant", portrait=False)
    assert (cornered[2] - cornered[0]) < (wide[2] - wide[0])

    # Closer bands keep less of the source, which is what separates them.
    close = crop_box(size, (0.5, 0.5), "close", portrait=True)
    assert (close[3] - close[1]) < (box[3] - box[1])


def test_the_aim_point_lands_on_the_target_only_when_the_shot_is_a_hit():
    from backend.test_world.crop import aim_point

    subject = {"x0": 0.4, "y0": 0.1, "x1": 0.6, "y1": 0.9}
    boxes = {"subject": subject, "other_person": None}

    hit_x, hit_y = aim_point({"intended_result": "hit"}, boxes)
    assert subject["x0"] < hit_x < subject["x1"]
    assert subject["y0"] < hit_y < subject["y1"]

    miss_x, _ = aim_point({"intended_result": "miss"}, boxes)
    assert not subject["x0"] <= miss_x <= subject["x1"]

    # A bystander scene with nobody else rendered must not quietly become a
    # hit on the player.
    stray_x, _ = aim_point({"intended_result": "bystander"}, boxes)
    assert not subject["x0"] <= stray_x <= subject["x1"]


def test_ciede2000_agrees_with_the_figure_the_palette_was_chosen_against():
    """The hat palette's tightest pair is documented as dE 14.2 (plan 9.1a).

    Hand-rolled maths that is subtly wrong would silently rate every colour
    reading, so it is pinned to a number arrived at independently.
    """
    from backend.test_world.measure import ciede2000
    from backend.test_world.measure import hex_to_rgb

    assert ciede2000((10, 20, 30), (10, 20, 30)) == 0
    assert ciede2000(hex_to_rgb("#A62C3E"), hex_to_rgb("#BF4227")) == pytest.approx(
        14.2, abs=0.05
    )
    assert ciede2000((0, 0, 0), (255, 255, 255)) == pytest.approx(100.0, abs=0.05)
