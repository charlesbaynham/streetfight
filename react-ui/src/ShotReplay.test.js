// Tests for the shot replay workbench: the prompt round-trip, firing selected
// shots at the replay endpoint, and surfacing agreements/disagreements with
// the admin's verdicts.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import {
  actAndFlush,
  emitUpdate,
  getAPICalls,
  getLastAPICall,
  installFetchMock,
  makeGame,
  makeTeam,
  makeUser,
} from "./testUtils";

import ShotReplay from "./ShotReplay";

const user = makeUser({ name: "Shooter McGavin" });
const game = makeGame({ teams: [makeTeam({ users: [user] })] });

function makeShotDetail(overrides = {}) {
  return {
    id: "shot-1",
    time_created: "2026-08-24T12:00:00",
    game_id: game.id,
    checked: false,
    result: null,
    image_base64: "data:image/jpeg;base64,AAAA",
    user,
    game,
    user_id: user.id,
    target_user_id: null,
    shot_damage: 1,
    location_context: null,
    ai_review_state: null,
    ai_review: null,
    ...overrides,
  };
}

const hitReview = {
  shot_hit_a_person: true,
  confidence: 0.9,
  outcome: "hit_player",
  outcome_reason: "armbands visible",
  is_hit: true,
  slot: 7,
  reasoning: "clear view of the target",
  zoom_used: true,
  zoom_count: 1,
  transcript: [
    {
      turns: [
        { role: "user", text: "The screening question", has_image: true },
      ],
      reply: { person_fills_less_than_half: true },
    },
    {
      turns: [
        { role: "user", text: "The screening question", has_image: true },
        { role: "assistant", text: '{"person_fills_less_than_half": true}' },
        { role: "user", text: "Here is another image", has_image: true },
      ],
      reply: { shot_hit_a_person: true, confidence: 0.9 },
    },
  ],
  channels: {
    tshirt: { visible: true, colour: "black", confidence: 0.9, hex: "#1A1A1A" },
    trousers: {
      visible: true,
      colour: "blue",
      confidence: 0.9,
      hex: "#0072CE",
    },
    hat: { visible: true, colour: "red", confidence: 0.9, hex: "#C8102E" },
    armbands: {
      visible: true,
      colour: "green",
      confidence: 0.9,
      hex: "#00B140",
    },
  },
};

function visionImagesFor(shotId) {
  return {
    full: `data:image/jpeg;base64,vision-full-${shotId}`,
    zoomed: `data:image/jpeg;base64,vision-zoomed-${shotId}`,
  };
}

function installWorkshopMock(shotsById, extra = {}) {
  installFetchMock({
    admin_is_authed: true,
    admin_get_shots_info: Object.keys(shotsById),
    admin_get_shot: ({ query }) => shotsById[query.shot_id],
    admin_get_shot_vision_images: ({ query }) => visionImagesFor(query.shot_id),
    admin_get_default_vision_prompt: { prompt: "The live prompt" },
    admin_replay_shot_review: hitReview,
    ...extra,
  });
}

test("prefills the prompt with the live one and lists every shot", async () => {
  installWorkshopMock({ "shot-1": makeShotDetail() });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  expect(screen.getByLabelText("Vision prompt")).toHaveValue("The live prompt");
  expect(
    screen.getByText("Shooter McGavin", { exact: false }),
  ).toBeInTheDocument();
  // History view: the listing asked for adjudicated shots too
  expect(getLastAPICall("admin_get_shots_info").query).toEqual({
    include_checked: "true",
  });
});

test("replaying a selected shot posts the edited prompt and shows the reading", async () => {
  installWorkshopMock({ "shot-1": makeShotDetail() });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  fireEvent.change(screen.getByLabelText("Vision prompt"), {
    target: { value: "A customised prompt" },
  });
  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("checkbox", { name: "" })),
  );
  await actAndFlush(() =>
    fireEvent.click(
      screen.getByRole("button", { name: "Replay 1 selected shot" }),
    ),
  );

  const call = getLastAPICall("admin_replay_shot_review");
  expect(call.method).toBe("POST");
  expect(call.body).toEqual({
    shot_id: "shot-1",
    prompt: "A customised prompt",
    // The default matches the live pipeline: the zoom is screening-gated,
    // not sent up front.
    always_zoom: false,
  });

  expect(screen.getByText("HIT")).toBeInTheDocument();
  expect(screen.getByText(/clear view of the target/)).toBeInTheDocument();
});

test("shows how many times the zoom was spent, and the full model transcript", async () => {
  installWorkshopMock({ "shot-1": makeShotDetail() });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("checkbox", { name: "" })),
  );
  await actAndFlush(() =>
    fireEvent.click(
      screen.getByRole("button", { name: "Replay 1 selected shot" }),
    ),
  );

  expect(screen.getByText("Zoomed in ×1")).toBeInTheDocument();
  expect(
    screen.getByText("Full model transcript (2 exchanges)"),
  ).toBeInTheDocument();
  // The turn-by-turn view, collapsed by default: each turn's text and the
  // raw reply for that exchange
  expect(screen.getAllByText("The screening question").length).toBeGreaterThan(
    0,
  );
  expect(screen.getByText("Here is another image")).toBeInTheDocument();

  // The prettified-JSON toggle dumps the whole transcript instead
  fireEvent.click(screen.getByLabelText("Prettified JSON"));
  expect(
    screen.getByText(/"person_fills_less_than_half": true/),
  ).toBeInTheDocument();
});

test("a replay disagreeing with the admin's verdict says so", async () => {
  installWorkshopMock({
    "shot-1": makeShotDetail({ checked: true, result: "miss" }),
  });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("checkbox", { name: "" })),
  );
  await actAndFlush(() =>
    fireEvent.click(
      screen.getByRole("button", { name: "Replay 1 selected shot" }),
    ),
  );

  expect(screen.getByText("Adjudicated: Miss")).toBeInTheDocument();
  expect(
    screen.getByText("Disagrees with the admin's verdict"),
  ).toBeInTheDocument();
});

test("a failed replay is shown against the shot", async () => {
  installWorkshopMock(
    { "shot-1": makeShotDetail() },
    {
      admin_replay_shot_review: {
        status: 502,
        body: { detail: "Replay failed: the model fell over" },
      },
    },
  );

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("checkbox", { name: "" })),
  );
  await actAndFlush(() =>
    fireEvent.click(
      screen.getByRole("button", { name: "Replay 1 selected shot" }),
    ),
  );

  expect(screen.getByText(/Replay failed: 502/)).toBeInTheDocument();
});

describe("vision-formatted images", () => {
  test("each shot card shows the two vision images (full + zoomed) with correct src", async () => {
    installWorkshopMock({ "shot-1": makeShotDetail() });

    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <ShotReplay />
        </MemoryRouter>,
      ),
    );

    // Vision images are fetched per shot_id and rendered side-by-side
    expect(
      await screen.findByAltText("Full frame as vision sees it"),
    ).toHaveAttribute("src", "data:image/jpeg;base64,vision-full-shot-1");
    expect(
      screen.getByAltText("Zoomed centre as vision sees it"),
    ).toHaveAttribute("src", "data:image/jpeg;base64,vision-zoomed-shot-1");
    expect(
      screen.getByText("Full frame (as vision sees it)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Zoomed centre (as vision sees it)"),
    ).toBeInTheDocument();

    expect(getLastAPICall("admin_get_shot_vision_images").query).toEqual({
      shot_id: "shot-1",
    });
  });

  test("renders both vision images for every shot in the list", async () => {
    installWorkshopMock({
      "shot-1": makeShotDetail({ id: "shot-1" }),
      "shot-2": {
        ...makeShotDetail({ id: "shot-2" }),
        id: "shot-2",
        user: { ...user, name: "Second Shooter" },
      },
    });

    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <ShotReplay />
        </MemoryRouter>,
      ),
    );

    expect(
      await screen.findAllByAltText("Full frame as vision sees it"),
    ).toHaveLength(2);
    expect(
      screen.getAllByAltText("Zoomed centre as vision sees it"),
    ).toHaveLength(2);
    expect(getAPICalls("admin_get_shot_vision_images")).toHaveLength(2);
  });

  test("does not refetch vision images on a shots SSE update", async () => {
    installWorkshopMock({ "shot-1": makeShotDetail() });

    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <ShotReplay />
        </MemoryRouter>,
      ),
    );

    await screen.findByAltText("Full frame as vision sees it");
    const before = getAPICalls("admin_get_shot_vision_images").length;

    await actAndFlush(() => emitUpdate("shots"));

    // Vision images are deterministic from the stored shot, not from queue state
    expect(getAPICalls("admin_get_shot_vision_images")).toHaveLength(before);
  });

  test("stale vision images are cleared when the card switches to a different shot", async () => {
    // Test the isolated component directly: it must not show the previous
    // shot's images while the new fetch is in flight.
    const { ShotVisionImages } = await import("./ShotReplay");

    let resolveFirst;
    let resolveSecond;
    installFetchMock({
      admin_get_shot_vision_images: ({ query }) => {
        if (query.shot_id === "shot-1") {
          return new Promise((resolve) => {
            resolveFirst = () => resolve(visionImagesFor("shot-1"));
          });
        }
        if (query.shot_id === "shot-2") {
          return new Promise((resolve) => {
            resolveSecond = () => resolve(visionImagesFor("shot-2"));
          });
        }
        return visionImagesFor(query.shot_id);
      },
    });

    const { rerender } = await actAndFlush(() =>
      render(<ShotVisionImages shot_id="shot-1" />),
    );

    expect(screen.getByText("Loading vision images...")).toBeInTheDocument();

    // Switch to shot-2 before shot-1 resolves — must clear and not show stale
    await actAndFlush(() => rerender(<ShotVisionImages shot_id="shot-2" />));

    // Still loading for shot-2, not the old shot-1 image
    expect(screen.getByText("Loading vision images...")).toBeInTheDocument();

    // Resolve shot-2 first
    await actAndFlush(() => {
      resolveSecond();
      return new Promise((r) => setTimeout(r, 0));
    });

    expect(
      await screen.findByAltText("Full frame as vision sees it"),
    ).toHaveAttribute("src", "data:image/jpeg;base64,vision-full-shot-2");

    // Now resolve the stale first request — it must not overwrite shot-2
    await actAndFlush(() => {
      resolveFirst();
      return new Promise((r) => setTimeout(r, 0));
    });

    expect(screen.getByAltText("Full frame as vision sees it")).toHaveAttribute(
      "src",
      "data:image/jpeg;base64,vision-full-shot-2",
    );
  });
});
