import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";

import OnboardingView from "./OnboardingView";
import {
  installFetchMock,
  getLastAPICall,
  grantAllPermissions,
  setPermission,
  makeUser,
  actAndFlush,
  proseFragment,
} from "./testUtils";
import prose from "./prose";

// A user with no team, for the steps that gate on webcam/location before a
// team even matters.
function soloUser(overrides = {}) {
  return makeUser({ team_id: null, team_name: null, ...overrides });
}

// The shape /user_info's outfit_wardrobe comes back in - see
// backend.user_interface._wardrobe_appearance.
const WHITE_GREEN_OUTFIT = {
  tshirt: { colour: "white", hex: "#ffffff" },
  trousers: { colour: "green", hex: "#3f7d3f" },
};

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

function isWarn(text) {
  return /\bwarn\b/.test(stepButton(text).className);
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

  expect(
    screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(proseFragment(prose.onboardingView.webcamPermission)),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(proseFragment(prose.onboardingView.locationPermission)),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/team/i)).not.toBeInTheDocument();
});

test("the webcam step appears once the player has a name, with no later steps yet", async () => {
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(stepButton(prose.onboardingView.webcamPermission)).toBeInTheDocument();
  expect(isDone(prose.onboardingView.webcamPermission)).toBe(false);
  expect(
    screen.queryByText(proseFragment(prose.onboardingView.locationPermission)),
  ).not.toBeInTheDocument();
});

test("the location step appears once webcam permission is granted", async () => {
  setPermission("camera", "granted");
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(isDone(prose.onboardingView.webcamPermission)).toBe(true);
  expect(
    stepButton(prose.onboardingView.locationPermission),
  ).toBeInTheDocument();
  expect(isDone(prose.onboardingView.locationPermission)).toBe(false);
  expect(screen.queryByText(/team/i)).not.toBeInTheDocument();
});

test("the team step waits for a team, and the game step doesn't show yet", async () => {
  grantAllPermissions();
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(
    screen.getByText(proseFragment(prose.onboardingView.joinTeamPrompt(false))),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(prose.onboardingView.waitForGame),
  ).not.toBeInTheDocument();
});

test("the team step shows the team name once assigned, and the game step then appears", async () => {
  grantAllPermissions();
  await renderOnboarding(
    makeUser({ name: "Bob", team_id: "team-9", team_name: "Blue Team" }),
  );

  expect(
    screen.getByText(prose.onboardingView.inTeam("Blue Team")),
  ).toBeInTheDocument();
  expect(
    screen.getByText(prose.onboardingView.waitForGame),
  ).toBeInTheDocument();
});

test("the team step mentions the outfit when the player has an identity slot", async () => {
  grantAllPermissions();
  await renderOnboarding(
    makeUser({
      name: "Bob",
      team_id: "team-9",
      team_name: "Blue Team",
      identity_slot: 7,
      outfit_wardrobe: WHITE_GREEN_OUTFIT,
    }),
  );

  expect(
    screen.getByText(prose.onboardingView.inTeam("Blue Team", 7)),
  ).toBeInTheDocument();
});

test("with no outfit picked, the outfit step says so and is not marked done", async () => {
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(stepButton(prose.onboardingView.outfitNotChosen)).toBeInTheDocument();
  expect(isDone(prose.onboardingView.outfitNotChosen)).toBe(false);
});

// The sentence is split across several elements (a swatch sits between the
// colour and the garment name, per garment), so it can't be found as one
// getByText match - "Outfit:" is the row's own direct text and is enough to
// find the button; the rest is checked via its normalised textContent.
test("once an outfit is picked, the outfit step shows a done checkmark and the garments", async () => {
  await renderOnboarding(
    soloUser({
      name: "Bob",
      outfit_wardrobe: WHITE_GREEN_OUTFIT,
    }),
  );

  const button = stepButton("Outfit:");
  expect(button.textContent.replace(/\s+/g, " ").trim()).toBe(
    "Outfit: white t-shirt & green trousers",
  );
  expect(isDone("Outfit:")).toBe(true);
});

test("the outfit step shows a colour swatch for each garment, like the outfit picker", async () => {
  await renderOnboarding(
    soloUser({ name: "Bob", outfit_wardrobe: WHITE_GREEN_OUTFIT }),
  );

  const button = stepButton("Outfit:");
  const whiteSwatch = within(button).getByTitle("white");
  const greenSwatch = within(button).getByTitle("green");
  expect(whiteSwatch).toHaveStyle({ background: "#ffffff" });
  expect(greenSwatch).toHaveStyle({ background: "#3f7d3f" });
});

test("the name box is pre-filled with an existing name", async () => {
  await renderOnboarding(makeUser({ name: "Zara" }));

  expect(
    screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
  ).toHaveValue("Zara");
});

test("clicking the name button POSTs set_name with the typed name", async () => {
  installFetchMock({ set_name: {} });
  await renderOnboarding(
    makeUser({ name: null, team_id: null, team_name: null }),
  );

  fireEvent.change(
    screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
    {
      target: { value: "Newname" },
    },
  );
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

  const input = screen.getByPlaceholderText(
    prose.onboardingView.namePlaceholder,
  );
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

  const input = screen.getByPlaceholderText(
    prose.onboardingView.namePlaceholder,
  );
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

  fireEvent.blur(
    screen.getByPlaceholderText(prose.onboardingView.namePlaceholder),
  );

  expect(getLastAPICall("set_name")).toBeUndefined();
});

test("a saved name shows a checkmark, not just a colour change", async () => {
  await renderOnboarding(
    makeUser({ name: "Zara", team_id: null, team_name: null }),
  );

  // The name entry's own action button swaps to the same checkmark icon
  // every other done onboarding step uses, instead of always showing the
  // return arrow.
  const input = screen.getByPlaceholderText(
    prose.onboardingView.namePlaceholder,
  );
  const icon = input.parentElement.querySelector("img");
  expect(icon.getAttribute("src")).toContain("check-solid");
});

test("steps already satisfied on mount render as done without any click", async () => {
  grantAllPermissions();
  await renderOnboarding(
    makeUser({ name: "Ann", team_id: "team-1", team_name: "Alpha" }),
  );

  expect(isDone(prose.onboardingView.webcamPermission)).toBe(true);
  expect(isDone(prose.onboardingView.locationPermission)).toBe(true);
  expect(isDone(prose.onboardingView.inTeam("Alpha"))).toBe(true);
});

// --- Tests below this point actually click through the webcam/location
// steps, which latch src/utils.js's sticky webcam_granted/geolocation_granted
// flags. Keep them last in the file: once latched, isCameraPermissionGranted
// / isLocationPermissionGranted report "granted" for the rest of this file
// regardless of the mocked Permissions API state.

test("clicking the location step and being denied leaves it not done and shows a visible error", async () => {
  setPermission("camera", "granted");
  mockGeolocationDenied();
  await renderOnboarding(soloUser({ name: "Bob" }));

  await actAndFlush(() =>
    fireEvent.click(stepButton(prose.onboardingView.locationPermission)),
  );

  expect(window.navigator.geolocation.getCurrentPosition).toHaveBeenCalled();
  expect(isDone(prose.onboardingView.locationPermission)).toBe(false);
  expect(screen.queryByText(/team/i)).not.toBeInTheDocument();
  expect(
    screen.getByText(proseFragment(prose.onboardingView.locationError)),
  ).toBeInTheDocument();
});

test("tapping the location button fewer than five times does not bypass it", async () => {
  setPermission("camera", "granted");
  // getCurrentPosition is left as the default bare jest.fn() (see testUtils.js),
  // which never calls its success or error callback - modelling the iPhone
  // bug where the permission prompt never appears at all.
  await renderOnboarding(soloUser({ name: "Bob" }));

  const button = stepButton(prose.onboardingView.locationPermission);
  fireEvent.click(button);
  fireEvent.click(button);
  fireEvent.click(button);
  fireEvent.click(button);

  expect(isDone(prose.onboardingView.locationPermission)).toBe(false);
  expect(screen.queryByText(/team/i)).not.toBeInTheDocument();
});

test("tapping the location button five times in a row bypasses it, and unlocks the rest of onboarding", async () => {
  setPermission("camera", "granted");
  await renderOnboarding(soloUser({ name: "Bob" }));

  const button = stepButton(prose.onboardingView.locationPermission);
  for (let i = 0; i < 5; i++) {
    fireEvent.click(button);
  }

  const bypassedText = proseFragment(prose.onboardingView.locationSkipped);
  expect(isDone(bypassedText)).toBe(true);
  expect(isWarn(bypassedText)).toBe(true);
  expect(
    screen.getByText(proseFragment(prose.onboardingView.joinTeamPrompt(false))),
  ).toBeInTheDocument();
});

test("clicking the webcam step requests camera access and marks itself done", async () => {
  await renderOnboarding(soloUser({ name: "Bob" }));

  expect(isDone(prose.onboardingView.webcamPermission)).toBe(false);
  fireEvent.click(stepButton(prose.onboardingView.webcamPermission));

  await waitFor(() =>
    expect(isDone(prose.onboardingView.webcamPermission)).toBe(true),
  );
  expect(window.navigator.mediaDevices.getUserMedia).toHaveBeenCalled();
  // Once webcam is done, the location step should appear next.
  expect(
    stepButton(prose.onboardingView.locationPermission),
  ).toBeInTheDocument();
});

test("clicking the location step requests geolocation and marks itself done when granted", async () => {
  setPermission("camera", "granted");
  mockGeolocationSuccess();
  await renderOnboarding(soloUser({ name: "Bob" }));

  fireEvent.click(stepButton(prose.onboardingView.locationPermission));

  await waitFor(() =>
    expect(isDone(prose.onboardingView.locationPermission)).toBe(true),
  );
  expect(
    screen.getByText(proseFragment(prose.onboardingView.joinTeamPrompt(false))),
  ).toBeInTheDocument();
});

test("getCurrentPosition is called with a timeout, so a stuck fix cannot hang the button forever", async () => {
  setPermission("camera", "granted");
  mockGeolocationSuccess();
  await renderOnboarding(soloUser({ name: "Bob" }));

  await actAndFlush(() =>
    fireEvent.click(stepButton(prose.onboardingView.locationPermission)),
  );

  const options =
    window.navigator.geolocation.getCurrentPosition.mock.calls[0][2];
  expect(options.timeout).toBeGreaterThan(0);
});
