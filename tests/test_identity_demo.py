"""Tests for the admin identity-code workbench (``backend.identity_demo``).

The pure decoding logic is tested in ``test_identity_*.py``; this covers the
demo layer -- spec parsing, error messages, the simulation, and the admin API.
"""

import pytest

from backend import identity_demo as demo


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def candidates(count):
    return [demo.CandidateSpec(name=f"p{i}", slot=i) for i in range(count)]


# -- scheme building --------------------------------------------------------


def test_default_scheme_matches_the_config():
    info = demo.describe_scheme(demo.SchemeSpec())

    assert (info["n"], info["k"], info["q"]) == (4, 2, 7)
    assert info["min_distance"] == 3
    assert info["capacity"] == 49
    # Every channel is full width, so only the all-black slot 0 is unassignable.
    assert info["usable_capacity"] == 48
    assert info["code_type"] == "reed_solomon"
    assert len(info["codebook"]) == 49
    assert info["codebook"][0]["appearance"] == {
        "tshirt": "black",
        "trousers": "black",
        "hat": "black",
        "armbands": "black",
    }


def test_codebook_marks_unwearable_codewords():
    # The configured scheme has no narrowed channel any more, so narrow one in
    # the workbench - which is what the workbench is for.
    spec = demo.SchemeSpec(
        channels=[
            demo.ChannelSpec(name="tshirt"),
            demo.ChannelSpec(
                name="trousers", labels=["black", "blue", "green", "red", "white"]
            ),
            demo.ChannelSpec(name="hat"),
            demo.ChannelSpec(name="armbands"),
        ]
    )
    info = demo.describe_scheme(spec)

    # Slot 5's codeword asks trousers for symbol 5, which then has no colour.
    row = info["codebook"][5]
    assert row["wearable"] is False
    assert row["appearance"] is None
    assert info["codebook"][0]["wearable"] is True
    assert info["usable_capacity"] == 34


def test_upgrade_ladder_gives_the_expected_codes():
    spec = demo.SchemeSpec(
        channels=[demo.ChannelSpec(name=f"c{i}") for i in range(4)],
        target_distance=3,
    )
    info = demo.describe_scheme(spec)

    assert (info["n"], info["k"], info["min_distance"]) == (4, 2, 3)
    assert info["code_type"] == "reed_solomon"
    assert info["guarantees"]["correctable_misreads"] == 1


def test_per_channel_alphabets_are_allowed():
    spec = demo.SchemeSpec(
        palette=["red", "yellow", "green", "blue", "purple"],
        channels=[
            demo.ChannelSpec(name="shirt"),
            demo.ChannelSpec(name="head"),
            demo.ChannelSpec(
                name="shape",
                labels=["circle", "square", "triangle", "star", "cross"],
            ),
        ],
        target_distance=2,
    )
    info = demo.describe_scheme(spec)

    assert info["channels"][2]["labels"][0] == "circle"
    assert info["codebook"][0]["appearance"]["shape"] == "circle"


def test_spare_palette_colours_via_explicit_q():
    spec = demo.SchemeSpec(
        palette=["red", "yellow", "green", "blue", "purple", "orange"],
        channels=[demo.ChannelSpec(name=n) for n in ("shirt", "head", "armband")],
        target_distance=2,
        q=5,
    )
    info = demo.describe_scheme(spec)

    assert info["q"] == 5
    assert info["capacity"] == 25
    # The spare colour exists in the alphabet but is never addressed.
    assert "orange" in info["channels"][0]["labels"]
    assert all("orange" not in row["appearance"].values() for row in info["codebook"])


def test_codebook_can_be_truncated():
    info = demo.describe_scheme(demo.SchemeSpec(), max_rows=5)

    assert len(info["codebook"]) == 5
    assert info["codebook_truncated"] is True


@pytest.mark.parametrize(
    "spec, message_fragment",
    [
        (demo.SchemeSpec(palette=["a", "b", "c", "d"]), "prime"),
        (demo.SchemeSpec(palette=["red", "red", "green"]), "duplicate"),
        (demo.SchemeSpec(channels=[]), "at least one channel"),
        (demo.SchemeSpec(target_distance=5), "cannot exceed n"),
        (demo.SchemeSpec(code_type="banana"), "unknown code_type"),
        (
            demo.SchemeSpec(
                channels=[demo.ChannelSpec(name=f"c{i}") for i in range(8)],
                target_distance=4,
            ),
            "n <= q",
        ),
    ],
)
def test_bad_schemes_explain_themselves(spec, message_fragment):
    with pytest.raises(demo.DemoError) as excinfo:
        demo.describe_scheme(spec)

    assert message_fragment in str(excinfo.value)


# -- decoding ---------------------------------------------------------------


# Slot 7 is codeword (0, 1, 2, 3): black t-shirt, purple trousers, red hat,
# blue armbands. Slot 14 is (0, 2, 4, 6) and shares only the t-shirt with it.
TARGET = "p7"


def test_clean_reading_identifies_the_right_player():
    request = demo.DecodeRequest(
        candidates=candidates(10),
        reading=[
            demo.ObservationSpec(symbol="black", confidence=0.9),
            demo.ObservationSpec(symbol="purple", confidence=0.9),
            demo.ObservationSpec(symbol="red", confidence=0.9),
            demo.ObservationSpec(symbol="blue", confidence=0.9),
        ],
    )
    result = demo.decode_reading(request)

    assert result["best"] == TARGET
    assert result["inconsistent"] is False
    assert result["auto_accept"] is True
    assert result["hard_reading"] == ["black", "purple", "red", "blue"]
    assert result["hard_reading_is_codeword"] is True
    assert result["ranked"][0]["distance"] == 0


def test_two_erasures_are_corrected():
    # d=3, so any two hidden garments still identify the player (plan §2.4).
    request = demo.DecodeRequest(
        candidates=candidates(49),
        reading=[
            demo.ObservationSpec(symbol="black", confidence=0.9),
            demo.ObservationSpec(symbol="purple", confidence=0.9),
            demo.ObservationSpec(kind="erasure"),
            demo.ObservationSpec(kind="erasure"),
        ],
    )
    result = demo.decode_reading(request)

    assert result["best"] == TARGET
    assert result["num_erasures"] == 2
    assert result["inconsistent"] is False
    assert result["hard_reading_is_codeword"] is None


def test_single_misread_is_corrected():
    # d=3 corrects one misread outright rather than only flagging it.
    request = demo.DecodeRequest(
        candidates=candidates(49),
        reading=[
            demo.ObservationSpec(symbol="black", confidence=0.9),
            demo.ObservationSpec(symbol="purple", confidence=0.9),
            demo.ObservationSpec(symbol="green", confidence=0.9),  # hat misread
            demo.ObservationSpec(symbol="blue", confidence=0.9),
        ],
    )
    result = demo.decode_reading(request)

    assert result["best"] == TARGET
    assert result["inconsistent"] is False
    assert result["hard_reading_is_codeword"] is False
    assert result["min_distance_to_codeword"] == 1


def test_erasure_plus_misread_is_detected_as_inconsistent():
    # One hidden garment leaves no correction budget, so a misread alongside it
    # is flagged rather than silently decoded.
    request = demo.DecodeRequest(
        candidates=candidates(49),
        reading=[
            demo.ObservationSpec(symbol="black", confidence=0.9),
            demo.ObservationSpec(symbol="purple", confidence=0.9),
            demo.ObservationSpec(symbol="green", confidence=0.9),  # hat misread
            demo.ObservationSpec(kind="erasure"),
        ],
    )
    result = demo.decode_reading(request)

    assert result["inconsistent"] is True
    assert result["min_distance_to_codeword"] == 1


def test_prior_breaks_a_tie():
    # Only the t-shirt is readable, and both candidates wear black: a pure tie.
    reading = [
        demo.ObservationSpec(symbol="black", confidence=0.9),
        demo.ObservationSpec(kind="erasure"),
        demo.ObservationSpec(kind="erasure"),
        demo.ObservationSpec(kind="erasure"),
    ]
    biased = demo.DecodeRequest(
        candidates=[
            demo.CandidateSpec(name="near", slot=7, prior=0.9),
            demo.CandidateSpec(name="far", slot=14, prior=0.1),
        ],
        reading=reading,
    )
    result = demo.decode_reading(biased)

    assert result["best"] == "near"
    assert result["ranked"][0]["posterior"] > result["ranked"][1]["posterior"]


def test_distribution_observations_are_accepted():
    request = demo.DecodeRequest(
        candidates=candidates(10),
        reading=[
            demo.ObservationSpec(
                kind="distribution", distribution={"black": 0.6, "green": 0.4}
            ),
            demo.ObservationSpec(symbol="purple", confidence=0.9),
            demo.ObservationSpec(symbol="red", confidence=0.9),
            demo.ObservationSpec(symbol="blue", confidence=0.9),
        ],
    )
    result = demo.decode_reading(request)

    assert result["best"] == TARGET


def test_a_colour_outside_a_channels_palette_is_rejected():
    # The workbench's own narrowed trousers channel: "yellow" exists in the
    # main palette, and a channel restricted to five colours does not have it.
    request = demo.DecodeRequest(
        scheme=demo.SchemeSpec(
            channels=[
                demo.ChannelSpec(name="tshirt"),
                demo.ChannelSpec(
                    name="trousers", labels=["black", "blue", "green", "red", "white"]
                ),
                demo.ChannelSpec(name="hat"),
                demo.ChannelSpec(name="armbands"),
            ]
        ),
        candidates=candidates(10),
        reading=[
            demo.ObservationSpec(symbol="black", confidence=0.9),
            demo.ObservationSpec(symbol="yellow", confidence=0.9),
            demo.ObservationSpec(symbol="red", confidence=0.9),
            demo.ObservationSpec(symbol="blue", confidence=0.9),
        ],
    )
    with pytest.raises(demo.DemoError) as excinfo:
        demo.decode_reading(request)

    assert "trousers" in str(excinfo.value)


@pytest.mark.parametrize(
    "request_kwargs, message_fragment",
    [
        ({"candidates": [], "reading": []}, "channels"),
        (
            {
                "candidates": candidates(2),
                "reading": [demo.ObservationSpec(symbol="beige")]
                + [demo.ObservationSpec(symbol="red")] * 3,
            },
            "no label 'beige'",
        ),
        (
            {
                "candidates": [
                    demo.CandidateSpec(name="a", slot=0),
                    demo.CandidateSpec(name="a", slot=1),
                ],
                "reading": [demo.ObservationSpec(symbol="red")] * 4,
            },
            "unique",
        ),
        (
            {
                "candidates": [demo.CandidateSpec(name="a", slot=99)],
                "reading": [demo.ObservationSpec(symbol="red")] * 4,
            },
            "out of range",
        ),
    ],
)
def test_bad_decode_requests_explain_themselves(request_kwargs, message_fragment):
    with pytest.raises(demo.DemoError) as excinfo:
        demo.decode_reading(demo.DecodeRequest(**request_kwargs))

    assert message_fragment in str(excinfo.value)


# -- simulation -------------------------------------------------------------


def test_noiseless_simulation_is_perfect():
    result = demo.simulate(
        demo.SimulateRequest(
            trials=200, p_erasure=0.0, p_misread=0.0, confidence=1.0, seed=1
        )
    )

    assert result["counts"]["top_correct"] == 200
    assert result["counts"]["auto_accept_wrong"] == 0
    assert result["silent_failure_examples"] == []


def test_simulation_is_reproducible_from_the_seed():
    def run(seed):
        return demo.simulate(
            demo.SimulateRequest(trials=200, seed=seed, p_misread=0.2)
        )["counts"]

    assert run(7) == run(7)
    assert run(7) != run(8)


def test_more_distance_means_fewer_silent_failures():
    parity = demo.SimulateRequest(trials=1500, p_erasure=0.1, p_misread=0.15, seed=3)
    reed_solomon = demo.SimulateRequest(
        scheme=demo.SchemeSpec(
            channels=[demo.ChannelSpec(name=f"c{i}") for i in range(5)],
            target_distance=4,
        ),
        trials=1500,
        p_erasure=0.1,
        p_misread=0.15,
        seed=3,
    )

    weak = demo.simulate(parity)["rates"]["error_given_auto_accept"]
    strong = demo.simulate(reed_solomon)["rates"]["error_given_auto_accept"]

    assert strong < weak


def test_simulation_counts_add_up():
    counts = demo.simulate(demo.SimulateRequest(trials=500, seed=2))["counts"]

    assert counts["top_correct"] + counts["top_wrong"] == 500
    assert counts["auto_accept"] + counts["flagged"] == 500
    assert (
        counts["auto_accept_correct"] + counts["auto_accept_wrong"]
        == counts["auto_accept"]
    )


@pytest.mark.parametrize(
    "request_kwargs, message_fragment",
    [
        ({"trials": 0}, "trials must be"),
        ({"p_erasure": 1.5}, "p_erasure must be"),
        ({"p_erasure": 0.6, "p_misread": 0.6}, "must be <= 1"),
        ({"num_players": 999}, "capacity"),
    ],
)
def test_bad_simulations_explain_themselves(request_kwargs, message_fragment):
    with pytest.raises(demo.DemoError) as excinfo:
        demo.simulate(demo.SimulateRequest(**request_kwargs))

    assert message_fragment in str(excinfo.value)


# -- the admin API ----------------------------------------------------------


def test_endpoints_need_admin_auth(api_client):
    assert api_client.get("/api/admin_identity_defaults").status_code == 403
    assert api_client.post("/api/admin_identity_scheme", json={}).status_code == 403


def test_api_defaults(admin_api_client):
    response = admin_api_client.get("/api/admin_identity_defaults")

    assert response.status_code == 200
    body = response.json()
    assert body["channel_names"] == ["tshirt", "trousers", "hat", "armbands"]
    assert body["target_distance"] == 3
    # Every channel wears the main palette, so none carries an explicit
    # alphabet; a channel given one in CHANNEL_PALETTES would travel with it.
    assert all(c["labels"] is None for c in body["channels"])


def test_api_scheme_and_decode(admin_api_client):
    response = admin_api_client.post("/api/admin_identity_scheme", json={})
    assert response.status_code == 200
    assert response.json()["capacity"] == 49

    response = admin_api_client.post(
        "/api/admin_identity_decode",
        json={
            "candidates": [{"name": "p7", "slot": 7}, {"name": "p8", "slot": 8}],
            "reading": [
                {"kind": "best_guess", "symbol": "black", "confidence": 0.9},
                {"kind": "best_guess", "symbol": "blue", "confidence": 0.9},
                {"kind": "best_guess", "symbol": "red", "confidence": 0.9},
                {"kind": "erasure"},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["best"] == "p7"


def test_api_simulate(admin_api_client):
    response = admin_api_client.post(
        "/api/admin_identity_simulate", json={"trials": 100, "seed": 5}
    )

    assert response.status_code == 200
    assert response.json()["counts"]["trials"] == 100


def test_api_reports_bad_schemes_as_400(admin_api_client):
    response = admin_api_client.post(
        "/api/admin_identity_scheme", json={"palette": ["a", "b", "c", "d"]}
    )

    assert response.status_code == 400
    assert "prime" in response.json()["detail"]
