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
import prose from "./prose";

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

    expect(
      screen.getByText(prose.shotReceivedOverlay.headline),
    ).toBeInTheDocument();
    expect(
      screen.getByText(prose.shotReceivedOverlay.shooterBy("Ann")),
    ).toBeInTheDocument();
    // Same marked-up view as prose.shotHistory.listTitle (ShotThumbnail), crosshair included -
    // the player should be able to judge the call for themselves.
    expect(
      await screen.findByAltText(prose.shotHistory.yourShotAlt),
    ).toHaveAttribute("src", "abc123");
    expect(
      screen.getByText(prose.shotReceivedOverlay.hitPointsLeft(2)),
    ).toBeInTheDocument();
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

    expect(
      screen.getByText(prose.shotReceivedOverlay.headline),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^by /)).not.toBeInTheDocument();
  });

  test.each([
    [
      "knocked out",
      { state: "knocked out" },
      prose.shotReceivedOverlay.knockedOut,
    ],
    ["dead", { state: "dead" }, prose.shotReceivedOverlay.dead],
    [
      "alive with 1 hit point",
      { state: "alive", hit_points: 1 },
      prose.shotReceivedOverlay.hitPointsLeft(1),
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
    expect(
      screen.getByText(prose.shotReceivedOverlay.headline),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: prose.shotReceivedOverlay.okButton }),
    );
    expect(
      screen.queryByText(prose.shotReceivedOverlay.headline),
    ).not.toBeInTheDocument();

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
    fireEvent.click(
      screen.getByRole("button", { name: prose.shotReceivedOverlay.okButton }),
    );
    expect(
      screen.queryByText(prose.shotReceivedOverlay.headline),
    ).not.toBeInTheDocument();

    // A second shot lands, newer than the one just dismissed - it must still
    // get its own overlay rather than being swept up by the dismissal.
    const newer = makeShot({
      direction: "received",
      result: "hit",
      time_created: "2026-08-15T10:05:00Z",
    });
    await seedShots({ received: [newer, older] });

    await waitFor(() =>
      expect(
        screen.getByText(prose.shotReceivedOverlay.headline),
      ).toBeInTheDocument(),
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
    fireEvent.click(
      screen.getByRole("button", {
        name: prose.shotReceivedOverlay.appealButton,
      }),
    );

    expect(
      screen.queryByText(prose.shotReceivedOverlay.headline),
    ).not.toBeInTheDocument();
    expect(openListener).toHaveBeenCalledTimes(1);
    expect(openListener.mock.calls[0][0].detail).toEqual({ shotId: shot.id });

    window.removeEventListener("streetfight:open-shot-history", openListener);
  });
});
