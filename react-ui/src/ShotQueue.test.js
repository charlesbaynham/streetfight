import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import ShotQueue, { rankShotCandidates } from "./ShotQueue";
import {
  installFetchMock,
  getAPICalls,
  getLastAPICall,
  emitUpdate,
  actAndFlush,
} from "./testUtils";

// ---------------------------------------------------------------------------
// rankShotCandidates - pure function, no rendering needed.
// ---------------------------------------------------------------------------

const EARTH_RADIUS_M = 6371e3; // matches the R used inside rankShotCandidates

// Degrees of latitude that correspond to exactly `metres` due north, on the
// same sphere the haversine calculation itself assumes - gives an exact
// expected distance to compare against, rather than an approximation.
function degreesNorthFor(metres) {
  return (metres / EARTH_RADIUS_M) * (180 / Math.PI);
}

function locationEntry(overrides) {
  return {
    user_id: "u-shooter",
    team_id: "t-red",
    user: "Someone",
    team: "Red",
    latitude: 51.5,
    longitude: -0.1,
    state: "alive",
    timestamp: 0,
    ...overrides,
  };
}

describe("rankShotCandidates", () => {
  test("excludes the shooting player from the candidate list", () => {
    const shot_data = {
      user_id: "u-shooter",
      location_context: JSON.stringify([
        locationEntry({ user_id: "u-shooter" }),
        locationEntry({ user_id: "u-other", user: "Other" }),
      ]),
    };

    const ranked = rankShotCandidates(shot_data);

    expect(ranked).toHaveLength(1);
    expect(ranked.map((u) => u.user_id)).not.toContain("u-shooter");
    expect(ranked[0].user_id).toBe("u-other");
  });

  test("computes plausible haversine distances from the shooter", () => {
    const shot_data = {
      user_id: "u-shooter",
      location_context: JSON.stringify([
        locationEntry({
          user_id: "u-shooter",
          latitude: 51.5,
          longitude: -0.1,
        }),
        locationEntry({
          user_id: "u-near",
          user: "Near Nancy",
          latitude: 51.5 + degreesNorthFor(500),
          longitude: -0.1,
        }),
      ]),
    };

    const [candidate] = rankShotCandidates(shot_data);

    // A pure north/south offset - well within the usual accuracy of consumer
    // GPS - so a metre or two of tolerance is plenty generous.
    expect(candidate.distance).toBeCloseTo(500, 0);
  });

  test("sorts candidates nearest-first", () => {
    const shot_data = {
      user_id: "u-shooter",
      location_context: JSON.stringify([
        locationEntry({
          user_id: "u-shooter",
          latitude: 51.5,
          longitude: -0.1,
        }),
        // Deliberately out of distance order in the source data.
        locationEntry({
          user_id: "u-far",
          user: "Far Fred",
          latitude: 51.5 + degreesNorthFor(2000),
          longitude: -0.1,
        }),
        locationEntry({
          user_id: "u-mid",
          user: "Mid Mary",
          latitude: 51.5 + degreesNorthFor(1000),
          longitude: -0.1,
        }),
        locationEntry({
          user_id: "u-near",
          user: "Near Nancy",
          latitude: 51.5 + degreesNorthFor(500),
          longitude: -0.1,
        }),
      ]),
    };

    const ranked = rankShotCandidates(shot_data);

    expect(ranked.map((u) => u.user_id)).toEqual(["u-near", "u-mid", "u-far"]);
    expect(ranked[0].distance).toBeLessThan(ranked[1].distance);
    expect(ranked[1].distance).toBeLessThan(ranked[2].distance);
  });
});

// ---------------------------------------------------------------------------
// Fixtures + rendering helper for ShotQueuePanel / ShotAiTags, exercised
// through the full <ShotQueue /> tree since neither is exported.
// ---------------------------------------------------------------------------

function makeShotDetail(id, overrides = {}) {
  return {
    id,
    user: { id: `${id}-shooter`, name: `Shooter of ${id}` },
    user_id: `${id}-shooter`,
    image_base64: `data:image/png;base64,${id}`,
    game: {
      teams: [
        {
          name: "Red",
          users: [{ id: `${id}-target-red`, name: "Target Red" }],
        },
        {
          name: "Blue",
          users: [{ id: `${id}-target-blue`, name: "Target Blue" }],
        },
      ],
    },
    location_context: JSON.stringify([
      locationEntry({ user_id: `${id}-shooter`, user: `Shooter of ${id}` }),
    ]),
    ...overrides,
  };
}

// Response for admin_get_shot_ai_review used whenever a test doesn't care
// about the AI tags themselves.
const NO_REVIEW_YET = { status: 200, body: { state: null, review: null } };

// A passive effect (like UpdateListener's SSE registration, which has no
// dependency array and re-subscribes on every render) can still be pending
// the tick after RTL's findBy*/waitFor resolves against the DOM update -
// yielding a macrotask here lets it settle before a test fires an SSE event
// that depends on it already being registered.
async function flushEffects() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("ShotQueuePanel", () => {
  let shotIds;
  let shotsById;

  beforeEach(() => {
    shotIds = ["shot-1", "shot-2", "shot-3"];
    shotsById = {
      "shot-1": makeShotDetail("shot-1"),
      "shot-2": makeShotDetail("shot-2"),
      "shot-3": makeShotDetail("shot-3"),
    };
  });

  async function renderQueue(routeOverrides = {}) {
    installFetchMock({
      admin_is_authed: true,
      admin_get_shots_info: () => shotIds,
      admin_get_shot: ({ query }) => shotsById[query.shot_id],
      admin_get_shot_ai_review: () => NO_REVIEW_YET,
      admin_shot_hit_user: {},
      admin_mark_shot_missed: {},
      admin_mark_shot_bystander: {},
      admin_refund_shot: {},
      admin_review_shot: {},
      ...routeOverrides,
    });
    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <ShotQueue />
        </MemoryRouter>,
      ),
    );
    await screen.findByText("Shot 1 of 3:");
    // The header (queue length) and the shot itself (loaded async, through
    // ShotCache) settle independently - wait for both before proceeding.
    await screen.findByAltText("The next shot in the queue");
    await flushEffects();
  }

  test("the header shows Shot <n> of <total>", async () => {
    await renderQueue();
    expect(screen.getByText("Shot 1 of 3:")).toBeInTheDocument();
  });

  test("Next / Previous move through the queue and clamp at both ends", async () => {
    await renderQueue();

    // Clamps at the start.
    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Previous" })),
    );
    expect(screen.getByText("Shot 1 of 3:")).toBeInTheDocument();

    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Next" })),
    );
    expect(screen.getByText("Shot 2 of 3:")).toBeInTheDocument();

    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Next" })),
    );
    expect(screen.getByText("Shot 3 of 3:")).toBeInTheDocument();

    // Clamps at the end.
    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Next" })),
    );
    expect(screen.getByText("Shot 3 of 3:")).toBeInTheDocument();

    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Previous" })),
    );
    expect(screen.getByText("Shot 2 of 3:")).toBeInTheDocument();
  });

  test("clamps the index down when the queue shrinks below it, rather than showing a blank panel", async () => {
    await renderQueue();

    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Next" })),
    );
    expect(screen.getByText("Shot 2 of 3:")).toBeInTheDocument();

    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Next" })),
    );
    expect(screen.getByText("Shot 3 of 3:")).toBeInTheDocument();

    // The two later shots get adjudicated away elsewhere; the next queue
    // refresh (triggered here via SSE) reports only one shot left.
    shotIds = ["shot-1"];
    await actAndFlush(() => emitUpdate("shots"));

    await waitFor(() =>
      expect(screen.getByText("Shot 1 of 1:")).toBeInTheDocument(),
    );
    // A shot is still shown, not a blank panel - the queue length and the
    // shot itself (loaded async, through ShotCache) settle independently.
    await waitFor(() =>
      expect(screen.getByText("By Shooter of shot-1")).toBeInTheDocument(),
    );
  });

  test("shows the shot photo and the shooting player's name", async () => {
    await renderQueue();

    expect(screen.getByText("By Shooter of shot-1")).toBeInTheDocument();
    expect(screen.getByAltText("The next shot in the queue")).toHaveAttribute(
      "src",
      "data:image/png;base64,shot-1",
    );
  });

  test("Hit posts admin_shot_hit_user with the shot id and the chosen target's id, then refreshes the queue", async () => {
    await renderQueue();
    const before = getAPICalls("admin_get_shots_info").length;

    const targetRow = screen.getByText("Target Red").closest("li");
    userEvent.click(within(targetRow).getByRole("button", { name: "Hit" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_shot_hit_user")).toBeDefined(),
    );
    expect(getLastAPICall("admin_shot_hit_user").query).toEqual({
      shot_id: "shot-1",
      target_user_id: "shot-1-target-red",
    });
    await waitFor(() =>
      expect(getAPICalls("admin_get_shots_info").length).toBeGreaterThan(
        before,
      ),
    );
  });

  test('"Missed" posts admin_mark_shot_missed for the shown shot, then refreshes', async () => {
    await renderQueue();
    const before = getAPICalls("admin_get_shots_info").length;

    userEvent.click(screen.getByRole("button", { name: "Missed" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_mark_shot_missed").query).toEqual({
        shot_id: "shot-1",
      }),
    );
    await waitFor(() =>
      expect(getAPICalls("admin_get_shots_info").length).toBeGreaterThan(
        before,
      ),
    );
  });

  test('"Bystander" posts admin_mark_shot_bystander for the shown shot, then refreshes', async () => {
    await renderQueue();
    const before = getAPICalls("admin_get_shots_info").length;

    userEvent.click(screen.getByRole("button", { name: "Bystander" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_mark_shot_bystander").query).toEqual({
        shot_id: "shot-1",
      }),
    );
    await waitFor(() =>
      expect(getAPICalls("admin_get_shots_info").length).toBeGreaterThan(
        before,
      ),
    );
  });

  test('"Refund" posts admin_refund_shot for the shown shot, then refreshes', async () => {
    await renderQueue();
    const before = getAPICalls("admin_get_shots_info").length;

    userEvent.click(screen.getByRole("button", { name: "Refund" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_refund_shot").query).toEqual({
        shot_id: "shot-1",
      }),
    );
    await waitFor(() =>
      expect(getAPICalls("admin_get_shots_info").length).toBeGreaterThan(
        before,
      ),
    );
  });

  test('"Re-run AI review" posts admin_review_shot for the shown shot', async () => {
    await renderQueue();

    userEvent.click(screen.getByRole("button", { name: "Re-run AI review" }));

    await waitFor(() =>
      expect(getLastAPICall("admin_review_shot").query).toEqual({
        shot_id: "shot-1",
      }),
    );
  });

  test("the show-adjudicated toggle asks the backend for checked shots too, defaulting to off", async () => {
    await renderQueue();

    expect(getLastAPICall("admin_get_shots_info").query.include_checked).toBe(
      "false",
    );

    userEvent.click(screen.getByLabelText(/Show adjudicated shots/));

    await waitFor(() =>
      expect(getLastAPICall("admin_get_shots_info").query.include_checked).toBe(
        "true",
      ),
    );
  });

  test("an adjudicated shot shows its verdict and no action buttons", async () => {
    shotsById["shot-1"] = makeShotDetail("shot-1", {
      checked: true,
      result: "miss",
    });
    await renderQueue();

    await screen.findByText("Adjudicated: Miss");
    expect(
      screen.queryByRole("button", { name: "Missed" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Bystander" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Refund" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Hit" }),
    ).not.toBeInTheDocument();
  });

  test("an adjudicated hit names the target in its verdict", async () => {
    shotsById["shot-1"] = makeShotDetail("shot-1", {
      checked: true,
      result: "hit",
      target_user_id: "shot-1-target-blue",
    });
    await renderQueue();

    await screen.findByText("Adjudicated: Hit on Target Blue");
  });

  test("notes load with the shot and save back to their endpoint", async () => {
    await renderQueue({
      admin_get_shot_notes: { notes: "crosshair is left of the head" },
      admin_set_shot_notes: {},
    });

    const box = await screen.findByLabelText("Admin notes");
    expect(box).toHaveValue("crosshair is left of the head");
    expect(screen.getByRole("button", { name: "Notes saved" })).toBeDisabled();

    await actAndFlush(() => userEvent.type(box, " - agreed"));
    await actAndFlush(() =>
      userEvent.click(screen.getByRole("button", { name: "Save notes" })),
    );

    expect(getLastAPICall("admin_set_shot_notes").query).toEqual({
      shot_id: "shot-1",
      notes: "crosshair is left of the head - agreed",
    });
    await screen.findByRole("button", { name: "Notes saved" });
  });
});

// ---------------------------------------------------------------------------
// ShotAiTags
// ---------------------------------------------------------------------------

describe("ShotAiTags", () => {
  let aiReviewResponse;

  beforeEach(() => {
    aiReviewResponse = NO_REVIEW_YET;
  });

  async function renderQueue() {
    installFetchMock({
      admin_is_authed: true,
      admin_get_shots_info: () => ["shot-1"],
      admin_get_shot: () => makeShotDetail("shot-1"),
      admin_get_shot_ai_review: () => aiReviewResponse,
      admin_shot_hit_user: {},
      admin_mark_shot_missed: {},
      admin_mark_shot_bystander: {},
      admin_refund_shot: {},
      admin_review_shot: {},
    });
    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <ShotQueue />
        </MemoryRouter>,
      ),
    );
    await screen.findByText("By Shooter of shot-1");
    await flushEffects();
  }

  test("renders nothing before a state arrives", async () => {
    await renderQueue();

    expect(screen.queryByText(/Reviewing/)).not.toBeInTheDocument();
    expect(screen.queryByText(/AI review failed/)).not.toBeInTheDocument();
    expect(screen.queryByText("HIT")).not.toBeInTheDocument();
  });

  test('shows "Reviewing..." while pending', async () => {
    aiReviewResponse = {
      status: 200,
      body: { state: "pending", review: null },
    };
    await renderQueue();

    await screen.findByText("Reviewing...");
  });

  test("shows the failure reason for an errored review", async () => {
    aiReviewResponse = {
      status: 200,
      body: { state: "error", review: { error: "vision model timed out" } },
    };
    await renderQueue();

    await screen.findByText("AI review failed: vision model timed out");
  });

  test("falls back to a generic message when the error carries no reason", async () => {
    aiReviewResponse = { status: 200, body: { state: "error", review: null } };
    await renderQueue();

    await screen.findByText("AI review failed: unknown error");
  });

  test.each([
    ["hit_player", "HIT"],
    ["hit_bystander", "Bystander - not a hit"],
    ["miss", "Miss"],
  ])("shows the %s outcome as %s", async (outcome, label) => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome,
          outcome_reason: "some reason",
          reasoning: "some reasoning",
          channels: {},
        },
      },
    };
    await renderQueue();

    await screen.findByText(label);
  });

  test("falls back to the raw outcome string for an unrecognised outcome", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "some_new_outcome_type",
          outcome_reason: "reason",
          reasoning: "",
          channels: {},
        },
      },
    };
    await renderQueue();

    await screen.findByText("some_new_outcome_type");
  });

  test("shows a tag per identity channel (colour, or unknown when unreadable), plus the reason and reasoning", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "hit_player",
          outcome_reason: "armbands visible",
          reasoning: "clear daylight photo",
          channels: {
            armbands: { colour: "red", hex: "#ff0000" },
            torso: { colour: null, hex: null },
          },
        },
      },
    };
    await renderQueue();

    await screen.findByText("HIT");
    expect(screen.getByText("armbands: red")).toBeInTheDocument();
    expect(screen.getByText("torso: unknown")).toBeInTheDocument();
    expect(
      screen.getByText("armbands visible - clear daylight photo"),
    ).toBeInTheDocument();
  });

  test("shows a zoom tag with no count for a legacy review (zoom_used only)", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "hit_player",
          outcome_reason: "armbands visible",
          reasoning: "",
          zoom_used: true,
          channels: {},
        },
      },
    };
    await renderQueue();

    await screen.findByText("HIT");
    expect(screen.getByText("Zoomed in")).toBeInTheDocument();
  });

  test("shows how many times the zoom was spent", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "hit_player",
          outcome_reason: "armbands visible",
          reasoning: "",
          zoom_used: true,
          zoom_count: 2,
          channels: {},
        },
      },
    };
    await renderQueue();

    await screen.findByText("HIT");
    expect(screen.getByText("Zoomed in ×2")).toBeInTheDocument();
    expect(screen.queryByText("Zoomed in")).not.toBeInTheDocument();
  });

  test("shows no zoom tag when the AI model did not use the zoom tool", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "miss",
          outcome_reason: "the shot did not land on anybody",
          reasoning: "",
          zoom_used: false,
          channels: {},
        },
      },
    };
    await renderQueue();

    await screen.findByText("Miss");
    expect(screen.queryByText("Zoomed in")).not.toBeInTheDocument();
  });

  test("shows the escalated-review message while the escalation is pending", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "hit_player",
          outcome_reason: "too few readable channels",
          reasoning: "",
          channels: {},
        },
        escalation_state: "pending",
        escalation: null,
      },
    };
    await renderQueue();

    await screen.findByText("Escalated to the stronger model - reviewing...");
  });

  test("shows the escalation failure reason", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "hit_player",
          outcome_reason: "too few readable channels",
          reasoning: "",
          channels: {},
        },
        escalation_state: "error",
        escalation: { error: "strong model timed out" },
      },
    };
    await renderQueue();

    await screen.findByText("Escalation failed: strong model timed out");
  });

  test("an unsure escalation shows the punt, the reasoning, and the ranked candidates", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "hit_player",
          outcome_reason: "too few readable channels",
          reasoning: "",
          channels: {},
        },
        escalation_state: "done",
        escalation: {
          verdict: "unsure",
          candidate: null,
          target_user_id: null,
          target_name: null,
          confidence: 0.4,
          reasoning: "Two plausible players in near-identical outfits.",
          candidates: [
            {
              number: 1,
              user_id: "u-alice",
              name: "Alice",
              probability: 0.61,
              reference_photo_shown: true,
            },
            {
              number: 2,
              user_id: "u-bob",
              name: "Bob",
              probability: 0.35,
              reference_photo_shown: false,
            },
          ],
        },
      },
    };
    await renderQueue();

    await screen.findByText("Needs your call");
    expect(
      screen.getByText("Two plausible players in near-identical outfits."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Alice - 61% (reference photo shown)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Bob - 35%")).toBeInTheDocument();
  });

  test("a player-verdict escalation shows the hit and who it names", async () => {
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "hit_player",
          outcome_reason: "too few readable channels",
          reasoning: "",
          channels: {},
        },
        escalation_state: "done",
        escalation: {
          verdict: "player",
          candidate: 1,
          target_user_id: "u-alice",
          target_name: "Alice",
          confidence: 0.82,
          reasoning: "Reference photo confirms the hat and trousers.",
          candidates: [],
        },
      },
    };
    await renderQueue();

    await screen.findByText("HIT on Alice (82%)");
  });

  test('refetches when a "shots" SSE update arrives, even though the shot id has not changed', async () => {
    aiReviewResponse = {
      status: 200,
      body: { state: "pending", review: null },
    };
    await renderQueue();
    await screen.findByText("Reviewing...");

    // The review for the same shot lands seconds later.
    aiReviewResponse = {
      status: 200,
      body: {
        state: "done",
        review: {
          outcome: "miss",
          outcome_reason: "no one there",
          reasoning: "",
          channels: {},
        },
      },
    };
    await actAndFlush(() => emitUpdate("shots"));

    await screen.findByText("Miss");
  });
});
