// The spectator screen. What is worth testing here is the wiring the screen
// depends on to stay honest while nobody is watching it: that it refreshes on
// the SSE bumps, that the adjudication sentence tracks the pipeline, and the
// two joins that are easy to get silently wrong (score by user id, armour as
// HP minus one).

import { render, screen, act, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import SpectatorView, {
  adjudicationStatus,
  hasConcluded,
  teamLetters,
} from "./SpectatorView";
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

    expect(screen.getByText("1 of 2 alive")).toBeInTheDocument();
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

// -- the team letter, which is what separates two near-identical hat colours --

describe("team letters", () => {
  test("gives teams that share an initial different letters", () => {
    // The reason the attribute exists: burgundy and rust are 14.2 dE2000
    // apart and read alike across a room, so the letter has to do the work.
    // With Blue holding "B", Burgundy must take something else.
    const letters = teamLetters([
      { id: "t1", name: "Blue Team" },
      { id: "t2", name: "Burgundy" },
      { id: "t3", name: "Rust" },
    ]);

    expect(letters.t1).toBe("B");
    expect(new Set(Object.values(letters)).size).toBe(3);
  });

  test("still gives a letter to a team with no usable name", () => {
    const letters = teamLetters([
      { id: "t1", name: "Red" },
      { id: "t2", name: "" },
    ]);

    expect(letters.t2).toBeTruthy();
    expect(letters.t2).not.toBe(letters.t1);
  });
});

// -- what counts as a conclusion, for the takeover ---------------------------

describe("hasConcluded", () => {
  test.each([
    ["nothing yet", {}, false],
    ["CharlesBot still looking", { state: "pending" }, false],
    ["CharlesBot has a reading", { state: "done" }, true],
    ["CharlesBot errored", { state: "error" }, true],
    // The design is explicit that escalating counts: it is news.
    ["escalating", { state: "done", escalation_state: "pending" }, true],
    ["resolved", { checked: true, result: "hit" }, true],
  ])("%s", (_name, shot, expected) => {
    expect(hasConcluded(shot)).toBe(expected);
  });
});

// -- the takeover and the face cycle -----------------------------------------
//
// Both are timer-driven, so these use fake timers and advance them by hand.
// renderScreen's real-timer flushing does not mix with that, so these mount
// the screen themselves.

describe("the takeover", () => {
  // state "pending" is a shot CharlesBot has picked up but not yet answered -
  // the state the takeover is built to sit in. (state null means nothing has
  // started at all, which reads as "Waiting for the admin".)
  const shot = (overrides) => ({
    id: "shot-new",
    time_created: new Date().toISOString(),
    shooter_name: "Zoe",
    target_name: null,
    checked: false,
    result: null,
    state: "pending",
    review: null,
    identification: null,
    escalation_state: null,
    escalation: null,
    ...overrides,
  });

  async function mountWith(initialShots) {
    let feed = initialShots;
    installFetchMock(world({ admin_get_recent_shots: () => feed }));

    await act(async () => {
      render(
        <MemoryRouter>
          <UpdateSSEConnection endpoint="sse_admin_updates" />
          <SpectatorView />
        </MemoryRouter>,
      );
      for (let i = 0; i < 8; i++) await Promise.resolve();
      jest.advanceTimersByTime(0);
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });

    return {
      async setFeed(next) {
        feed = next;
        await act(async () => {
          emitUpdate("shots");
          for (let i = 0; i < 8; i++) await Promise.resolve();
        });
      },
      async tick(ms) {
        await act(async () => {
          jest.advanceTimersByTime(ms);
          for (let i = 0; i < 8; i++) await Promise.resolve();
        });
      },
    };
  }

  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  // The same sentences appear in the sidebar feed, so assert on the overlay
  // itself rather than on text anywhere in the document.
  const takeover = () => document.querySelector(".shotTakeover");

  test("does not fire for shots that were already there on load", async () => {
    // Opening the page mid-game must not replay the last six shots at the room.
    await mountWith([shot({ id: "old-1" }), shot({ id: "old-2" })]);

    expect(takeover()).toBeNull();
  });

  test("fires for a shot that arrives afterwards, and follows it to a verdict", async () => {
    const screenApi = await mountWith([shot({ id: "old-1" })]);

    await screenApi.setFeed([shot({ id: "new-1" }), shot({ id: "old-1" })]);
    expect(
      within(takeover()).getByText("CharlesBot looking..."),
    ).toBeInTheDocument();

    // The verdict lands in the feed; the panel must follow it rather than
    // showing a snapshot taken when it popped.
    await screenApi.setFeed([
      shot({ id: "new-1", checked: true, result: "hit", target_name: "Kit" }),
      shot({ id: "old-1" }),
    ]);
    expect(within(takeover()).getByText("Hit on Kit")).toBeInTheDocument();
  });

  test("lets go on its own when nothing ever concludes", async () => {
    // CharlesBot is off unless a per-game toggle is on, so this is the
    // ordinary case: without the cap the first shot of the night would park
    // on screen for the rest of the evening.
    const screenApi = await mountWith([shot({ id: "old-1" })]);
    await screenApi.setFeed([
      shot({ id: "new-1", state: null }),
      shot({ id: "old-1" }),
    ]);

    expect(takeover()).not.toBeNull();

    // A stage at a time: each timeout is only scheduled once the previous
    // state change has re-rendered, so one bulk advance would not chain.
    await screenApi.tick(15050); // the cap, waiting -> resolving
    await screenApi.tick(3050); // the hold once resolved
    await screenApi.tick(350); // the exit

    expect(takeover()).toBeNull();
  });

  test("says how many are waiting, and never queues more than three", async () => {
    const screenApi = await mountWith([shot({ id: "old-1" })]);

    await screenApi.setFeed([
      shot({ id: "n1" }),
      shot({ id: "n2" }),
      shot({ id: "n3" }),
      shot({ id: "n4" }),
      shot({ id: "n5" }),
      shot({ id: "old-1" }),
    ]);

    // Three held, so two behind the one on screen
    expect(screen.getByText("2 more waiting")).toBeInTheDocument();
  });
});

describe("the face cycle", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  async function mount(shots) {
    installFetchMock(world({ admin_get_recent_shots: shots }));
    await act(async () => {
      render(
        <MemoryRouter>
          <UpdateSSEConnection endpoint="sse_admin_updates" />
          <SpectatorView />
        </MemoryRouter>,
      );
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });
  }

  const aShot = {
    id: "s1",
    shooter_name: "Zoe",
    target_name: "Kit",
    checked: true,
    result: "hit",
    state: "done",
  };

  test("swaps to the gallery once the map face has had its turn", async () => {
    await mount([aShot]);

    // The map face carries the roster; the gallery does not.
    expect(screen.getByTestId("map-view-admin")).toBeInTheDocument();

    await act(async () => {
      jest.advanceTimersByTime(90 * 1000 + 50);
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });

    expect(screen.queryByTestId("map-view-admin")).not.toBeInTheDocument();
  });

  test("stays on the map while there are no shots to show", async () => {
    // A photo wall with nothing on it is the first hour of every game.
    await mount([]);

    await act(async () => {
      jest.advanceTimersByTime(90 * 1000 + 50);
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });

    expect(screen.getByTestId("map-view-admin")).toBeInTheDocument();
  });
});
