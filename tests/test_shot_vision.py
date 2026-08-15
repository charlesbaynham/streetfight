"""Tests for the vision adapter: the prompt contract, parsing, and the
hit/bystander rule.

No network and no database: every test either builds a reply by hand or feeds
one through :class:`FakeVisionClient`.
"""

import pytest

from backend import shot_vision as sv
from backend.identity.config import TROUSERS_PALETTE
from backend.identity.config import default_scheme
from backend.vision_client import FakeVisionClient
from backend.vision_client import VisionError
from backend.vision_client import parse_json_reply

SCHEME = default_scheme()
CHANNELS = ["tshirt", "trousers", "hat", "armbands"]


# -- helpers ----------------------------------------------------------------


def appearance_of(slot):
    return SCHEME.appearance_of_slot(slot)


def reply_for(appearance, hidden=(), person=True, confidence=0.9):
    """A well-formed model reply for someone wearing ``appearance``."""
    channels = {}
    for name in CHANNELS:
        if name in hidden:
            channels[name] = {
                "visible": False,
                "colour": "unknown",
                "confidence": 0.2,
            }
        else:
            channels[name] = {
                "visible": True,
                "colour": appearance[name],
                "confidence": confidence,
            }
    return {
        "shot_hit_a_person": person,
        "reasoning": "a test reply",
        "channels": channels,
    }


def outcome_of(raw):
    return sv.classify(sv.parse_result(raw), SCHEME)


# -- the prompt -------------------------------------------------------------


def test_prompt_offers_unknown_for_every_channel():
    prompt = sv.build_prompt()

    # The measured failure mode without it is a confident wrong colour, which
    # costs twice what an abstention does.
    assert prompt.count('answer is no and the colour is "unknown"') == len(CHANNELS)


def test_prompt_asks_about_visibility_before_colour():
    prompt = sv.build_prompt()

    for name in CHANNELS:
        section = prompt.split(f"{name} (")[1]
        assert section.index("Can you clearly see it") < section.index(
            "which of these is it"
        )


def test_prompt_offers_each_channel_only_its_own_colours():
    prompt = sv.build_prompt()

    trousers_options = prompt.split("trousers (")[1].split("hat (")[0]
    for colour in TROUSERS_PALETTE:
        assert f'"{colour}"' in trousers_options
    # Nobody owns yellow trousers, so the model must never be able to say so
    for absent in ("yellow", "orange", "purple"):
        assert f'"{absent}"' not in trousers_options


def test_schema_restricts_the_trousers_enum():
    schema = sv.build_schema()
    trousers = schema["properties"]["channels"]["properties"]["trousers"]

    assert trousers["properties"]["colour"]["enum"] == TROUSERS_PALETTE + ["unknown"]


def test_prompt_names_the_wide_colour_buckets():
    prompt = sv.build_prompt()

    assert "includes olive and khaki" in prompt
    assert "includes navy and denim" in prompt


# -- parsing ----------------------------------------------------------------


def test_parses_a_well_formed_reply():
    result = sv.parse_result(reply_for(appearance_of(7)))

    assert result.shot_hit_a_person
    assert result.channels["tshirt"].colour == "black"
    assert result.channels["armbands"].colour == "blue"
    assert result.channels["tshirt"].confidence == 0.9


def test_unknown_becomes_an_erasure():
    result = sv.parse_result(reply_for(appearance_of(7), hidden=("hat",)))

    assert result.channels["hat"].is_erasure
    assert result.channels["hat"].colour is None


def test_a_colour_outside_the_channel_palette_is_rejected():
    raw = reply_for(appearance_of(7))
    raw["channels"]["trousers"]["colour"] = "yellow"

    with pytest.raises(sv.ShotVisionError) as excinfo:
        sv.parse_result(raw)

    assert "trousers" in str(excinfo.value)


def test_a_nonsense_colour_is_rejected():
    raw = reply_for(appearance_of(7))
    raw["channels"]["hat"]["colour"] = "beige"

    with pytest.raises(sv.ShotVisionError):
        sv.parse_result(raw)


def test_a_named_colour_with_visible_false_is_treated_as_unreadable():
    # Believe the abstention: an erasure is the cheap failure, a misread is not.
    raw = reply_for(appearance_of(7))
    raw["channels"]["hat"]["visible"] = False

    result = sv.parse_result(raw)

    assert result.channels["hat"].is_erasure


def test_missing_channels_are_rejected():
    raw = reply_for(appearance_of(7))
    del raw["channels"]["hat"]

    with pytest.raises(sv.ShotVisionError) as excinfo:
        sv.parse_result(raw)

    assert "hat" in str(excinfo.value)


def test_a_missing_verdict_field_is_rejected():
    with pytest.raises(sv.ShotVisionError):
        sv.parse_result({"reasoning": "hmm", "channels": {}})


def test_a_miss_needs_no_channels():
    result = sv.parse_result(
        {"shot_hit_a_person": False, "reasoning": "empty pavement"}
    )

    assert not result.shot_hit_a_person
    assert all(read.is_erasure for read in result.channels.values())


def test_confidence_is_clamped_not_rejected():
    raw = reply_for(appearance_of(7))
    raw["channels"]["tshirt"]["confidence"] = 5.0

    assert sv.parse_result(raw).channels["tshirt"].confidence == 1.0


# -- the top-level confidence -----------------------------------------------


def test_top_level_confidence_is_parsed():
    raw = reply_for(appearance_of(7))
    raw["confidence"] = 0.7

    assert sv.parse_result(raw).confidence == 0.7


def test_top_level_confidence_is_clamped_not_rejected():
    raw = reply_for(appearance_of(7))

    raw["confidence"] = 5.0
    assert sv.parse_result(raw).confidence == 1.0

    raw["confidence"] = -3
    assert sv.parse_result(raw).confidence == 0.0


def test_a_missing_top_level_confidence_defaults_to_zero():
    # Legacy stored reviews have no confidence field, and a model may ignore
    # the request. Neither must ever look confident enough to auto-fire.
    assert sv.parse_result(reply_for(appearance_of(7))).confidence == 0.0


def test_an_unparseable_top_level_confidence_defaults_to_zero():
    raw = reply_for(appearance_of(7))
    raw["confidence"] = "very sure"

    assert sv.parse_result(raw).confidence == 0.0


def test_a_miss_reply_keeps_its_confidence():
    raw = {"shot_hit_a_person": False, "reasoning": "pavement", "confidence": 0.8}

    assert sv.parse_result(raw).confidence == 0.8


def test_to_dict_includes_the_top_level_confidence():
    raw = reply_for(appearance_of(7))
    raw["confidence"] = 0.7

    assert outcome_of(raw).to_dict()["confidence"] == 0.7


def test_the_schema_requires_the_overall_confidence():
    schema = sv.build_schema()

    assert schema["properties"]["confidence"] == {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
    }
    assert "confidence" in schema["required"]


def test_the_prompt_asks_for_an_overall_confidence():
    prompt = sv.build_prompt()

    assert "photo as a whole" in prompt
    assert '"confidence": 0.9' in prompt


# -- the low-confidence erasure rule ----------------------------------------


def test_a_low_confidence_channel_becomes_an_erasure():
    raw = reply_for(appearance_of(7))
    raw["channels"]["armbands"]["confidence"] = 0.5

    symbols = sv.to_hard_symbols(sv.parse_result(raw), SCHEME)

    assert symbols[CHANNELS.index("armbands")] is None


def test_low_confidence_armbands_fall_back_to_the_code_check():
    # A shaky armband read behaves exactly like a hidden one: the other three
    # channels still reconstruct the outfit.
    raw = reply_for(appearance_of(7))
    raw["channels"]["armbands"]["confidence"] = 0.5

    result = outcome_of(raw)

    assert result.outcome == sv.HIT_PLAYER
    assert result.outcome_reason == (
        "armbands hidden, but the other colours are a valid code"
    )
    assert result.slot == 7


def test_two_low_confidence_channels_make_a_bystander():
    raw = reply_for(appearance_of(7))
    raw["channels"]["armbands"]["confidence"] = 0.5
    raw["channels"]["hat"]["confidence"] = 0.55

    result = outcome_of(raw)

    assert result.outcome == sv.HIT_BYSTANDER
    assert "too few other garments" in result.outcome_reason


# -- rebuilding candidates from a stored review -----------------------------


def stored_review(raw):
    """The to_dict() payload a completed review of ``raw`` would store."""
    return outcome_of(raw).to_dict()


def test_slot_candidates_identify_a_fully_read_outfit():
    body = stored_review(reply_for(appearance_of(7)))

    assert sv.slot_candidates_from_review(body, SCHEME) == [7]


def test_slot_candidates_survive_one_erasure():
    body = stored_review(reply_for(appearance_of(7), hidden=("hat",)))

    assert sv.slot_candidates_from_review(body, SCHEME) == [7]


def test_slot_candidates_with_only_two_readable_channels_are_empty():
    # With only k = 2 readable positions an MDS code matches exactly one
    # codeword whatever the colours are, so the match vouches for nothing.
    body = stored_review(reply_for(appearance_of(7), hidden=("hat", "armbands")))

    assert sv.slot_candidates_from_review(body, SCHEME) == []


def test_slot_candidates_erase_low_confidence_stored_reads():
    # Same erasure rule as the live path: two channels at 0.5 leave only two
    # readable, which is not enough to vouch for anything.
    raw = reply_for(appearance_of(7))
    raw["channels"]["hat"]["confidence"] = 0.5
    raw["channels"]["armbands"]["confidence"] = 0.5

    assert sv.slot_candidates_from_review(stored_review(raw), SCHEME) == []


def test_slot_candidates_of_an_invalid_code_are_empty():
    # Three readable channels whose unique completion is not the outfit anyone
    # wears. (With >= 3 readable positions an MDS code matches at most one
    # codeword, so "several candidates" cannot occur here; zero candidates is
    # the ambiguous case.)
    raw = reply_for(appearance_of(7), hidden=("armbands",))
    appearance = appearance_of(7)
    wrong = "green" if appearance["hat"] != "green" else "orange"
    raw["channels"]["hat"]["colour"] = wrong

    assert sv.slot_candidates_from_review(stored_review(raw), SCHEME) == []


def test_slot_candidates_of_a_garbled_payload_are_empty():
    assert sv.slot_candidates_from_review({"outcome": "hit_player"}, SCHEME) == []
    assert sv.slot_candidates_from_review({"channels": "what"}, SCHEME) == []
    assert (
        sv.slot_candidates_from_review({"channels": {"tshirt": "black"}}, SCHEME) == []
    )


# -- the hit / bystander rule -----------------------------------------------


def test_no_person_at_the_aim_point_is_a_miss():
    result = outcome_of({"shot_hit_a_person": False, "reasoning": "missed"})

    assert result.outcome == sv.MISS
    assert not result.is_hit


def test_visible_armbands_are_a_hit():
    result = outcome_of(reply_for(appearance_of(7)))

    assert result.outcome == sv.HIT_PLAYER
    assert result.is_hit
    assert result.slot == 7


def test_visible_armbands_are_a_hit_even_with_everything_else_hidden():
    # Armbands are the player marker; the rest is identification, not eligibility.
    result = outcome_of(
        reply_for(appearance_of(7), hidden=("tshirt", "trousers", "hat"))
    )

    assert result.outcome == sv.HIT_PLAYER


def test_hidden_armbands_still_count_when_the_code_checks_out():
    # The point of the erasure tolerance: three good garments reconstruct the
    # fourth, so a real player is not written off as a passer-by.
    result = outcome_of(reply_for(appearance_of(7), hidden=("armbands",)))

    assert result.outcome == sv.HIT_PLAYER
    assert result.outcome_reason == (
        "armbands hidden, but the other colours are a valid code"
    )
    assert result.slot == 7


def test_hidden_armbands_and_an_invalid_code_is_a_bystander():
    raw = reply_for(appearance_of(7), hidden=("armbands",))
    # Break the code: change the hat to a colour no codeword pairs with these
    appearance = appearance_of(7)
    wrong = "green" if appearance["hat"] != "green" else "orange"
    raw["channels"]["hat"]["colour"] = wrong

    result = outcome_of(raw)

    assert result.outcome == sv.HIT_BYSTANDER
    assert not result.is_hit


def test_hidden_armbands_and_a_second_erasure_is_a_bystander():
    # Only two readable channels always complete to *some* codeword (k = 2), so
    # the check would vouch for nothing. It must not be treated as evidence.
    result = outcome_of(reply_for(appearance_of(7), hidden=("armbands", "hat")))

    assert result.outcome == sv.HIT_BYSTANDER
    assert "too few other garments" in result.outcome_reason


def test_the_all_black_outfit_is_a_bystander():
    # Slot 0 is deliberately never assigned: it is the most likely outfit for a
    # passer-by to be wearing by accident, and where "black" misreads pile up.
    result = outcome_of(reply_for(appearance_of(0), hidden=("armbands",)))

    assert result.outcome == sv.HIT_BYSTANDER


def test_every_usable_slot_survives_hidden_armbands():
    for slot in SCHEME.usable_slots():
        result = outcome_of(reply_for(appearance_of(slot), hidden=("armbands",)))
        assert result.outcome == sv.HIT_PLAYER, slot
        assert result.slot == slot


# -- handing the reading to the decoder -------------------------------------


def test_to_reading_maps_colours_and_erasures():
    result = sv.parse_result(reply_for(appearance_of(7), hidden=("hat",)))
    reading = sv.to_reading(result, SCHEME)

    assert len(reading) == 4
    assert reading.num_erasures == 1
    assert reading[2].is_erasure  # hat is the third channel
    assert not reading[0].is_erasure


def test_to_hard_symbols_matches_the_codeword():
    slot = 7
    result = sv.parse_result(reply_for(appearance_of(slot)))

    assert sv.to_hard_symbols(result, SCHEME) == list(SCHEME.codeword_of_slot(slot))


def test_result_serialises_with_colour_swatches():
    body = outcome_of(reply_for(appearance_of(7))).to_dict()

    assert body["outcome"] == sv.HIT_PLAYER
    assert body["is_hit"] is True
    assert body["channels"]["tshirt"]["hex"] == "#1A1A1A"
    # The same colour name has a different hex in the trousers palette
    assert body["channels"]["trousers"]["colour"] == "blue"
    assert body["channels"]["trousers"]["hex"] == "#0072CE"


def test_serialised_erasure_has_no_swatch():
    body = outcome_of(reply_for(appearance_of(7), hidden=("hat",))).to_dict()

    assert body["channels"]["hat"]["colour"] is None
    assert body["channels"]["hat"]["hex"] is None


# -- the client contract ----------------------------------------------------


@pytest.mark.asyncio
async def test_review_image_runs_the_whole_pipeline():
    client = FakeVisionClient(reply=reply_for(appearance_of(8)))

    result = await sv.review_image(client, "data:image/jpeg;base64,AAAA", SCHEME)

    assert result.outcome == sv.HIT_PLAYER
    assert result.slot == 8
    # The image and the real prompt reached the client
    assert client.images_sent == ["data:image/jpeg;base64,AAAA"]
    assert "unknown" in client.calls[0]["turns"][0]["text"]


# -- the one zoom the model may ask for --------------------------------------

ZOOM_REQUEST = {"request_zoom": True}


@pytest.mark.asyncio
async def test_a_zoom_request_gets_exactly_one_more_turn():
    client = FakeVisionClient(reply=[ZOOM_REQUEST, reply_for(appearance_of(8))])

    result = await sv.review_image(
        client,
        "data:image/jpeg;base64,WIDE",
        SCHEME,
        zoom_provider=lambda: "data:image/jpeg;base64,ZOOMED",
    )

    assert len(client.calls) == 2
    assert client.images_sent == [
        "data:image/jpeg;base64,WIDE",
        "data:image/jpeg;base64,WIDE",  # the first turn is still in view
        "data:image/jpeg;base64,ZOOMED",
    ]
    assert result.outcome == sv.HIT_PLAYER
    assert result.slot == 8


@pytest.mark.asyncio
async def test_the_second_turn_carries_the_first_exchange():
    client = FakeVisionClient(reply=[ZOOM_REQUEST, reply_for(appearance_of(8))])

    await sv.review_image(client, "data:...", SCHEME, zoom_provider=lambda: "data:zoom")

    roles = [turn["role"] for turn in client.calls[1]["turns"]]
    assert roles == ["user", "assistant", "user"]
    assert "one zoom" in client.calls[1]["turns"][-1]["text"]


@pytest.mark.asyncio
async def test_the_zoom_is_not_produced_unless_it_is_asked_for():
    calls = []

    def zoom_provider():
        calls.append(1)
        return "data:zoom"

    client = FakeVisionClient(reply=reply_for(appearance_of(8)))

    await sv.review_image(client, "data:...", SCHEME, zoom_provider=zoom_provider)

    assert calls == []


@pytest.mark.asyncio
async def test_only_one_zoom_is_ever_granted():
    # A model that keeps asking gets its second reply used as the answer.
    second = reply_for(appearance_of(8))
    second["request_zoom"] = True
    client = FakeVisionClient(reply=[ZOOM_REQUEST, second])

    result = await sv.review_image(
        client, "data:...", SCHEME, zoom_provider=lambda: "data:zoom"
    )

    assert len(client.calls) == 2
    assert result.outcome == sv.HIT_PLAYER


@pytest.mark.asyncio
async def test_a_zoom_request_with_no_zoom_available_is_an_error_not_a_hang():
    client = FakeVisionClient(reply=ZOOM_REQUEST)

    with pytest.raises(sv.ShotVisionError):
        await sv.review_image(client, "data:...", SCHEME)

    assert len(client.calls) == 1


def test_wants_zoom_only_fires_on_an_explicit_true():
    assert sv.wants_zoom({"request_zoom": True})
    assert not sv.wants_zoom({"request_zoom": False})
    assert not sv.wants_zoom({})
    assert not sv.wants_zoom("nope")


def test_the_schema_lets_the_model_ask():
    assert sv.build_schema()["properties"]["request_zoom"] == {"type": "boolean"}


def test_the_prompt_explains_the_zoom_and_the_hit_rule():
    prompt = sv.build_prompt()

    assert '{"request_zoom": true}' in prompt
    assert "middle 25% of the image in higher resolution" in prompt
    assert "You may do this once only" in prompt
    assert "You MUST ultimately make a decision" in prompt
    assert "clothing or hands or shoes counts as a hit" in prompt


def test_the_buckets_cover_chinos():
    assert "beige" in sv.build_prompt()


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        'Sure! Here is the JSON:\n{"a": 1}\nHope that helps.',
    ],
)
def test_json_is_recovered_however_the_model_wraps_it(text):
    assert parse_json_reply(text) == {"a": 1}


@pytest.mark.parametrize("text", ["", "   ", "I could not do that", "[1, 2, 3]"])
def test_unparseable_replies_raise(text):
    with pytest.raises(VisionError):
        parse_json_reply(text)
