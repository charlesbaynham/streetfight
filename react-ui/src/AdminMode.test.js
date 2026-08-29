import fs from "fs";
import path from "path";

import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import AdminMode, { weaponName } from "./AdminMode";
import {
  installFetchMock,
  getAPICalls,
  getLastAPICall,
  emitUpdate,
  makeUser,
  makeTeam,
  makeGame,
  actAndFlush,
} from "./testUtils";

// These panels aren't what's under test here (Circles, the ticker feed, the
// item QR generator, the live player map) and each does its own polling /
// fetching that would just be unrelated noise in every assertion below.
jest.mock("./NewItems", () => () => <div data-testid="new-items-stub" />);
jest.mock("./CircleControl", () => () => (
  <div data-testid="circle-control-stub" />
));
jest.mock("./TickerView", () => () => <div data-testid="ticker-view-stub" />);
jest.mock("./MapView", () => ({
  MapViewAdmin: () => <div data-testid="map-view-admin-stub" />,
}));

// ---------------------------------------------------------------------------
// weaponName
// ---------------------------------------------------------------------------

describe("weaponName", () => {
  test.each([
    [{ shot_damage: 0, shot_timeout: 6 }, "No weapon"],
    [{ shot_damage: 1, shot_timeout: 6 }, "Pewster"],
    [{ shot_damage: 2, shot_timeout: 6 }, "Tracka-Tracka"],
    [{ shot_damage: 3, shot_timeout: 6 }, "OMG"],
    [{ shot_damage: 1, shot_timeout: 1 }, "Eat-a-bullet"],
  ])("maps %j to %s", (user, expected) => {
    expect(weaponName(user)).toBe(expected);
  });

  test("returns null for a damage/timeout combination not in the table", () => {
    expect(weaponName({ shot_damage: 9, shot_timeout: 9 })).toBeNull();
    expect(weaponName({ shot_damage: 2, shot_timeout: 1 })).toBeNull();
  });

  // The frontend keeps its own copy of the backend's WEAPON_NAME_LOOKUP
  // (comment above WEAPONS in AdminMode.js says so) instead of fetching it,
  // so nothing catches the two drifting apart except a test that reads both.
  test("matches WEAPON_NAME_LOOKUP in backend/item_actions.py", () => {
    const backendSource = fs.readFileSync(
      path.join(__dirname, "..", "..", "backend", "item_actions.py"),
      "utf8",
    );
    const lookupBlock = backendSource.match(
      /WEAPON_NAME_LOOKUP = \{([\s\S]*?)\n\}/,
    );
    expect(lookupBlock).not.toBeNull(); // sanity: the parse itself didn't silently find nothing

    const backendEntries = [
      ...lookupBlock[1].matchAll(/\((\d+),\s*(\d+)\):\s*"([^"]+)"/g),
    ].map(([, damage, timeout, name]) => ({
      damage: Number(damage),
      timeout: Number(timeout),
      name,
    }));
    expect(backendEntries.length).toBeGreaterThan(0);

    // Every backend entry maps to the same name on the frontend...
    for (const { damage, timeout, name } of backendEntries) {
      expect(weaponName({ shot_damage: damage, shot_timeout: timeout })).toBe(
        name,
      );
    }

    // ...and the frontend doesn't recognise anything the backend doesn't.
    const known = new Set(
      backendEntries.map((e) => `${e.damage},${e.timeout}`),
    );
    for (let damage = 0; damage <= 4; damage++) {
      for (const timeout of [0, 1, 2, 6, 7]) {
        if (!known.has(`${damage},${timeout}`)) {
          expect(
            weaponName({ shot_damage: damage, shot_timeout: timeout }),
          ).toBeNull();
        }
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Fixtures + rendering helper for the rest of AdminMode (UserControls,
// GamePanel, SendTickerMessage, PlayerRow, AdminPanel). These are all
// unexported, so they're exercised through the full <AdminMode /> tree.
// ---------------------------------------------------------------------------

function buildFixtures() {
  // Standard weapon (Pewster), alive.
  const pewsterUser = makeUser({
    id: "user-pewster",
    name: "Alice",
    team_id: "team-red",
    team_name: "Red",
    hit_points: 3,
    num_bullets: 5,
    shot_damage: 1,
    shot_timeout: 6,
  });
  // Non-standard damage/timeout combination, and dead - covers the skull
  // marker and the "raw figures" weapon fallback together.
  const customUser = makeUser({
    id: "user-custom",
    name: "Bob",
    team_id: "team-red",
    team_name: "Red",
    hit_points: 0,
    num_bullets: 1,
    shot_damage: 9,
    shot_timeout: 9,
  });
  // Has opened the app but isn't in any team yet.
  const noteamUser = makeUser({
    id: "user-noteam",
    name: "",
    team_id: null,
    team_name: null,
    hit_points: 2,
    num_bullets: 1,
    shot_damage: 1,
    shot_timeout: 6,
  });

  const redTeam = makeTeam({
    id: "team-red",
    name: "Red",
    game_id: "game-1",
    users: [pewsterUser, customUser],
  });
  const blueTeam = makeTeam({
    id: "team-blue",
    name: "Blue",
    game_id: "game-1",
    users: [],
  });

  const game1 = makeGame({
    id: "game-1",
    active: true,
    ai_shot_review_enabled: false,
    ai_auto_actions_enabled: false,
    teams: [redTeam, blueTeam],
  });

  return { pewsterUser, customUser, noteamUser, redTeam, blueTeam, game1 };
}

function defaultRoutes(fixtures) {
  return {
    admin_is_authed: true,
    admin_list_games: [fixtures.game1],
    get_users: [fixtures.pewsterUser, fixtures.customUser, fixtures.noteamUser],
    admin_get_shots_info: [],
    admin_set_hp: {},
    admin_hit_user: {},
    admin_give_ammo: {},
    admin_give_appeals: {},
    admin_set_weapon: {},
    admin_set_game_active: {},
    admin_set_ai_shot_review: {},
    admin_set_ai_auto_actions: {},
    admin_set_ai_escalation: {},
    admin_set_ai_resolve_everything: {},
    admin_reset_game: {},
    admin_create_team: {},
    admin_set_team_name: {},
    admin_send_custom_ticker_message: {},
    admin_set_user_name: {},
    admin_add_user_to_team: {},
    admin_delete_user: {},
    admin_create_game: {},
    admin_dump_images: {},
    // Only free_slots is read by AdminMode (PlayerRow's slot picker); the
    // real report carries more fields but they'd be dead weight here.
    admin_identity_report: { free_slots: [3, 5, 9] },
  };
}

// A passive effect (like UpdateListener's SSE registration, which has no
// dependency array and re-subscribes on every render) can still be pending
// the tick after RTL's findBy*/waitFor resolves against the DOM update -
// yielding a macrotask here lets it settle before a test fires an SSE event
// that depends on it already being registered.
async function flushEffects() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

// Renders <AdminMode/> and waits for the admin panel itself (not just the
// login gate) to have mounted.
async function renderAdmin(routeOverrides = {}, fixtures = buildFixtures()) {
  installFetchMock({ ...defaultRoutes(fixtures), ...routeOverrides });
  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <AdminMode />
      </MemoryRouter>,
    ),
  );
  await screen.findByRole("heading", { level: 1, name: "Admin" });
  await flushEffects();
  return fixtures;
}

// Locates a PlayerRow <li> by the user's id, which PlayerRow always renders
// verbatim in a <code> tag - the one place in the tree guaranteed to show the
// bare id (UserControls only falls back to the id when the player is
// unnamed).
function playerRowFor(userId) {
  return screen.getByText(userId).closest("li");
}

// Unnamed players are hidden by default (this is the behaviour under test in
// the "unnamed players" describe block below) - tests that need to interact
// with one reveal it via this checkbox first.
function showUnnamedPlayers() {
  userEvent.click(
    screen.getByRole("checkbox", { name: /Show unnamed players/ }),
  );
}

// ---------------------------------------------------------------------------
// UserControls
// ---------------------------------------------------------------------------

describe("UserControls", () => {
  test("shows HP, ammo and weapon name, with a skull marker at zero HP", async () => {
    await renderAdmin();

    const aliceRow = screen.getByText("Alice").closest("li");
    expect(aliceRow).toHaveTextContent("3 HP");
    expect(aliceRow).toHaveTextContent("5 ammo");
    expect(aliceRow).toHaveTextContent("Pewster");
    expect(aliceRow).not.toHaveTextContent("\u{1F480}");

    const bobRow = screen.getByText("Bob").closest("li");
    expect(bobRow).toHaveTextContent("\u{1F480}");
  });

  test("falls back to raw damage/timeout figures for a non-standard weapon", async () => {
    await renderAdmin();

    const bobRow = screen.getByText("Bob").closest("li");
    expect(bobRow).toHaveTextContent("9 dmg / 9s");
  });

  test("Kill posts admin_set_hp with num 0 for the right user", async () => {
    await renderAdmin();
    const aliceRow = screen.getByText("Alice").closest("li");

    userEvent.click(within(aliceRow).getByRole("button", { name: "Kill" }));

    await waitFor(() => expect(getLastAPICall("admin_set_hp")).toBeDefined());
    expect(getLastAPICall("admin_set_hp").query).toEqual({
      user_id: "user-pewster",
      num: "0",
    });
  });

  test("Hit (-1) posts admin_hit_user with num 1 for the right user", async () => {
    await renderAdmin();
    const aliceRow = screen.getByText("Alice").closest("li");

    userEvent.click(within(aliceRow).getByRole("button", { name: "Hit (-1)" }));

    await waitFor(() => expect(getLastAPICall("admin_hit_user")).toBeDefined());
    expect(getLastAPICall("admin_hit_user").query).toEqual({
      user_id: "user-pewster",
      num: "1",
    });
  });

  test("the numbered HP buttons post admin_set_hp with that value", async () => {
    await renderAdmin();
    const bobRow = screen.getByText("Bob").closest("li");

    userEvent.click(within(bobRow).getByRole("button", { name: "3" }));

    await waitFor(() => expect(getLastAPICall("admin_set_hp")).toBeDefined());
    expect(getLastAPICall("admin_set_hp").query).toEqual({
      user_id: "user-custom",
      num: "3",
    });
  });

  test("the ammo buttons post admin_give_ammo with +1/-1", async () => {
    await renderAdmin();
    const aliceRow = screen.getByText("Alice").closest("li");

    userEvent.click(within(aliceRow).getByRole("button", { name: "+1" }));
    await waitFor(() =>
      expect(getLastAPICall("admin_give_ammo").query).toEqual({
        user_id: "user-pewster",
        num: "1",
      }),
    );

    userEvent.click(within(aliceRow).getByRole("button", { name: "-1" }));
    await waitFor(() =>
      expect(getLastAPICall("admin_give_ammo").query).toEqual({
        user_id: "user-pewster",
        num: "-1",
      }),
    );
  });

  test("the appeals buttons post admin_give_appeals with +1/-1", async () => {
    await renderAdmin();
    const aliceRow = screen.getByText("Alice").closest("li");

    userEvent.click(
      within(aliceRow).getByRole("button", { name: "Appeals +1" }),
    );
    await waitFor(() =>
      expect(getLastAPICall("admin_give_appeals").query).toEqual({
        user_id: "user-pewster",
        num: "1",
      }),
    );

    userEvent.click(
      within(aliceRow).getByRole("button", { name: "Appeals -1" }),
    );
    await waitFor(() =>
      expect(getLastAPICall("admin_give_appeals").query).toEqual({
        user_id: "user-pewster",
        num: "-1",
      }),
    );
  });

  test("shows the appeal budget alongside the ammo count", async () => {
    await renderAdmin();

    expect(screen.getByText("Alice").closest("li")).toHaveTextContent(
      "3 appeals",
    );
  });

  test("the weapon dropdown posts admin_set_weapon with the selected name", async () => {
    await renderAdmin();
    const aliceRow = screen.getByText("Alice").closest("li");

    userEvent.selectOptions(
      within(aliceRow).getByRole("combobox"),
      "Tracka-Tracka",
    );

    await waitFor(() =>
      expect(getLastAPICall("admin_set_weapon")).toBeDefined(),
    );
    expect(getLastAPICall("admin_set_weapon").query).toEqual({
      user_id: "user-pewster",
      weapon: "Tracka-Tracka",
    });
  });

  test("offers a custom option only when the player's stats match no known weapon", async () => {
    await renderAdmin();

    const aliceRow = screen.getByText("Alice").closest("li"); // standard weapon
    expect(
      within(aliceRow).queryByRole("option", { name: "custom" }),
    ).not.toBeInTheDocument();
    expect(within(aliceRow).getByRole("combobox").value).toBe("Pewster");

    const bobRow = screen.getByText("Bob").closest("li"); // non-standard weapon
    expect(
      within(bobRow).getByRole("option", { name: "custom" }),
    ).toBeInTheDocument();
    expect(within(bobRow).getByRole("combobox").value).toBe("");
  });
});

// ---------------------------------------------------------------------------
// GamePanel
// ---------------------------------------------------------------------------

describe("GamePanel", () => {
  test("shows running status and pauses the game", async () => {
    await renderAdmin();

    expect(screen.getByText("running")).toBeInTheDocument();
    userEvent.click(screen.getByRole("button", { name: "Pause game" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_set_game_active")).toBeDefined(),
    );
    expect(getLastAPICall("admin_set_game_active").query).toEqual({
      game_id: "game-1",
      active: "false",
    });
  });

  test("shows paused status and starts the game", async () => {
    const fixtures = buildFixtures();
    fixtures.game1.active = false;
    await renderAdmin({}, fixtures);

    expect(screen.getByText("paused")).toBeInTheDocument();
    userEvent.click(screen.getByRole("button", { name: "Start game" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_set_game_active").query).toEqual({
        game_id: "game-1",
        active: "true",
      }),
    );
  });

  test("both AI checkboxes render with distinct labels", async () => {
    await renderAdmin();

    expect(
      screen.getByLabelText(/CharlesBot reviews shot photos automatically/),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/CharlesBot verdicts resolve shots automatically/),
    ).toBeInTheDocument();
  });

  test("the AI review checkbox reflects ai_shot_review_enabled and posts on toggle", async () => {
    await renderAdmin();

    const checkbox = screen.getByLabelText(
      /CharlesBot reviews shot photos automatically/,
    );
    expect(checkbox).not.toBeChecked();

    userEvent.click(checkbox);

    await waitFor(() =>
      expect(getLastAPICall("admin_set_ai_shot_review")).toBeDefined(),
    );
    expect(getLastAPICall("admin_set_ai_shot_review").query).toEqual({
      game_id: "game-1",
      enabled: "true",
    });
  });

  test("the AI auto-actions checkbox reflects ai_auto_actions_enabled and posts on toggle", async () => {
    await renderAdmin();

    const checkbox = screen.getByLabelText(
      /CharlesBot verdicts resolve shots automatically/,
    );
    expect(checkbox).not.toBeChecked();

    userEvent.click(checkbox);

    await waitFor(() =>
      expect(getLastAPICall("admin_set_ai_auto_actions")).toBeDefined(),
    );
    expect(getLastAPICall("admin_set_ai_auto_actions").query).toEqual({
      game_id: "game-1",
      enabled: "true",
    });
  });

  test("the resolve-everything checkbox reflects ai_resolve_everything_enabled and posts on toggle", async () => {
    await renderAdmin();

    const checkbox = screen.getByLabelText(
      /CharlesBot resolves every shot it can/,
    );
    expect(checkbox).not.toBeChecked();

    userEvent.click(checkbox);

    await waitFor(() =>
      expect(getLastAPICall("admin_set_ai_resolve_everything").query).toEqual({
        game_id: "game-1",
        enabled: "true",
      }),
    );
  });

  test("Reset game asks for confirmation first and does nothing if declined", async () => {
    await renderAdmin();
    window.confirm = jest.fn(() => false);

    userEvent.click(screen.getByRole("button", { name: "Reset game" }));

    // window.confirm blocks the click handler synchronously, so a declined
    // confirmation never reaches adminPost - nothing to await here.
    expect(window.confirm).toHaveBeenCalled();
    expect(getAPICalls("admin_reset_game")).toHaveLength(0);
  });

  test("Reset game passes the keep-weapons checkbox state when confirmed", async () => {
    await renderAdmin();
    window.confirm = jest.fn(() => true);

    // Default is checked - confirm it's actually sent as true first.
    userEvent.click(screen.getByRole("button", { name: "Reset game" }));
    await waitFor(() =>
      expect(getLastAPICall("admin_reset_game").query).toEqual({
        game_id: "game-1",
        keep_weapons: "true",
      }),
    );

    userEvent.click(screen.getByLabelText("keep weapons"));
    userEvent.click(screen.getByRole("button", { name: "Reset game" }));
    await waitFor(() =>
      expect(getLastAPICall("admin_reset_game").query).toEqual({
        game_id: "game-1",
        keep_weapons: "false",
      }),
    );
  });

  test("adding a team posts admin_create_team with the typed name and clears the input", async () => {
    await renderAdmin();

    const input = screen.getByPlaceholderText("New team name");
    userEvent.type(input, "Green");
    userEvent.click(screen.getByRole("button", { name: "Add team" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_create_team")).toBeDefined(),
    );
    expect(getLastAPICall("admin_create_team").query).toEqual({
      game_id: "game-1",
      team_name: "Green",
    });
    expect(input).toHaveValue("");
  });

  test("renaming a team posts admin_set_team_name with the typed name", async () => {
    await renderAdmin();

    const teamSection = screen
      .getByRole("heading", { level: 4, name: "Red" })
      .closest("div");
    const input = within(teamSection).getByRole("textbox", {
      name: "team name",
    });
    userEvent.clear(input);
    userEvent.type(input, "Crimson");
    userEvent.click(
      within(teamSection).getByRole("button", { name: "Rename team" }),
    );

    await waitFor(() =>
      expect(getLastAPICall("admin_set_team_name")).toBeDefined(),
    );
    expect(getLastAPICall("admin_set_team_name").query).toEqual({
      team_id: "team-red",
      name: "Crimson",
    });
  });

  test("teams and their players render", async () => {
    await renderAdmin();

    expect(
      screen.getByRole("heading", { level: 4, name: "Red" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 4, name: "Blue" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Alice").closest("li")).toBeInTheDocument();
    expect(screen.getByText("Bob").closest("li")).toBeInTheDocument();
    expect(
      screen.queryByText("No teams yet - add one below."),
    ).not.toBeInTheDocument();
  });

  test("shows an empty-state message when a game has no teams", async () => {
    const fixtures = buildFixtures();
    fixtures.game1.teams = [];
    await renderAdmin({}, fixtures);

    expect(
      screen.getByText("No teams yet - add one below."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// SendTickerMessage
// ---------------------------------------------------------------------------

describe("SendTickerMessage", () => {
  test("posts admin_send_custom_ticker_message and clears the input", async () => {
    await renderAdmin();

    const input = screen.getByPlaceholderText("Ticker announcement");
    userEvent.type(input, "Enemy spotted near the fountain");
    userEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_send_custom_ticker_message")).toBeDefined(),
    );
    expect(getLastAPICall("admin_send_custom_ticker_message").query).toEqual({
      game_id: "game-1",
      message: "Enemy spotted near the fountain",
    });
    expect(input).toHaveValue("");
  });
});

// ---------------------------------------------------------------------------
// PlayerRow
// ---------------------------------------------------------------------------

describe("PlayerRow", () => {
  test("shows the player's name and team", async () => {
    await renderAdmin();
    const row = playerRowFor("user-pewster");
    expect(row).toHaveTextContent("Alice");
    expect(row).toHaveTextContent("(Red)");
  });

  test('shows "unnamed" and "(no team)" for a player with neither', async () => {
    await renderAdmin();
    showUnnamedPlayers();
    const row = playerRowFor("user-noteam");
    expect(row).toHaveTextContent("unnamed");
    expect(row).toHaveTextContent("(no team)");
  });

  test("rename posts admin_set_user_name", async () => {
    await renderAdmin();
    const row = playerRowFor("user-pewster");

    const nameInput = within(row).getByPlaceholderText("name");
    userEvent.clear(nameInput);
    userEvent.type(nameInput, "Alicia");
    userEvent.click(within(row).getByRole("button", { name: "Rename" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_set_user_name")).toBeDefined(),
    );
    expect(getLastAPICall("admin_set_user_name").query).toEqual({
      user_id: "user-pewster",
      name: "Alicia",
    });
  });

  test('"Put in team" posts admin_add_user_to_team with the selected team, omitting slot when none is chosen', async () => {
    await renderAdmin();
    showUnnamedPlayers();
    const row = playerRowFor("user-noteam");

    userEvent.selectOptions(
      within(row).getByRole("combobox", { name: "team" }),
      "Blue",
    );
    userEvent.click(within(row).getByRole("button", { name: "Put in team" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_add_user_to_team")).toBeDefined(),
    );
    expect(getLastAPICall("admin_add_user_to_team").query).toEqual({
      user_id: "user-noteam",
      team_id: "team-blue",
    });
  });

  test("the slot select offers (no slot) plus the game's free slots", async () => {
    await renderAdmin();
    showUnnamedPlayers();
    const row = playerRowFor("user-noteam");

    const slotSelect = within(row).getByRole("combobox", { name: "slot" });
    await waitFor(() =>
      expect(
        within(slotSelect)
          .getAllByRole("option")
          .map((o) => o.textContent),
      ).toEqual(["(no slot)", "outfit #3", "outfit #5", "outfit #9"]),
    );
  });

  test("the slot select includes the player's current slot, labelled as current", async () => {
    const fixtures = buildFixtures();
    fixtures.customUser.identity_slot = 7;
    await renderAdmin({}, fixtures);
    const row = playerRowFor("user-custom");

    const slotSelect = within(row).getByRole("combobox", { name: "slot" });
    await waitFor(() =>
      expect(
        within(slotSelect)
          .getAllByRole("option")
          .map((o) => o.textContent),
      ).toEqual([
        "(no slot)",
        "outfit #3",
        "outfit #5",
        "outfit #7 (current)",
        "outfit #9",
      ]),
    );
  });

  test('"Put in team" includes the slot when one is chosen', async () => {
    await renderAdmin();
    showUnnamedPlayers();
    const row = playerRowFor("user-noteam");

    userEvent.selectOptions(
      within(row).getByRole("combobox", { name: "team" }),
      "Blue",
    );
    userEvent.selectOptions(
      within(row).getByRole("combobox", { name: "slot" }),
      "5",
    );
    userEvent.click(within(row).getByRole("button", { name: "Put in team" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_add_user_to_team")).toBeDefined(),
    );
    expect(getLastAPICall("admin_add_user_to_team").query).toEqual({
      user_id: "user-noteam",
      team_id: "team-blue",
      slot: "5",
    });
  });

  test("Delete asks for confirmation naming the player and does nothing if declined", async () => {
    await renderAdmin();
    window.confirm = jest.fn(() => false);
    const row = playerRowFor("user-pewster");

    userEvent.click(within(row).getByRole("button", { name: "Delete" }));

    expect(window.confirm).toHaveBeenCalledWith("Delete Alice entirely?");
    expect(getAPICalls("admin_delete_user")).toHaveLength(0);
  });

  test("Delete posts admin_delete_user once confirmed", async () => {
    await renderAdmin();
    window.confirm = jest.fn(() => true);
    const row = playerRowFor("user-pewster");

    userEvent.click(within(row).getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_delete_user")).toBeDefined(),
    );
    expect(getLastAPICall("admin_delete_user").query).toEqual({
      user_id: "user-pewster",
    });
  });
});

// ---------------------------------------------------------------------------
// AdminPanel
// ---------------------------------------------------------------------------

describe("AdminPanel", () => {
  test("shows a loading state with a Retry button before the games list arrives", async () => {
    // admin_list_games is deliberately left unmocked (404-ish forever), so
    // the panel never leaves its "games === null" loading state.
    installFetchMock({
      admin_is_authed: true,
      get_users: [],
      admin_get_shots_info: [],
    });
    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <AdminMode />
        </MemoryRouter>,
      ),
    );

    await screen.findByText("Loading...");
    const before = getAPICalls("admin_list_games").length;

    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Retry" })),
    );

    await waitFor(() =>
      expect(getAPICalls("admin_list_games").length).toBeGreaterThan(before),
    );
  });

  test("Create new game posts admin_create_game without confirmation when no game exists", async () => {
    const fixtures = buildFixtures();
    await renderAdmin({ admin_list_games: [] }, fixtures);
    window.confirm = jest.fn();

    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Create new game" })),
    );

    await waitFor(() =>
      expect(getAPICalls("admin_create_game")).toHaveLength(1),
    );
    expect(window.confirm).not.toHaveBeenCalled();
  });

  test("Create new game asks for confirmation when a game already exists, and aborts if declined", async () => {
    await renderAdmin();
    window.confirm = jest.fn(() => false);

    userEvent.click(screen.getByRole("button", { name: "Create new game" }));

    expect(window.confirm).toHaveBeenCalled();
    expect(getAPICalls("admin_create_game")).toHaveLength(0);
  });

  test("Create new game proceeds once confirmed when a game already exists", async () => {
    await renderAdmin();
    window.confirm = jest.fn(() => true);

    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Create new game" })),
    );

    await waitFor(() =>
      expect(getAPICalls("admin_create_game")).toHaveLength(1),
    );
  });

  test('everything refreshes when an "admin" SSE update arrives', async () => {
    await renderAdmin();

    const gamesBefore = getAPICalls("admin_list_games").length;
    const usersBefore = getAPICalls("get_users").length;

    await actAndFlush(() => emitUpdate("admin"));

    await waitFor(() => {
      expect(getAPICalls("admin_list_games").length).toBeGreaterThan(
        gamesBefore,
      );
      expect(getAPICalls("get_users").length).toBeGreaterThan(usersBefore);
    });
  });

  test("the Players section lists every named user, including those with no team", async () => {
    await renderAdmin();

    expect(playerRowFor("user-pewster")).toBeInTheDocument();
    expect(playerRowFor("user-custom")).toBeInTheDocument();
  });

  test("unnamed players are hidden by default but revealed by the checkbox", async () => {
    await renderAdmin();

    expect(screen.queryByText("user-noteam")).not.toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "Show unnamed players (1)" }),
    ).not.toBeChecked();

    showUnnamedPlayers();

    expect(playerRowFor("user-noteam")).toBeInTheDocument();
  });

  test("Download shot images (zip) posts admin_dump_images and downloads the response as a zip", async () => {
    await renderAdmin();

    userEvent.click(
      screen.getByRole("button", { name: "Download shot images (zip)" }),
    );

    await waitFor(() =>
      expect(getAPICalls("admin_dump_images")).toHaveLength(1),
    );
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledTimes(1));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });
});
