import { MemoryRouter } from "react-router-dom";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";

import UserMode from "./UserMode";
import {
  installFetchMock,
  getAPICalls,
  getEventSources,
  emitUpdate,
  grantAllPermissions,
  setPermission,
  makeUser,
  actAndFlush,
  proseFragment,
} from "./testUtils";
import { setLocationBypass } from "./utils";
import prose from "./prose";

// WebcamView, MapView and FullscreenButton are heavy children that fight
// jsdom (real camera/canvas access, react-zoom-pan-pinch, add-to-homescreen).
// Stand in with simple markers so we can assert which view GetView chose and
// what props flow down to the webcam, without exercising that machinery.
jest.mock("./WebcamView", () => (props) => (
  <div
    data-testid="webcam-view"
    data-trigger={props.trigger}
    data-isdead={String(props.isDead)}
  />
));
jest.mock("./FullscreenButton", () => () => (
  <div data-testid="fullscreen-button" />
));
jest.mock("./MapView", () => ({
  MapViewSelf: () => <div data-testid="map-view-self" />,
}));

function renderUserMode(url = "/") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <UserMode />
    </MemoryRouter>,
  );
}

// Somebody who has never joined anything - every visitor gets a User row on
// their first load, so this is what a passer-by who scanned a card off a
// lamppost actually looks like.
function strangerUser(overrides = {}) {
  return makeUser({
    name: null,
    game_id: null,
    team_id: null,
    team_name: null,
    active: false,
    ...overrides,
  });
}

// GetView's permissionsGranted state starts false and only flips once its own
// mount-time permission check resolves, so every render - even one destined
// for the in-game HUD - transiently mounts (and un-mounts) OnboardingView
// first. OnboardingView runs its own separate permission-check effects on
// that transient mount; flushing here drains them before they can resolve
// unwrapped after a later assertion / the next test starts.
async function flushPendingEffects() {
  await act(async () => {});
}

function readyUser(overrides = {}) {
  return makeUser({
    name: "Test Player",
    active: true,
    state: "alive",
    team_id: "team-1",
    team_name: "Red",
    ...overrides,
  });
}

afterEach(() => {
  jest.useRealTimers();
});

test("shows Loading... before user_info has resolved", async () => {
  // No fetch mock installed - user_info 404s, so user stays null forever.
  // The 404 is expected and logged by sendAPIRequest itself; keep it out of
  // the test output.
  jest.spyOn(console, "dir").mockImplementation(() => {});
  await actAndFlush(renderUserMode);
  expect(screen.getByText(prose.userMode.loading)).toBeInTheDocument();

  await flushPendingEffects();
});

test("shows onboarding when the player has no name, even though everything else is ready", async () => {
  grantAllPermissions();
  installFetchMock({ user_info: readyUser({ name: null }), user_shots: [] });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(
      screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();
  expect(
    screen.queryByText(proseFragment(prose.bulletCount.ammoLabel)),
  ).not.toBeInTheDocument();
});

test("shows onboarding when the game is not active, even though everything else is ready", async () => {
  grantAllPermissions();
  installFetchMock({ user_info: readyUser({ active: false }), user_shots: [] });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(
      screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();
  expect(
    screen.queryByText(proseFragment(prose.bulletCount.ammoLabel)),
  ).not.toBeInTheDocument();
});

test("shows onboarding when permissions aren't granted, even though everything else is ready", async () => {
  // grantAllPermissions() deliberately not called - permissions stay "prompt".
  installFetchMock({ user_info: readyUser(), user_shots: [] });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(
      screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();
  expect(
    screen.queryByText(proseFragment(prose.bulletCount.ammoLabel)),
  ).not.toBeInTheDocument();
});

test("shows the in-game HUD when location was bypassed instead of granted", async () => {
  // Camera is properly granted, but location never was - the player tapped
  // through the onboarding gate's bypass instead (OnboardingView.js).
  setPermission("camera", "granted");
  setLocationBypass();
  installFetchMock({ user_info: readyUser(), user_shots: [] });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(
      screen.getByText(proseFragment(prose.bulletCount.ammoLabel)),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();
});

test("shows the in-game HUD for a living player once everything is satisfied", async () => {
  grantAllPermissions();
  installFetchMock({ user_info: readyUser(), user_shots: [] });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(
      screen.getByText(proseFragment(prose.bulletCount.ammoLabel)),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();
  expect(screen.getByTestId("webcam-view")).toBeInTheDocument();
  expect(
    screen.getByAltText(prose.fireButton.fireButtonAlt),
  ).toBeInTheDocument();
  // CrosshairImage has no alt text of its own; confirm via the fire button's
  // sibling instead - the fire button's presence already implies "alive".
  await flushPendingEffects();
});

test("a knocked-out player gets the knocked-out view, no fire button, and standalone scoreboard/shot-history buttons", async () => {
  grantAllPermissions();
  installFetchMock({
    user_info: readyUser({
      state: "knocked out",
      time_of_death: Date.now() / 1000 + 60,
    }),
    user_shots: [
      {
        id: "s1",
        checked: false,
        result: null,
        time_created: new Date().toISOString(),
      },
    ],
  });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(
      screen.getByText(prose.guideImages.knockedOutTitle),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();
  expect(
    screen.queryByAltText(prose.fireButton.fireButtonAlt),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(proseFragment(prose.bulletCount.ammoLabel)),
  ).not.toBeInTheDocument();

  const scoreboardButton = screen.getByRole("button", {
    name: proseFragment(prose.scoreboard.showScoresButton),
  });
  expect(scoreboardButton.className).toMatch(/standalone/);

  await waitFor(() =>
    expect(
      screen.getByRole("button", {
        name: proseFragment(prose.shotHistory.listTitle),
      }).className,
    ).toMatch(/standalone/),
  );
  // shotHistoryStore is a singleton not reset between tests; flush its
  // refreshShots() fetch fully so no update lands after this test ends.
  await flushPendingEffects();
});

test("a dead player gets the dead image, no fire button, and standalone scoreboard/shot-history buttons", async () => {
  grantAllPermissions();
  installFetchMock({
    user_info: readyUser({ state: "dead" }),
    user_shots: [
      {
        id: "s1",
        checked: false,
        result: null,
        time_created: new Date().toISOString(),
      },
    ],
  });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(screen.getByAltText(prose.guideImages.deadAlt)).toBeInTheDocument(),
  );
  await flushPendingEffects();
  expect(
    screen.queryByAltText(prose.fireButton.fireButtonAlt),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(proseFragment(prose.bulletCount.ammoLabel)),
  ).not.toBeInTheDocument();

  const scoreboardButton = screen.getByRole("button", {
    name: proseFragment(prose.scoreboard.showScoresButton),
  });
  expect(scoreboardButton.className).toMatch(/standalone/);

  await waitFor(() =>
    expect(
      screen.getByRole("button", {
        name: proseFragment(prose.shotHistory.listTitle),
      }).className,
    ).toMatch(/standalone/),
  );
  await flushPendingEffects();
});

test("firing the fire button changes the trigger passed to the webcam view", async () => {
  grantAllPermissions();
  installFetchMock({ user_info: readyUser(), user_shots: [] });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(
      screen.getByAltText(prose.fireButton.fireButtonAlt),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();
  expect(screen.getByTestId("webcam-view").dataset.trigger).toBe("0");

  fireEvent.click(
    screen.getByAltText(prose.fireButton.fireButtonAlt).closest("button"),
  );

  await waitFor(() =>
    expect(screen.getByTestId("webcam-view").dataset.trigger).toBe("1"),
  );
  await flushPendingEffects();
});

test("a 'user' SSE update triggers a refetch of user_info", async () => {
  grantAllPermissions();
  // The second user_info response differs observably (num_bullets) from the
  // first, so the refetch can be confirmed by what's on screen rather than
  // by a raw fetch call count - the count ticks up the instant the request
  // is *issued*, well before its response has actually been applied.
  installFetchMock({
    user_info: () =>
      readyUser({ num_bullets: getAPICalls("user_info").length <= 1 ? 5 : 99 }),
    user_shots: [],
  });
  await actAndFlush(renderUserMode);

  await waitFor(() => expect(screen.getByText(/x5/)).toBeInTheDocument());
  await flushPendingEffects();

  await actAndFlush(() => emitUpdate("user", getEventSources()[0]));

  await waitFor(() => expect(screen.getByText(/x99/)).toBeInTheDocument());
  await flushPendingEffects();
});

test("permissions are rechecked every 5s, and granting them moves the player off onboarding without a reload", async () => {
  jest.useFakeTimers();
  installFetchMock({ user_info: readyUser(), user_shots: [] });
  // Permissions start ungranted, so onboarding is shown first. Not using
  // actAndFlush here: it drains ticks via a real setTimeout, which never
  // fires once fake timers are installed above - the waitFor below is
  // fake-timer aware and drives the clock itself.
  renderUserMode();

  await waitFor(() =>
    expect(
      screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();

  grantAllPermissions();

  // The recheck interval fires every 5s; give waitFor plenty of virtual time
  // (it drives jest's fake timers itself) to get past that boundary.
  await waitFor(
    () =>
      expect(
        screen.getByText(proseFragment(prose.bulletCount.ammoLabel)),
      ).toBeInTheDocument(),
    {
      timeout: 8000,
    },
  );

  // Other permission-recheck rounds may still be settling (in-flight from
  // before permissions were granted); flush them before the test ends.
  await flushPendingEffects();
});

test("a visitor who has never joined anything gets the landing page, with no way in", async () => {
  grantAllPermissions();
  installFetchMock({ user_info: strangerUser(), user_shots: [] });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(screen.getByText(prose.whatIsThis.heading)).toBeInTheDocument(),
  );
  await flushPendingEffects();

  // The load-bearing half: nothing on this page starts a join.
  expect(
    screen.queryByPlaceholderText(prose.onboardingView.namePlaceholder),
  ).not.toBeInTheDocument();
  // And a passer-by is left holding no SSE stream. One is opened while
  // user_info is still in flight, since nothing yet says who this is; what
  // matters is that the landing page replacing the player view closes it
  // again rather than leaving the backend streaming keepalives at somebody
  // who is only reading (see the SSE note in CLAUDE.md).
  const CLOSED = 2;
  expect(
    getEventSources().filter((es) => es.readyState !== CLOSED),
  ).toHaveLength(0);
});

test("a player signed up to a game but not yet named gets onboarding, not the landing page", async () => {
  grantAllPermissions();
  installFetchMock({
    user_info: strangerUser({ game_id: "game-1" }),
    user_shots: [],
  });
  await actAndFlush(renderUserMode);

  await waitFor(() =>
    expect(
      screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
    ).toBeInTheDocument(),
  );
  await flushPendingEffects();
  expect(screen.queryByText(prose.whatIsThis.heading)).not.toBeInTheDocument();
});

test("somebody arriving with a join code is never shown the landing page, even if the join fails", async () => {
  grantAllPermissions();
  // join_game refuses, so JoinFromQueryParams strips the query and navigates
  // back to "/" - leaving a user who still looks exactly like a stranger.
  jest.spyOn(console, "dir").mockImplementation(() => {});
  installFetchMock({
    user_info: strangerUser(),
    user_shots: [],
    join_game: { status: 403, body: { detail: "No such game" } },
  });
  await actAndFlush(() => renderUserMode("/?j=somecode"));

  await waitFor(() => expect(getAPICalls("join_game")).toHaveLength(1));
  await flushPendingEffects();

  expect(screen.queryByText(prose.whatIsThis.heading)).not.toBeInTheDocument();
  expect(
    screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
  ).toBeInTheDocument();
});
