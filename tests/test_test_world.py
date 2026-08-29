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
