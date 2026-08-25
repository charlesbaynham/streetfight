// Tests for the shot replay workbench: the prompt round-trip, firing selected
// shots at the replay endpoint, and surfacing agreements/disagreements with
// the admin's verdicts.

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import {
  actAndFlush,
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

function installWorkshopMock(shotsById, extra = {}) {
  installFetchMock({
    admin_is_authed: true,
    admin_get_shots_info: Object.keys(shotsById),
    admin_get_shot: ({ query }) => shotsById[query.shot_id],
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
    always_zoom: true,
  });

  expect(screen.getByText("HIT")).toBeInTheDocument();
  expect(screen.getByText(/clear view of the target/)).toBeInTheDocument();
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
