import os
from uuid import UUID
from uuid import uuid4 as get_uuid

import pytest

from backend.identity.config import COLOUR_BUCKETS
from backend.identity.config import COLOUR_COMMONNESS
from backend.identity.config import PROVIDED_CHANNEL
from backend.identity.config import TEAM_CHANNEL
from backend.identity.config import default_scheme
from backend.identity.config import hex_for
from backend.identity.config import palette_for_channel
from backend.identity.overrides import nearest_slots
from backend.identity.overrides import overrides_for
from backend.identity_admin import outfit_options
from backend.join_codes import make_join_url
from backend.model import TickerEntry
from backend.model import User

# Mocking the environment variables for testing, same pattern as
# tests/test_join_codes.py
os.environ["SECRET_KEY"] = "test_secret_key"
os.environ.setdefault("WEBSITE_URL", "https://streetfight.example.com")

SCHEME = default_scheme()
THRESHOLD = SCHEME.code.min_distance()


# Mock "schedule_update_event" since we don't have an asyncio loop, same
# pattern as tests/test_join_codes.py and tests/test_admin_identity.py.
@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def fresh_player(api_client_factory):
    """A new player TestClient with its session cookie already settled.

    FastAPI's TestClient always reports the same ``request.client.host``
    ("testclient"), and ``get_user_id``'s cookieless-session bookkeeping
    (``backend/user_id.py``) keys its "who hasn't got a cookie back yet"
    dict on exactly that host - so two brand-new clients making their very
    first request before either has a cookie back would otherwise be handed
    the *same* session UUID. A second round trip lets the first client's
    cookie clear that bookkeeping before any other client's first request
    can land in the gap. Doesn't touch the database - my_id creates no
    ``User`` row.
    """
    client = api_client_factory()
    client.get("/api/my_id")
    client.get("/api/my_id")
    return client


def team_join_url_and_colour(admin_api_client, game_id, team_id):
    """Generate join codes (pinning the team's hat colour) and pull out this
    team's team-code URL and the colour it was pinned to."""
    body = admin_api_client.get(f"/api/admin_join_qr_codes?game_id={game_id}").json()
    entry = next(t for t in body["teams"] if UUID(t["team_id"]) == team_id)
    return entry["encoded_url"], entry["team_colour"]


def join_options_call(client, url):
    return client.get("/api/join_options", params={"data": url})


def outfit_options_call(client, url, wardrobe, relaxed=False, page=0):
    return client.post(
        "/api/outfit_options",
        json={"data": url, "wardrobe": wardrobe, "relaxed": relaxed, "page": page},
    )


def pick_outfit_call(client, url, wardrobe, appearance, confirmed=True):
    return client.post(
        "/api/pick_outfit",
        json={
            "data": url,
            "wardrobe": wardrobe,
            "appearance": appearance,
            "confirmed": confirmed,
        },
    )


# ---------------------------------------------------------------------------
# outfit_options - pure ranking, no database involved
# ---------------------------------------------------------------------------


def test_canonical_option_ranks_above_a_much_rarer_overridden_one():
    """The headline rule (plan C4): distance from a canonical codeword beats
    rarity absolutely. A wide-open wardrobe (no channel declared) enumerates
    the whole ~245-outfit space with nobody else in the game, so both a
    0-override and a 1-override tier are guaranteed to exist.
    """
    team_colour = SCHEME.channels.by_name(TEAM_CHANNEL).labels[0]
    options = outfit_options(SCHEME, team_colour, {}, [], get_uuid(), THRESHOLD)

    canonical_idx = [i for i, o in enumerate(options) if o.overrides_needed == 0]
    overridden_idx = [i for i, o in enumerate(options) if o.overrides_needed == 1]
    assert canonical_idx and overridden_idx

    # There really is a rarer overridden option than any canonical one -
    # otherwise the test would pass for the wrong reason (rarity alone would
    # already order them the same way).
    rarest_overridden = max(options[i].rarity for i in overridden_idx)
    least_rare_canonical = min(options[i].rarity for i in canonical_idx)
    assert rarest_overridden > least_rare_canonical

    # Yet every 0-override option ranks above every 1-override option.
    assert max(canonical_idx) < min(overridden_idx)


def test_every_offered_colour_has_a_swatch_and_a_rarity_estimate():
    """Widening a palette means adding the colour in three places, and only one
    of them fails loudly. A colour with no ``PALETTE_HEX`` entry renders as a
    blank swatch; a wardrobe colour with no ``COLOUR_COMMONNESS`` entry falls
    back to ``commonness_for``'s neutral 0.5, which silently parks it in the
    middle of the ranking - so a rare colour added for the capacity would stop
    being the one the picker leads with, which is the whole point of it.
    """
    wardrobe_channels = [
        name
        for name in SCHEME.channels.names
        if name not in (TEAM_CHANNEL, PROVIDED_CHANNEL)
    ]

    for name in SCHEME.channels.names:
        for colour in palette_for_channel(name):
            assert hex_for(name, colour) is not None, f"no hex for {name} {colour}"

    for name in wardrobe_channels:
        estimated = COLOUR_COMMONNESS.get(name, {})
        missing = set(palette_for_channel(name)) - set(estimated)
        assert not missing, f"{name} has no ownership estimate for {sorted(missing)}"


def test_rarity_breaks_ties_within_an_override_tier():
    """Within a tier, rarer outfits rank higher - checked as a monotonicity
    invariant across the whole ranked list rather than one hand-picked pair."""
    team_colour = SCHEME.channels.by_name(TEAM_CHANNEL).labels[0]
    options = outfit_options(SCHEME, team_colour, {}, [], get_uuid(), THRESHOLD)

    tiers = {o.overrides_needed for o in options}
    assert len(tiers) > 1  # otherwise this test can't be exercising the tie-break

    for a, b in zip(options, options[1:]):
        if a.overrides_needed == b.overrides_needed:
            assert a.rarity >= b.rarity


def test_options_are_wearable_from_wardrobe_and_clear_threshold():
    team_colour = SCHEME.channels.by_name(TEAM_CHANNEL).labels[0]
    wardrobe = {"tshirt": ["black", "blue"], "trousers": ["black"]}
    options = outfit_options(SCHEME, team_colour, wardrobe, [], get_uuid(), THRESHOLD)

    assert options  # sanity: this wardrobe does yield some options
    for o in options:
        assert o.appearance["tshirt"] in wardrobe["tshirt"]
        assert o.appearance["trousers"] in wardrobe["trousers"]
        assert o.appearance["hat"] == team_colour
        assert o.min_distance >= THRESHOLD


def test_empty_wardrobe_entry_means_no_constraint_not_no_options():
    """An absent/empty wardrobe entry for a channel opens up its whole
    palette rather than offering nothing (plan C4)."""
    team_colour = SCHEME.channels.by_name(TEAM_CHANNEL).labels[0]
    options = outfit_options(SCHEME, team_colour, {}, [], get_uuid(), THRESHOLD)

    tshirts = {o.appearance["tshirt"] for o in options}
    trousers = {o.appearance["trousers"] for o in options}
    assert tshirts == set(SCHEME.channels.by_name("tshirt").labels)
    assert trousers == set(palette_for_channel("trousers"))


def test_options_never_share_a_wardrobe_combination():
    """The armband is ours to assign, not the player's to choose (roadmap
    #10 revision): across the whole open wardrobe space, no two returned
    options share a tshirt+trousers pair."""
    team_colour = SCHEME.channels.by_name(TEAM_CHANNEL).labels[0]
    options = outfit_options(SCHEME, team_colour, {}, [], get_uuid(), THRESHOLD)

    combos = [(o.appearance["tshirt"], o.appearance["trousers"]) for o in options]
    assert len(combos) == len(set(combos))


def test_collapsed_survivor_is_the_best_ranked_of_its_armband_group():
    """Pin the wardrobe to a single tshirt+trousers pair, so every raw
    candidate before collapsing differs only in armband colour, and check
    the one option kept really is the best of that 7-armband-wide group
    (fewest overrides needed against a real slot), not just the first seen.
    """
    team_colour = SCHEME.channels.by_name(TEAM_CHANNEL).labels[0]
    tshirt = SCHEME.channels.by_name("tshirt").labels[0]
    trousers = palette_for_channel("trousers")[0]
    wardrobe = {"tshirt": [tshirt], "trousers": [trousers]}

    options = outfit_options(SCHEME, team_colour, wardrobe, [], get_uuid(), 0)
    assert len(options) == 1
    survivor = options[0]
    assert (survivor.appearance["tshirt"], survivor.appearance["trousers"]) == (
        tshirt,
        trousers,
    )

    def overrides_needed_for(armband):
        appearance = {
            "tshirt": tshirt,
            "trousers": trousers,
            TEAM_CHANNEL: team_colour,
            PROVIDED_CHANNEL: armband,
        }
        word = tuple(
            SCHEME.channels.by_name(name).label_to_index(appearance[name])
            for name in SCHEME.channels.names
        )
        slot = nearest_slots(word, SCHEME)[0]
        return len(overrides_for(word, slot, SCHEME))

    best_possible = min(
        overrides_needed_for(armband)
        for armband in SCHEME.channels.by_name(PROVIDED_CHANNEL).labels
    )
    assert survivor.overrides_needed == best_possible


# ---------------------------------------------------------------------------
# GET /api/join_options
# ---------------------------------------------------------------------------


def test_join_options_serves_palette_and_colour_notes_and_creates_no_user_row(
    api_client_factory, admin_api_client, db_session, one_game, one_team
):
    url, colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    player = fresh_player(api_client_factory)
    user_id = UUID(player.get("/api/my_id").json())

    response = join_options_call(player, url)

    assert response.is_success
    body = response.json()
    assert body["team_colour"] == colour
    assert body["team_channel"] == TEAM_CHANNEL
    assert body["provided_channel"] == PROVIDED_CHANNEL
    assert set(body["wardrobe_channels"]) == {"tshirt", "trousers"}
    assert body["colour_notes"] == COLOUR_BUCKETS
    assert body["you"] is None

    # channels is _channels_payload verbatim - carries hex
    tshirt = next(c for c in body["channels"] if c["name"] == "tshirt")
    assert tshirt["hex"]["black"] == "#1A1A1A"

    # A team link prefetched by, say, a chat app's link-preview bot must not
    # burn an outfit or create a User row.
    assert db_session.get(User, user_id) is None


def test_join_options_reports_the_caller_once_they_have_picked(
    api_client_factory, admin_api_client, one_game, one_team
):
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    player = fresh_player(api_client_factory)

    options = outfit_options_call(player, url, wardrobe={}).json()["options"]
    picked = pick_outfit_call(
        player, url, wardrobe={}, appearance=options[0]["appearance"]
    )
    assert picked.is_success

    response = join_options_call(player, url)
    assert response.json()["you"]["slot"] == picked.json()["slot"]


# ---------------------------------------------------------------------------
# POST /api/outfit_options
# ---------------------------------------------------------------------------


def test_outfit_options_pagination_boundaries(
    api_client_factory, admin_api_client, one_game, one_team
):
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    player = fresh_player(api_client_factory)

    first_page = outfit_options_call(player, url, wardrobe={}, page=0).json()
    assert first_page["page_size"] == 12
    assert len(first_page["options"]) == 12
    total = first_page["total"]
    # 7 tshirt colours x 5 trousers colours, collapsed one-per-combination
    # (the open wardrobe space is ~245 before that collapse).
    assert total > 12

    last_page_index = (total - 1) // 12
    last_page = outfit_options_call(
        player, url, wardrobe={}, page=last_page_index
    ).json()
    assert 1 <= len(last_page["options"]) <= 12

    beyond = outfit_options_call(
        player, url, wardrobe={}, page=last_page_index + 5
    ).json()
    assert beyond["options"] == []
    assert beyond["total"] == total


def test_wardrobe_that_cannot_clear_threshold_returns_empty_then_relaxed_finds_distance_two(
    api_client_factory, admin_api_client, one_game, one_team
):
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)

    first_player = fresh_player(api_client_factory)
    first_options = outfit_options_call(first_player, url, wardrobe={}).json()[
        "options"
    ]
    first_pick = pick_outfit_call(
        first_player, url, wardrobe={}, appearance=first_options[0]["appearance"]
    )
    assert first_pick.is_success
    taken_appearance = first_pick.json()["effective_appearance"]
    t0, r0 = taken_appearance["tshirt"], taken_appearance["trousers"]
    r1 = next(c for c in palette_for_channel("trousers") if c != r0)

    # This wardrobe can only ever differ from the first player on trousers
    # and armband (tshirt is pinned to the same colour), so its ceiling is
    # distance 2 - distance 3 is structurally unreachable.
    second_player = fresh_player(api_client_factory)
    wardrobe = {"tshirt": [t0], "trousers": [r0, r1]}

    strict = outfit_options_call(second_player, url, wardrobe, relaxed=False).json()
    assert strict["options"] == []
    assert strict["exhausted"] is False

    relaxed = outfit_options_call(second_player, url, wardrobe, relaxed=True).json()
    assert relaxed["options"]
    assert all(o["min_distance"] == 2 for o in relaxed["options"])
    assert relaxed["exhausted"] is False


def test_three_teammates_declaring_only_black_all_get_distinct_outfits(
    api_client_factory, admin_api_client, one_game, one_team
):
    """plan §12.6: the design never refuses a player, even when three
    teammates all declare the same (maximally common) wardrobe."""
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    wardrobe = {"tshirt": ["black"], "trousers": ["black"]}

    slots = []
    for i in range(3):
        player = fresh_player(api_client_factory)
        body = outfit_options_call(player, url, wardrobe, relaxed=True).json()
        assert body["options"], f"player {i} was refused an outfit"
        if i > 0:
            # With every teammate restricted to black/black, only the first
            # player (nobody else placed yet) can clear even the relaxed
            # gate - everyone after that only gets anything via the
            # never-refuse fallback.
            assert body["exhausted"] is True

        pick = pick_outfit_call(
            player, url, wardrobe, appearance=body["options"][0]["appearance"]
        )
        assert pick.is_success
        slots.append(pick.json()["slot"])

    assert len(set(slots)) == 3


def test_outfit_options_rejects_out_of_palette_colour(
    api_client_factory, admin_api_client, one_game, one_team
):
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    player = fresh_player(api_client_factory)

    response = outfit_options_call(player, url, wardrobe={"tshirt": ["neonpink"]})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/pick_outfit
# ---------------------------------------------------------------------------


def test_pick_outfit_before_user_row_exists(
    api_client_factory, admin_api_client, db_session, one_game, one_team
):
    """plan §8.2: a client that only ever scans a link and never calls
    /api/user_info must still be able to pick."""
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    player = fresh_player(api_client_factory)

    user_id = UUID(player.get("/api/my_id").json())
    assert db_session.get(User, user_id) is None

    options = outfit_options_call(player, url, wardrobe={}).json()["options"]
    assert db_session.get(User, user_id) is None  # still no row after browsing options

    response = pick_outfit_call(
        player, url, wardrobe={}, appearance=options[0]["appearance"]
    )
    assert response.is_success

    db_session.expire_all()
    user = db_session.get(User, user_id)
    assert user is not None
    assert user.identity_slot == response.json()["slot"]


def test_pick_outfit_idempotent_revisit_sends_no_second_ticker_message(
    api_client_factory, admin_api_client, db_session, one_game, one_team
):
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    player = fresh_player(api_client_factory)

    options = outfit_options_call(player, url, wardrobe={}).json()["options"]
    first = pick_outfit_call(
        player, url, wardrobe={}, appearance=options[0]["appearance"]
    )
    assert first.is_success
    assert "min_distance" in first.json()
    slot = first.json()["slot"]

    # Re-visiting the team link is a no-op regardless of what's submitted -
    # the idempotent branch fires before the (bogus) appearance is even
    # looked at.
    second = pick_outfit_call(player, url, wardrobe={}, appearance={})
    assert second.is_success
    assert second.json()["slot"] == slot
    assert "min_distance" not in second.json()

    db_session.expire_all()
    join_messages = [
        t.message
        for t in db_session.query(TickerEntry).filter_by(game_id=one_game).all()
        if "joined team" in t.message
    ]
    assert len(join_messages) == 1


def test_pick_outfit_requires_confirmation(
    api_client_factory, admin_api_client, one_game, one_team
):
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    player = fresh_player(api_client_factory)

    options = outfit_options_call(player, url, wardrobe={}).json()["options"]
    response = pick_outfit_call(
        player, url, wardrobe={}, appearance=options[0]["appearance"], confirmed=False
    )

    assert response.status_code == 400
    assert "confirm" in response.json()["detail"].lower()


def test_pick_outfit_rejects_appearance_outside_declared_wardrobe(
    api_client_factory, admin_api_client, one_game, one_team
):
    """The client is not trusted: an appearance the wardrobe never offered is
    rejected exactly like a stale one, not silently substituted."""
    url, colour = team_join_url_and_colour(admin_api_client, one_game, one_team)
    player = fresh_player(api_client_factory)

    wardrobe = {"tshirt": ["black"], "trousers": ["black"]}
    fabricated = {
        "tshirt": "purple",
        "trousers": "black",
        "hat": colour,
        "armbands": "black",
    }

    response = pick_outfit_call(player, url, wardrobe, fabricated)
    assert response.status_code == 409


def test_pick_outfit_invalidated_underneath_returns_distinguishable_error(
    api_client_factory, admin_api_client, one_game, one_team
):
    """A choice invalidated by a race (someone else claims the exact same
    appearance first) must fail with the distinguishable "pick again" error,
    never a silently substituted outfit."""
    url, _colour = team_join_url_and_colour(admin_api_client, one_game, one_team)

    a = fresh_player(api_client_factory)
    b = fresh_player(api_client_factory)

    appearance = outfit_options_call(a, url, wardrobe={}).json()["options"][0][
        "appearance"
    ]

    # B claims the exact outfit A was shown, out from under them.
    assert pick_outfit_call(b, url, wardrobe={}, appearance=appearance).is_success

    response = pick_outfit_call(a, url, wardrobe={}, appearance=appearance)
    assert response.status_code == 409
    assert "again" in response.json()["detail"].lower()


def test_pick_outfit_rejects_per_slot_code(api_client_factory, one_game, one_team):
    slot = SCHEME.usable_slots()[0]
    per_slot_url = make_join_url(one_game, one_team, slot)
    player = fresh_player(api_client_factory)

    assert join_options_call(player, per_slot_url).status_code == 400
    assert outfit_options_call(player, per_slot_url, wardrobe={}).status_code == 400
    assert (
        pick_outfit_call(player, per_slot_url, wardrobe={}, appearance={}).status_code
        == 400
    )
