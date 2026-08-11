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

    assert (info["n"], info["k"], info["q"]) == (3, 2, 5)
    assert info["min_distance"] == 2
    assert info["capacity"] == 25
    assert info["code_type"] == "parity"
    assert len(info["codebook"]) == 25
    assert info["codebook"][0]["appearance"] == {
        "shirt": "red",
        "head": "red",
        "armband": "red",
    }


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
        channels=[
            demo.ChannelSpec(name="shirt"),
            demo.ChannelSpec(name="head"),
            demo.ChannelSpec(
                name="shape",
                labels=["circle", "square", "triangle", "star", "cross"],
            ),
        ]
    )
    info = demo.describe_scheme(spec)

    assert info["channels"][2]["labels"][0] == "circle"
    assert info["codebook"][0]["appearance"]["shape"] == "circle"


def test_spare_palette_colours_via_explicit_q():
    spec = demo.SchemeSpec(
        palette=["red", "yellow", "green", "blue", "purple", "orange"], q=5
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
                channels=[demo.ChannelSpec(name=f"c{i}") for i in range(6)],
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


def test_clean_reading_identifies_the_right_player():
    request = demo.DecodeRequest(
        candidates=candidates(5),
        reading=[
            demo.ObservationSpec(symbol="yellow", confidence=0.9),
            demo.ObservationSpec(symbol="red", confidence=0.9),
            demo.ObservationSpec(symbol="purple", confidence=0.9),
        ],
    )
    result = demo.decode_reading(request)

    # Slot 1 is codeword (1, 0, 4) = yellow / red / purple.
    assert result["best"] == "p1"
    assert result["inconsistent"] is False
    assert result["auto_accept"] is True
    assert result["hard_reading"] == ["yellow", "red", "purple"]
    assert result["hard_reading_is_codeword"] is True
    assert result["ranked"][0]["distance"] == 0


def test_erasure_is_corrected_by_the_parity_channel():
    request = demo.DecodeRequest(
        candidates=candidates(25),
        reading=[
            demo.ObservationSpec(symbol="yellow", confidence=0.9),
            demo.ObservationSpec(symbol="red", confidence=0.9),
            demo.ObservationSpec(kind="erasure"),
        ],
    )
    result = demo.decode_reading(request)

    assert result["best"] == "p1"
    assert result["num_erasures"] == 1
    assert result["inconsistent"] is False
    assert result["hard_reading_is_codeword"] is None


def test_misread_is_detected_as_inconsistent():
    request = demo.DecodeRequest(
        candidates=candidates(25),
        reading=[
            demo.ObservationSpec(symbol="yellow", confidence=0.9),
            demo.ObservationSpec(symbol="red", confidence=0.9),
            demo.ObservationSpec(symbol="green", confidence=0.9),
        ],
    )
    result = demo.decode_reading(request)

    # d=2 detects but cannot correct a single misread.
    assert result["inconsistent"] is True
    assert result["hard_reading_is_codeword"] is False
    assert result["min_distance_to_codeword"] == 1


def test_prior_breaks_a_tie():
    reading = [
        demo.ObservationSpec(symbol="yellow", confidence=0.9),
        demo.ObservationSpec(symbol="red", confidence=0.9),
        demo.ObservationSpec(kind="erasure"),
    ]
    biased = demo.DecodeRequest(
        candidates=[
            demo.CandidateSpec(name="near", slot=1, prior=0.9),
            demo.CandidateSpec(name="far", slot=6, prior=0.1),
        ],
        reading=reading,
    )
    result = demo.decode_reading(biased)

    assert result["best"] == "near"
    assert result["ranked"][0]["posterior"] > result["ranked"][1]["posterior"]


def test_distribution_observations_are_accepted():
    request = demo.DecodeRequest(
        candidates=candidates(5),
        reading=[
            demo.ObservationSpec(
                kind="distribution", distribution={"yellow": 0.6, "green": 0.4}
            ),
            demo.ObservationSpec(symbol="red", confidence=0.9),
            demo.ObservationSpec(symbol="purple", confidence=0.9),
        ],
    )
    result = demo.decode_reading(request)

    assert result["best"] == "p1"


@pytest.mark.parametrize(
    "request_kwargs, message_fragment",
    [
        ({"candidates": [], "reading": []}, "channels"),
        (
            {
                "candidates": candidates(2),
                "reading": [
                    demo.ObservationSpec(symbol="beige"),
                    demo.ObservationSpec(symbol="red"),
                    demo.ObservationSpec(symbol="red"),
                ],
            },
            "no label 'beige'",
        ),
        (
            {
                "candidates": [
                    demo.CandidateSpec(name="a", slot=0),
                    demo.CandidateSpec(name="a", slot=1),
                ],
                "reading": [demo.ObservationSpec(symbol="red")] * 3,
            },
            "unique",
        ),
        (
            {
                "candidates": [demo.CandidateSpec(name="a", slot=99)],
                "reading": [demo.ObservationSpec(symbol="red")] * 3,
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
    assert response.json()["channel_names"] == ["shirt", "head", "armband"]


def test_api_scheme_and_decode(admin_api_client):
    response = admin_api_client.post("/api/admin_identity_scheme", json={})
    assert response.status_code == 200
    assert response.json()["capacity"] == 25

    response = admin_api_client.post(
        "/api/admin_identity_decode",
        json={
            "candidates": [{"name": "p1", "slot": 1}, {"name": "p2", "slot": 2}],
            "reading": [
                {"kind": "best_guess", "symbol": "yellow", "confidence": 0.9},
                {"kind": "best_guess", "symbol": "red", "confidence": 0.9},
                {"kind": "erasure"},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["best"] == "p1"


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
