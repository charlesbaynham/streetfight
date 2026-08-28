// Tests for the reference-photo kit check: the roster's per-player states,
// capturing a photo against a player, and the verdict the admin actually acts
// on at the door (recognised / recognised as somebody else / nothing to check
// against, plus a channel the model was only half sure of).

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import {
  actAndFlush,
  emitUpdate,
  getAPICalls,
  getLastAPICall,
  installFetchMock,
} from "./testUtils";

import ReferencePhotos from "./ReferencePhotos";

// The real webcam wants a camera, a canvas and a <video> jsdom cannot play.
// Stand in for it with something that hands back a frame when the trigger
// changes - the same contract MyWebcam's onCapture prop has.
jest.mock("./MyWebcam", () => {
  const React = require("react");
  return {
    MyWebcam: ({ trigger, onCapture }) => {
      const fired = React.useRef(null);
      React.useEffect(() => {
        if (trigger && fired.current !== trigger) {
          fired.current = trigger;
          onCapture("data:image/jpeg;base64,MOCKFRAME");
        }
      });
      return React.createElement("div", null, "Mock webcam");
    },
  };
});

const STORED_PHOTO = "data:image/jpeg;base64,STORED";

function makeRow(overrides = {}) {
  return {
    user_id: "user-1",
    name: "Alice",
    team_name: "Reds",
    has_photo: false,
    review_state: null,
    matches_expected: null,
    top_name: null,
    top_probability: null,
    ...overrides,
  };
}

function makeReview(overrides = {}) {
  return {
    outcome: "hit_player",
    outcome_reason: "a person fills the frame",
    reasoning: "clear view of the armbands",
    confidence: 0.9,
    zoom_used: false,
    zoom_count: 0,
    channels: {
      tshirt: {
        visible: true,
        colour: "black",
        confidence: 0.9,
        hex: "#1A1A1A",
      },
      trousers: {
        visible: true,
        colour: "blue",
        confidence: 0.9,
        hex: "#0072CE",
      },
    },
    identification: {
      ranked: [
        { user_id: "user-1", name: "Alice", probability: 0.93 },
        { user_id: "user-2", name: "Bob", probability: 0.05 },
      ],
      expected_user_id: "user-1",
      matches_expected: true,
      confident: true,
      ambiguous: false,
      inconsistent: false,
    },
    ...overrides,
  };
}

// The photo endpoint returns a bare JSON string, so it has to go over the
// mock as JSON text rather than as an already-parsed body.
function jsonString(value) {
  return { status: 200, body: JSON.stringify(value) };
}

function installReferenceMock(
  { rows, state = null, review = null },
  extra = {},
) {
  installFetchMock({
    admin_is_authed: true,
    admin_get_shots_info: [],
    admin_list_games: [{ id: "game-1", teams: [{ name: "Reds" }] }],
    admin_get_reference_photo_status: rows,
    admin_get_reference_photo: jsonString(STORED_PHOTO),
    admin_get_reference_review: { state, review },
    admin_capture_reference_photo: jsonString("user-1"),
    admin_review_reference_photo: { queued: true },
    admin_delete_reference_photo: jsonString("user-1"),
    ...extra,
  });
}

async function renderPage() {
  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ReferencePhotos />
      </MemoryRouter>,
    ),
  );
}

async function openPlayer(name) {
  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("button", { name: new RegExp(name) })),
  );
}

describe("the roster", () => {
  test("shows each player's kit-check state", async () => {
    installReferenceMock({
      rows: [
        makeRow({ user_id: "user-1", name: "Alice" }),
        makeRow({
          user_id: "user-2",
          name: "Bob",
          has_photo: true,
          review_state: "pending",
        }),
        makeRow({
          user_id: "user-3",
          name: "Carol",
          has_photo: true,
          review_state: "done",
          matches_expected: true,
          top_name: "Carol",
          top_probability: 0.93,
        }),
        makeRow({
          user_id: "user-4",
          name: "Dan",
          has_photo: true,
          review_state: "done",
          matches_expected: false,
          top_name: "Erin",
          top_probability: 0.71,
        }),
        makeRow({
          user_id: "user-5",
          name: "Erin",
          has_photo: true,
          review_state: "done",
          matches_expected: null,
        }),
        makeRow({
          user_id: "user-6",
          name: "Frank",
          has_photo: true,
          review_state: "error",
        }),
      ],
    });

    await renderPage();

    expect(screen.getByText("No photo yet")).toBeInTheDocument();
    expect(screen.getByText("Reviewing...")).toBeInTheDocument();
    expect(screen.getByText("✓ Recognised (p=0.93)")).toBeInTheDocument();
    expect(screen.getByText("✗ Reads as Erin (p=0.71)")).toBeInTheDocument();
    expect(screen.getByText("No outfit picked")).toBeInTheDocument();
    expect(screen.getByText("Review failed")).toBeInTheDocument();

    expect(getLastAPICall("admin_get_reference_photo_status").query).toEqual({
      game_id: "game-1",
    });
  });

  test("refreshes when the admin SSE stream says something changed", async () => {
    installReferenceMock({ rows: [makeRow()] });

    await renderPage();
    const before = getAPICalls("admin_get_reference_photo_status").length;

    await actAndFlush(() => emitUpdate("admin"));

    expect(
      getAPICalls("admin_get_reference_photo_status").length,
    ).toBeGreaterThan(before);
  });
});

describe("capturing", () => {
  test("posts the photographed frame against the player", async () => {
    installReferenceMock({ rows: [makeRow()] });

    await renderPage();
    await openPlayer("Alice");

    // No photo yet, so the camera is already up
    await actAndFlush(() =>
      fireEvent.click(screen.getByRole("button", { name: "Photograph Alice" })),
    );

    const call = getLastAPICall("admin_capture_reference_photo");
    expect(call.method).toBe("POST");
    expect(call.body).toEqual({
      user_id: "user-1",
      photo: "data:image/jpeg;base64,MOCKFRAME",
    });

    // ...and the stored photo is then shown back
    expect(
      screen.getByAltText("Alice in the kit they arrived in"),
    ).toHaveAttribute("src", STORED_PHOTO);
  });

  test("does not ask for a photo that has not been taken", async () => {
    installReferenceMock({ rows: [makeRow()] });

    await renderPage();
    await openPlayer("Alice");

    // The endpoint 404s when there is no photo, which would land in the admin
    // error log as if something had gone wrong.
    expect(getAPICalls("admin_get_reference_photo")).toHaveLength(0);
  });

  test("re-running the review and deleting the photo hit their endpoints", async () => {
    installReferenceMock({
      rows: [makeRow({ has_photo: true, review_state: "done" })],
      state: "done",
      review: makeReview(),
    });

    await renderPage();
    await openPlayer("Alice");

    await actAndFlush(() =>
      fireEvent.click(screen.getByRole("button", { name: "Re-run review" })),
    );
    expect(getLastAPICall("admin_review_reference_photo").query).toEqual({
      user_id: "user-1",
    });

    await actAndFlush(() =>
      fireEvent.click(screen.getByRole("button", { name: "Delete photo" })),
    );
    expect(getLastAPICall("admin_delete_reference_photo").query).toEqual({
      user_id: "user-1",
    });
    // Deleting leaves the camera up for a fresh one
    expect(
      screen.getByRole("button", { name: "Photograph Alice" }),
    ).toBeInTheDocument();
  });
});

describe("the verdict", () => {
  const doneRow = makeRow({ has_photo: true, review_state: "done" });

  test("a player recognised as themselves is a pass", async () => {
    installReferenceMock({
      rows: [doneRow],
      state: "done",
      review: makeReview(),
    });

    await renderPage();
    await openPlayer("Alice");

    expect(
      screen.getByText("Recognised as Alice (p=0.93)"),
    ).toBeInTheDocument();
    // The runners-up are there in small, so a close second is visible
    expect(screen.getByText(/Bob \(p=0.05\)/)).toBeInTheDocument();
  });

  test("a player recognised as somebody else names them", async () => {
    installReferenceMock({
      rows: [doneRow],
      state: "done",
      review: makeReview({
        identification: {
          ranked: [
            { user_id: "user-2", name: "Bob", probability: 0.71 },
            { user_id: "user-1", name: "Alice", probability: 0.2 },
          ],
          expected_user_id: "user-1",
          matches_expected: false,
          confident: true,
          ambiguous: false,
          inconsistent: false,
        },
      }),
    });

    await renderPage();
    await openPlayer("Alice");

    expect(
      screen.getByText("Reads as Bob (p=0.71), not Alice"),
    ).toBeInTheDocument();
  });

  test("a player with no outfit cannot be checked, and says so", async () => {
    installReferenceMock({
      rows: [doneRow],
      state: "done",
      review: makeReview({
        identification: {
          ranked: [{ user_id: "user-2", name: "Bob", probability: 0.6 }],
          expected_user_id: null,
          matches_expected: null,
          confident: false,
          ambiguous: false,
          inconsistent: false,
        },
      }),
    });

    await renderPage();
    await openPlayer("Alice");

    expect(screen.getByText(/has not picked an outfit/)).toBeInTheDocument();
    expect(screen.getByText(/not a confident reading/)).toBeInTheDocument();
  });

  test("a channel the model was only half sure of is flagged", async () => {
    installReferenceMock({
      rows: [doneRow],
      state: "done",
      review: makeReview({
        channels: {
          trousers: {
            visible: true,
            colour: "black",
            confidence: 0.4,
            hex: "#1A1A1A",
          },
        },
      }),
    });

    await renderPage();
    await openPlayer("Alice");

    expect(
      screen.getByText(/trousers read as black at 0.40/),
    ).toBeInTheDocument();
    expect(screen.getByText(/trousers: black \(40%\)/)).toBeInTheDocument();
  });

  test("a failed review is shown rather than an empty panel", async () => {
    installReferenceMock({
      rows: [makeRow({ has_photo: true, review_state: "error" })],
      state: "error",
      review: { error: "the model fell over" },
    });

    await renderPage();
    await openPlayer("Alice");

    expect(
      screen.getByText(/Review failed: the model fell over/),
    ).toBeInTheDocument();
  });
});
