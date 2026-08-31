import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import OnboardingView from "./OnboardingView";
import {
  installFetchMock,
  getLastAPICall,
  grantAllPermissions,
  setPermission,
  makeUser,
  actAndFlush,
} from "./testUtils";

// A user with no team, for the steps that gate on webcam/location before a
// team even matters.
function soloUser(overrides = {}) {
  return makeUser({ team_id: null, team_name: null, ...overrides });
}

// OnboardingView checks permissions on mount via two `.then()`-chained async
// functions (isCameraPermissionGranted / isLocationPermissionGranted), each
// itself awaiting navigator.permissions.query(...) - several microtask ticks
// deep. actAndFlush (see testUtils.js) drains enough ticks, inside one
// continuous act() call, for both to settle before a test asserts, so every
// test observes the settled state instead of racing the initial render.
async function renderOnboarding(user) {
  return actAndFlush(() => render(<OnboardingView user={user} />));
}

function stepButton(text) {
  return screen.getByText(text).closest("button");
}

function isDone(text) {
  return /\bdone\b/.test(stepButton(text).className);
}

function mockGeolocationSuccess() {
  window.navigator.geolocation.getCurrentPosition.mockImplementation(
    (success) => success({ coords: { latitude: 51.4, longitude: -0.3 } }),
  );
}

function mockGeolocationDenied() {
  window.navigator.geolocation.getCurrentPosition.mockImplementation(
    (_success, error) => error(new Error("denied")),
  );
}

test("with no name set, only the name entry is shown", async () => {
  await renderOnboarding(
    makeUser({ name: null, team_id: null, team_name: null }),
  );

  expect(screen.getByPlaceholderText("Enter your name...")).toBeInTheDocument();
  expect(screen.queryByText(/Grant webcam permission/)).not.toBeInTheDocument();
  expect(
    screen.queryByText(/Grant location permission/),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/team/i)).not.toBeInTheDocument();
});

test("the webcam step appears once the player has a name, with no later steps yet", async () => {
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(stepButton("Grant webcam permission:")).toBeInTheDocument();
  expect(isDone("Grant webcam permission:")).toBe(false);
  expect(
    screen.queryByText(/Grant location permission/),
  ).not.toBeInTheDocument();
});

test("the location step appears once webcam permission is granted", async () => {
  setPermission("camera", "granted");
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(isDone("Grant webcam permission:")).toBe(true);
  expect(stepButton("Grant location permission:")).toBeInTheDocument();
  expect(isDone("Grant location permission:")).toBe(false);
  expect(screen.queryByText(/team/i)).not.toBeInTheDocument();
});

test("the team step waits for a team, and the game step doesn't show yet", async () => {
  grantAllPermissions();
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(
    screen.getByText("Scan your team's join QR code with your camera app..."),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("Wait for game to start..."),
  ).not.toBeInTheDocument();
});

test("the team step shows the team name once assigned, and the game step then appears", async () => {
  grantAllPermissions();
  await renderOnboarding(
    makeUser({ name: "Bob", team_id: "team-9", team_name: "Blue Team" }),
  );

  expect(screen.getByText('You are in team "Blue Team"')).toBeInTheDocument();
  expect(screen.getByText("Wait for game to start...")).toBeInTheDocument();
});

test("the team step mentions the outfit when the player has an identity slot", async () => {
  grantAllPermissions();
  await renderOnboarding(
    makeUser({
      name: "Bob",
      team_id: "team-9",
      team_name: "Blue Team",
      identity_slot: 7,
    }),
  );

  expect(
    screen.getByText('You are in team "Blue Team" — outfit #7'),
  ).toBeInTheDocument();
});

test("the name box is pre-filled with an existing name", async () => {
  await renderOnboarding(makeUser({ name: "Zara" }));

  expect(screen.getByPlaceholderText("Enter your name...")).toHaveValue("Zara");
});

test("clicking the name button POSTs set_name with the typed name", async () => {
  installFetchMock({ set_name: {} });
  await renderOnboarding(
    makeUser({ name: null, team_id: null, team_name: null }),
  );

  fireEvent.change(screen.getByPlaceholderText("Enter your name..."), {
    target: { value: "Newname" },
  });
  fireEvent.click(screen.getByRole("button"));

  await waitFor(() => expect(getLastAPICall("set_name")).toBeDefined());
  expect(getLastAPICall("set_name").method).toBe("POST");
  // set_name takes "name" as a query param, not a JSON body - see
  // NameEntry's call to sendAPIRequest in OnboardingView.js.
  expect(getLastAPICall("set_name").query).toEqual({ name: "Newname" });
});

test("pressing Enter in the name box POSTs set_name with the typed name", async () => {
  installFetchMock({ set_name: {} });
  await renderOnboarding(
    makeUser({ name: null, team_id: null, team_name: null }),
  );

  const input = screen.getByPlaceholderText("Enter your name...");
  fireEvent.change(input, { target: { value: "EnterName" } });
  fireEvent.keyDown(input, { key: "Enter" });

  await waitFor(() => expect(getLastAPICall("set_name")).toBeDefined());
  expect(getLastAPICall("set_name").query).toEqual({ name: "EnterName" });
});

test("leaving the name box (blur) POSTs set_name, with no button tap or Enter needed", async () => {
  installFetchMock({ set_name: {} });
  await renderOnboarding(
    makeUser({ name: null, team_id: null, team_name: null }),
  );

  const input = screen.getByPlaceholderText("Enter your name...");
  fireEvent.change(input, { target: { value: "BlurName" } });
  fireEvent.blur(input);

  await waitFor(() => expect(getLastAPICall("set_name")).toBeDefined());
  expect(getLastAPICall("set_name").query).toEqual({ name: "BlurName" });
});

test("blurring an empty name box does not POST set_name", async () => {
  installFetchMock({ set_name: {} });
  await renderOnboarding(
    makeUser({ name: null, team_id: null, team_name: null }),
  );

  fireEvent.blur(screen.getByPlaceholderText("Enter your name..."));

  expect(getLastAPICall("set_name")).toBeUndefined();
});

test("a saved name shows a checkmark, not just a colour change", async () => {
  await renderOnboarding(
    makeUser({ name: "Zara", team_id: null, team_name: null }),
  );

  // The name entry's own action button swaps to the same checkmark icon
  // every other done onboarding step uses, instead of always showing the
  // return arrow.
  const input = screen.getByPlaceholderText("Enter your name...");
  const icon = input.parentElement.querySelector("img");
  expect(icon.getAttribute("src")).toContain("check-solid");
});

test("steps already satisfied on mount render as done without any click", async () => {
  grantAllPermissions();
  await renderOnboarding(
    makeUser({ name: "Ann", team_id: "team-1", team_name: "Alpha" }),
  );

  expect(isDone("Grant webcam permission:")).toBe(true);
  expect(isDone("Grant location permission:")).toBe(true);
  expect(isDone('You are in team "Alpha"')).toBe(true);
});

// --- Tests below this point actually click through the webcam/location
// steps, which latch src/utils.js's sticky webcam_granted/geolocation_granted
// flags. Keep them last in the file: once latched, isCameraPermissionGranted
// / isLocationPermissionGranted report "granted" for the rest of this file
// regardless of the mocked Permissions API state.

test("clicking the location step and being denied leaves it not done", async () => {
  setPermission("camera", "granted");
  mockGeolocationDenied();
  await renderOnboarding(soloUser({ name: "Bob" }));

  await actAndFlush(() =>
    fireEvent.click(stepButton("Grant location permission:")),
  );

  expect(window.navigator.geolocation.getCurrentPosition).toHaveBeenCalled();
  expect(isDone("Grant location permission:")).toBe(false);
  expect(screen.queryByText(/team/i)).not.toBeInTheDocument();
});

test("clicking the webcam step requests camera access and marks itself done", async () => {
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(isDone("Grant webcam permission:")).toBe(false);
  fireEvent.click(stepButton("Grant webcam permission:"));

  await waitFor(() => expect(isDone("Grant webcam permission:")).toBe(true));
  expect(window.navigator.mediaDevices.getUserMedia).toHaveBeenCalled();
  // Once webcam is done, the location step should appear next.
  expect(stepButton("Grant location permission:")).toBeInTheDocument();
});

test("clicking the location step requests geolocation and marks itself done when granted", async () => {
  setPermission("camera", "granted");
  mockGeolocationSuccess();
  await renderOnboarding(soloUser({ name: "Bob" }));

  fireEvent.click(stepButton("Grant location permission:"));

  await waitFor(() => expect(isDone("Grant location permission:")).toBe(true));
  expect(
    screen.getByText("Scan your team's join QR code with your camera app..."),
  ).toBeInTheDocument();
});
