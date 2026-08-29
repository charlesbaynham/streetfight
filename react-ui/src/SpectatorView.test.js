// The spectator screen. What is worth testing here is the wiring the screen
// depends on to stay honest while nobody is watching it: that it refreshes on
// the SSE bumps, that the adjudication sentence tracks the pipeline, and the
// two joins that are easy to get silently wrong (score by user id, armour as
// HP minus one).

import { render, screen, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import SpectatorView, { adjudicationStatus } from "./SpectatorView";
import { UpdateSSEConnection } from "./UpdateListener";
import {
  installFetchMock,
  getAPICalls,
  emitUpdate,
  makeGame,
  makeTeam,
  makeUser,
} from "./testUtils";

jest.mock("./MapView", () => ({
  MapViewSelf: () => <div>Mock MapViewSelf</div>,
  MapViewAdmin: (props) => (
    <div data-testid="map-view-admin" data-game-id={props.gameId || ""} />
  ),
}));

async function renderAndFlush(ui, ticks = 8) {
  let result;
  await act(async () => {
    result = render(ui);
    for (let i = 0; i < ticks; i++) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
  return result;
}

const ALICE = makeUser({
  id: "user-alice",
  name: "Alice",
  team_id: "team-red",
  hit_points: 3,
  num_bullets: 5,
});
const BOB = makeUser({
  id: "user-bob",
  name: "Bob",
  team_id: "team-red",
  state: "knocked out",
  hit_points: 0,
  time_of_death: Date.now() / 1000 + 120,
});

function world(overrides = {}) {
  return {
    admin_is_authed: true,
    admin_get_shots_info: [],
    admin_list_games: [
      makeGame({
        id: "game-1",
        active: true,
        teams: [
          makeTeam({
            id: "team-red",
            name: "Reds",
            identity_colour: "burgundy",
            users: [ALICE, BOB],
          }),
        ],
      }),
    ],
    admin_get_scoreboard: {
      table: [
        { user_id: "user-alice", name: "Alice", total_damage: 7 },
        { user_id: "user-bob", name: "Bob", total_damage: 2 },
      ],
    },
    admin_get_recent_shots: [],
    admin_ticker_messages: [],
    admin_identity_report: {
      team_channel: "hat",
      channels: [
        { name: "hat", labels: ["burgundy"], hex: { burgundy: "#A62C3E" } },
      ],
    },
    admin_get_shot_thumbnail: { image_base64: "data:image/jpeg;base64,AAA" },
    ...overrides,
  };
}

function renderScreen(overrides) {
  installFetchMock(world(overrides));
  return renderAndFlush(
    <MemoryRouter>
      <UpdateSSEConnection endpoint="sse_admin_updates" />
      <SpectatorView />
    </MemoryRouter>,
  );
}

describe("the roster", () => {
  test("shows armour as hit points minus one, and ammo", async () => {
    // There is no armour column; armour is HP above 1. Getting this wrong
    // would silently show everyone one point of armour they do not have.
    await renderScreen();

    expect(screen.getByText("2 armour")).toBeInTheDocument();
    expect(screen.getByText("5 ammo")).toBeInTheDocument();
  });

  test("joins each player's score by user id", async () => {
    await renderScreen();

    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  test("counts only the living in the headline", async () => {
    await renderScreen();

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText(/of 2 alive/)).toBeInTheDocument();
  });

  test("shows a knocked-out player's countdown instead of their stats", async () => {
    await renderScreen();

    expect(screen.getByText(/back in \d+:\d\d/)).toBeInTheDocument();
  });
});

describe("live updates", () => {
  test("refetches the game on an admin bump and the feed on a shots bump", async () => {
    await renderScreen();

    const gamesBefore = getAPICalls("admin_list_games").length;
    const shotsBefore = getAPICalls("admin_get_recent_shots").length;

    await act(async () => {
      emitUpdate("admin");
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(getAPICalls("admin_list_games").length).toBeGreaterThan(gamesBefore);

    await act(async () => {
      emitUpdate("shots");
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(getAPICalls("admin_get_recent_shots").length).toBeGreaterThan(
      shotsBefore,
    );
  });

  test("addresses the map at the active game rather than letting the backend guess", async () => {
    await renderScreen();

    expect(screen.getByTestId("map-view-admin")).toHaveAttribute(
      "data-game-id",
      "game-1",
    );
  });
});

describe("the shot feed", () => {
  const shot = (overrides) => ({
    id: "shot-1",
    time_created: new Date().toISOString(),
    shooter_name: "Alice",
    target_name: null,
    checked: false,
    result: null,
    state: null,
    review: null,
    identification: null,
    escalation_state: null,
    escalation: null,
    ...overrides,
  });

  test("shows the shooter and fetches the photograph once", async () => {
    // A name nobody on the roster has, so the assertion is about the feed.
    await renderScreen({
      admin_get_recent_shots: [shot({ shooter_name: "Zoe" })],
    });

    expect(screen.getByText("Zoe")).toBeInTheDocument();
    expect(getAPICalls("admin_get_shot_thumbnail")).toHaveLength(1);
  });

  test("does not refetch a photograph it already has", async () => {
    // The feed is refetched on every bump; the photos never change.
    await renderScreen({ admin_get_recent_shots: [shot({})] });

    await act(async () => {
      emitUpdate("shots");
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(getAPICalls("admin_get_shot_thumbnail")).toHaveLength(1);
  });

  // The pipeline, as the screen narrates it. Each row is a state a shot really
  // passes through in backend/ai_shot_review.py and backend/shot_escalation.py.
  test.each([
    ["waiting on the admin", {}, "Waiting for the admin", "warn"],
    [
      "CharlesBot working",
      { state: "pending" },
      "CharlesBot looking...",
      "thinking",
    ],
    [
      "escalated",
      { state: "done", escalation_state: "pending" },
      "Escalated to the stronger model...",
      "thinking",
    ],
    [
      "escalation broken",
      { state: "done", escalation_state: "error" },
      "Escalation failed - over to the admin",
      "warn",
    ],
    [
      "resolved as a hit",
      { checked: true, result: "hit", target_name: "Bob" },
      "Hit on Bob",
      "good",
    ],
    ["resolved as a miss", { checked: true, result: "miss" }, "Miss", "bad"],
    ["refunded", { checked: true, result: "refunded" }, "Refunded", "warn"],
  ])("says %s", (_name, overrides, expectedText, expectedTone) => {
    const [text, tone] = adjudicationStatus(shot(overrides));
    expect(text).toBe(expectedText);
    expect(tone).toBe(expectedTone);
  });

  test("relays CharlesBot's own verdict once it has one", async () => {
    const [text, tone] = adjudicationStatus(
      shot({
        state: "done",
        review: { outcome: "hit_player" },
        identification: {
          confident: true,
          ambiguous: false,
          inconsistent: false,
          ranked: [{ name: "Bob", probability: 0.9 }],
        },
      }),
    );

    expect(text).toBe("CharlesBot thinks: hit on Bob");
    expect(tone).toBe("thinking");
  });
});

describe("empty states", () => {
  test("says so when no shots have been fired", async () => {
    await renderScreen();
    expect(screen.getByText("No shots fired yet.")).toBeInTheDocument();
  });

  test("says so when there is no game at all", async () => {
    await renderScreen({ admin_list_games: [] });
    expect(screen.getByText("No games yet.")).toBeInTheDocument();
  });
});
