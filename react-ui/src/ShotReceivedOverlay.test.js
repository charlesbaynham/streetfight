import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import ShotReceivedOverlay from "./ShotReceivedOverlay";
import * as shotHistoryStore from "./shotHistoryStore";
import { getPlaySpy } from "./testMocks/useSound";
import { installFetchMock, makeShot, makeUser } from "./testUtils";

// The real modernizr module detects vibrate support once, at import time,
// against jsdom's real navigator - too early for testUtils' stubbed
// navigator.vibrate to have any effect. Mock it the way FireButton.test.js
// and ShotHistory.test.js do.
jest.mock("./modernizr", () => ({ vibrate: true }));

afterEach(async () => {
  // Give any in-flight fetch a macrotask to resolve inside act(), matching
  // ShotHistory.test.js's own afterEach.
  await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
});

// Populates the shared store the way ShotHistoryController normally would:
// both halves of the history, plus the shot image endpoint the overlay
// fetches once it knows which shot to show.
function seedShots({ received = [], fired = [], images = {} } = {}) {
  installFetchMock({
    user_shots: fired,
    user_shots_received: received,
    user_shot_image: ({ query }) => ({
      image_base64: images[query.shot_id] || "fallback-image-data",
    }),
  });
  return act(() => shotHistoryStore.refreshShots());
}

describe("ShotReceivedOverlay", () => {
  test("an unacknowledged received hit shows the shooter, the photo, and plays the hit sound", async () => {
    const shot = makeShot({
      direction: "received",
      result: "hit",
      shooter_name: "Ann",
    });
    await seedShots({ received: [shot], images: { [shot.id]: "abc123" } });

    render(<ShotReceivedOverlay user={makeUser({ hit_points: 2 })} />);

    expect(screen.getByText("You have been shot")).toBeInTheDocument();
    expect(screen.getByText("by Ann")).toBeInTheDocument();
    expect(await screen.findByAltText("The shot that hit you")).toHaveAttribute(
      "src",
      "abc123",
    );
    expect(screen.getByText("2 hit points left")).toBeInTheDocument();
    expect(getPlaySpy()).toHaveBeenCalledTimes(1);
    expect(navigator.vibrate).toHaveBeenCalledWith([200, 100, 200, 100, 400]);
  });

  test("omits the shooter line when shooter_name is null", async () => {
    const shot = makeShot({
      direction: "received",
      result: "hit",
      shooter_name: null,
    });
    await seedShots({ received: [shot] });

    render(<ShotReceivedOverlay user={makeUser()} />);

    expect(screen.getByText("You have been shot")).toBeInTheDocument();
    expect(screen.queryByText(/^by /)).not.toBeInTheDocument();
  });

  test.each([
    ["knocked out", { state: "knocked out" }, "You are knocked out"],
    ["dead", { state: "dead" }, "You are dead"],
    [
      "alive with 1 hit point",
      { state: "alive", hit_points: 1 },
      "1 hit point left",
    ],
  ])("says what the shot did: %s", async (_case, overrides, expected) => {
    const shot = makeShot({ direction: "received", result: "hit" });
    await seedShots({ received: [shot] });

    render(<ShotReceivedOverlay user={makeUser(overrides)} />);

    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  test("a received shot with no verdict yet shows nothing", async () => {
    const shot = makeShot({ direction: "received", result: null });
    await seedShots({ received: [shot] });

    const { container } = render(<ShotReceivedOverlay user={makeUser()} />);

    expect(container).toBeEmptyDOMElement();
    expect(getPlaySpy()).not.toHaveBeenCalled();
  });

  test("pressing OK hides it, and it stays hidden on a fresh mount", async () => {
    const shot = makeShot({ direction: "received", result: "hit" });
    await seedShots({ received: [shot] });

    const { unmount } = render(<ShotReceivedOverlay user={makeUser()} />);
    expect(screen.getByText("You have been shot")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    expect(screen.queryByText("You have been shot")).not.toBeInTheDocument();

    unmount();
    const { container } = render(<ShotReceivedOverlay user={makeUser()} />);
    expect(container).toBeEmptyDOMElement();
  });

  test("dismissing acknowledges older hits too, but a hit that lands after it still shows", async () => {
    const older = makeShot({
      direction: "received",
      result: "hit",
      time_created: "2026-08-15T10:00:00Z",
    });
    await seedShots({ received: [older] });

    render(<ShotReceivedOverlay user={makeUser()} />);
    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    expect(screen.queryByText("You have been shot")).not.toBeInTheDocument();

    // A second shot lands, newer than the one just dismissed - it must still
    // get its own overlay rather than being swept up by the dismissal.
    const newer = makeShot({
      direction: "received",
      result: "hit",
      time_created: "2026-08-15T10:05:00Z",
    });
    await seedShots({ received: [newer, older] });

    await waitFor(() =>
      expect(screen.getByText("You have been shot")).toBeInTheDocument(),
    );
    // Sound plays again for the new shot (once per shot shown).
    expect(getPlaySpy()).toHaveBeenCalledTimes(2);
  });

  test("Appeal this shot dismisses the overlay and opens the shot's history detail", async () => {
    const shot = makeShot({ direction: "received", result: "hit" });
    await seedShots({ received: [shot] });

    const openListener = jest.fn();
    window.addEventListener("streetfight:open-shot-history", openListener);

    render(<ShotReceivedOverlay user={makeUser()} />);
    fireEvent.click(screen.getByRole("button", { name: "Appeal this shot" }));

    expect(screen.queryByText("You have been shot")).not.toBeInTheDocument();
    expect(openListener).toHaveBeenCalledTimes(1);
    expect(openListener.mock.calls[0][0].detail).toEqual({ shotId: shot.id });

    window.removeEventListener("streetfight:open-shot-history", openListener);
  });
});
