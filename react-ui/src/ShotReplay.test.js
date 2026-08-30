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
    { role: "user", text: "The screening question", has_image: true },
    { role: "assistant", reply: { person_fills_less_than_half: true } },
    { role: "user", text: "Here is another image", has_image: true },
    {
      role: "assistant",
      reply: { shot_hit_a_person: true, confidence: 0.9 },
      reasoning: "The armbands are clearly green in this crop.",
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

// The response contract the live pipeline asks for, seeded into the schema
// box alongside the prompt.
const liveSchema = {
  type: "object",
  properties: { shot_hit_a_person: { type: "boolean" } },
  required: ["shot_hit_a_person"],
};

function visionImagesFor(shotId) {
  return {
    full: `data:image/jpeg;base64,vision-full-${shotId}`,
    zoomed: `data:image/jpeg;base64,vision-zoomed-${shotId}`,
    zoomed2: `data:image/jpeg;base64,vision-zoomed2-${shotId}`,
  };
}

function installWorkshopMock(shotsById, extra = {}) {
  installFetchMock({
    admin_is_authed: true,
    admin_get_shots_info: Object.keys(shotsById),
    admin_get_shot: ({ query }) => shotsById[query.shot_id],
    admin_get_shot_vision_images: ({ query }) => visionImagesFor(query.shot_id),
    admin_get_default_vision_prompt: ({ query }) => ({
      prompt:
        query.zoom_mode === "single"
          ? "The single-turn prompt"
          : "The live prompt",
      schema: liveSchema,
    }),
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
    // the response contract is the live one, and no reasoning-effort
    // override is sent.
    zoom_mode: "screened",
    response_schema: liveSchema,
    reasoning_effort: null,
  });

  expect(screen.getByText("HIT")).toBeInTheDocument();
  expect(screen.getByText(/clear view of the target/)).toBeInTheDocument();
});

test("the edited response schema is posted alongside the prompt", async () => {
  // Editing the wording alone changes nothing if the model is still forced to
  // answer the pipeline's own schema -- the contract has to travel with it.
  installWorkshopMock({ "shot-1": makeShotDetail() });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  expect(screen.getByLabelText("Response schema")).toHaveValue(
    JSON.stringify(liveSchema, null, 2),
  );

  const customSchema = { type: "object", properties: { aim_point: {} } };
  fireEvent.change(screen.getByLabelText("Response schema"), {
    target: { value: JSON.stringify(customSchema) },
  });
  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("checkbox", { name: "" })),
  );
  await actAndFlush(() =>
    fireEvent.click(
      screen.getByRole("button", { name: "Replay 1 selected shot" }),
    ),
  );

  expect(
    getLastAPICall("admin_replay_shot_review").body.response_schema,
  ).toEqual(customSchema);
});

test("an unparseable response schema blocks the replay and says so", async () => {
  installWorkshopMock({ "shot-1": makeShotDetail() });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  fireEvent.change(screen.getByLabelText("Response schema"), {
    target: { value: "{not json" },
  });
  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("checkbox", { name: "" })),
  );
  await actAndFlush(() =>
    fireEvent.click(
      screen.getByRole("button", { name: "Replay 1 selected shot" }),
    ),
  );

  expect(screen.getByText(/not valid JSON/)).toBeInTheDocument();
  expect(getAPICalls("admin_replay_shot_review")).toHaveLength(0);
});

test("choosing a conversation shape reseeds the prompt that describes it", async () => {
  // The prompt explains the zoom it is about to be offered, so an untouched
  // prompt must follow the shape rather than describe a different exchange.
  installWorkshopMock({ "shot-1": makeShotDetail() });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  await actAndFlush(() =>
    fireEvent.change(screen.getByLabelText("Conversation shape"), {
      target: { value: "single" },
    }),
  );

  expect(screen.getByLabelText("Vision prompt")).toHaveValue(
    "The single-turn prompt",
  );

  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("checkbox", { name: "" })),
  );
  await actAndFlush(() =>
    fireEvent.click(
      screen.getByRole("button", { name: "Replay 1 selected shot" }),
    ),
  );

  expect(getLastAPICall("admin_replay_shot_review").body.zoom_mode).toBe(
    "single",
  );
});

test("an edited prompt survives a change of conversation shape", async () => {
  installWorkshopMock({ "shot-1": makeShotDetail() });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  fireEvent.change(screen.getByLabelText("Vision prompt"), {
    target: { value: "My own wording" },
  });
  await actAndFlush(() =>
    fireEvent.change(screen.getByLabelText("Conversation shape"), {
      target: { value: "single" },
    }),
  );

  expect(screen.getByLabelText("Vision prompt")).toHaveValue("My own wording");
});

test("a reply that did not match the contract is shown as it landed", async () => {
  // A custom contract has no outcome to render: showing the pipeline's
  // default "Miss" would be a verdict the model never gave.
  installWorkshopMock(
    { "shot-1": makeShotDetail() },
    {
      admin_replay_shot_review: {
        ...hitReview,
        outcome: "miss",
        is_hit: false,
        parse_error: "'shot_hit_a_person' must be true or false; got None",
        raw_reply: { aim_point: "512x384" },
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

  expect(
    screen.getByText(/did not match the standard reading/),
  ).toBeInTheDocument();
  expect(screen.getByText(/"aim_point": "512x384"/)).toBeInTheDocument();
  expect(screen.queryByText("Miss")).not.toBeInTheDocument();
});

test("a chosen reasoning effort is sent as the override", async () => {
  installWorkshopMock({ "shot-1": makeShotDetail() });

  await actAndFlush(() =>
    render(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    ),
  );

  fireEvent.change(screen.getByLabelText("Reasoning effort"), {
    target: { value: "high" },
  });
  await actAndFlush(() =>
    fireEvent.click(screen.getByRole("checkbox", { name: "" })),
  );
  await actAndFlush(() =>
    fireEvent.click(
      screen.getByRole("button", { name: "Replay 1 selected shot" }),
    ),
  );

  expect(getLastAPICall("admin_replay_shot_review").body.reasoning_effort).toBe(
    "high",
  );
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
    screen.getByText("Full model transcript (4 turns)"),
  ).toBeInTheDocument();
  // The flat, chronological view, collapsed by default: each turn's text or
  // reply, in the order they were actually exchanged -- nothing repeated
  expect(screen.getByText("The screening question")).toBeInTheDocument();
  expect(screen.getByText("Here is another image")).toBeInTheDocument();
  expect(
    screen.getByText(/"person_fills_less_than_half": true/),
  ).toBeInTheDocument();

  // The prettified-JSON toggle dumps the whole transcript instead
  fireEvent.click(screen.getByLabelText("Prettified JSON"));
  expect(screen.getByText(/"shot_hit_a_person": true/)).toBeInTheDocument();
});

test("shows a thinking model's reasoning trace alongside its reply", async () => {
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

  // Shown under its own "Model reasoning" disclosure, alongside the reply it
  // led to -- only the turn that actually carried one gets a disclosure.
  expect(screen.getAllByText("Model reasoning")).toHaveLength(1);
  expect(
    screen.getByText("The armbands are clearly green in this crop."),
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

describe("escalation replay", () => {
  const escalationPayload = {
    verdict: "player",
    candidate: 1,
    target_user_id: "user-9",
    target_name: "Bertha Bystander",
    confidence: 0.82,
    reasoning: "the burgundy hat matches candidate 1's reference photo",
    candidates: [
      {
        number: 1,
        user_id: "user-9",
        name: "Bertha Bystander",
        probability: 0.6,
        reference_photo_shown: true,
      },
      {
        number: 2,
        user_id: "user-8",
        name: "Colin Candidate",
        probability: 0.3,
        reference_photo_shown: false,
      },
    ],
    requested_reference_photos: [],
    transcript: [
      { role: "user", text: "The escalation prompt", has_image: true },
      { role: "user", text: "Here is the zoomed view", has_image: true },
      {
        role: "assistant",
        reply: { verdict: "player", candidate: 1 },
        reasoning: "Candidate 1's armband is the only lime one in frame.",
      },
    ],
  };

  test("escalating a shot shows the stronger model's verdict and transcript", async () => {
    installWorkshopMock(
      { "shot-1": makeShotDetail() },
      { admin_replay_shot_escalation: escalationPayload },
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
        screen.getByRole("button", { name: "Escalate 1 selected shot" }),
      ),
    );

    const call = getLastAPICall("admin_replay_shot_escalation");
    expect(call.method).toBe("POST");
    // None of the contract boxes reach this path: the escalation prompt is
    // assembled from the ranking, not typed.
    expect(call.body).toEqual({ shot_id: "shot-1", reasoning_effort: null });

    // Rendered by the queue's own ShotEscalation, so it reads identically
    expect(screen.getByText("Stronger model")).toBeInTheDocument();
    expect(
      screen.getByText("HIT on Bertha Bystander (82%)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/burgundy hat matches candidate 1/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Colin Candidate - 30%/)).toBeInTheDocument();

    // ...and the whole point of the item: the escalated exchange, turn by turn
    expect(
      screen.getByText("Full model transcript (3 turns)"),
    ).toBeInTheDocument();
    expect(screen.getByText("The escalation prompt")).toBeInTheDocument();
    expect(
      screen.getByText("Candidate 1's armband is the only lime one in frame."),
    ).toBeInTheDocument();
  });

  test("an escalation replay is shown beside the review replay, not instead of it", async () => {
    installWorkshopMock(
      { "shot-1": makeShotDetail() },
      { admin_replay_shot_escalation: escalationPayload },
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
    await actAndFlush(() =>
      fireEvent.click(
        screen.getByRole("button", { name: "Escalate 1 selected shot" }),
      ),
    );

    // Reading the second rung against the first is the reason both are kept
    expect(screen.getByText("HIT")).toBeInTheDocument();
    expect(
      screen.getByText("HIT on Bertha Bystander (82%)"),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Full model transcript/)).toHaveLength(2);
  });

  test("the chosen reasoning effort is sent with the escalation too", async () => {
    installWorkshopMock(
      { "shot-1": makeShotDetail() },
      { admin_replay_shot_escalation: escalationPayload },
    );

    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <ShotReplay />
        </MemoryRouter>,
      ),
    );

    fireEvent.change(screen.getByLabelText("Reasoning effort"), {
      target: { value: "max" },
    });
    await actAndFlush(() =>
      fireEvent.click(screen.getByRole("checkbox", { name: "" })),
    );
    await actAndFlush(() =>
      fireEvent.click(
        screen.getByRole("button", { name: "Escalate 1 selected shot" }),
      ),
    );

    expect(
      getLastAPICall("admin_replay_shot_escalation").body.reasoning_effort,
    ).toBe("max");
  });

  test("a shot with no stored review says why it cannot be escalated", async () => {
    installWorkshopMock(
      { "shot-1": makeShotDetail() },
      {
        admin_replay_shot_escalation: {
          status: 400,
          body: {
            detail:
              "This shot has no completed AI review to escalate from - run " +
              "the AI review first",
          },
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
        screen.getByRole("button", { name: "Escalate 1 selected shot" }),
      ),
    );

    expect(
      screen.getByText(/Escalation replay failed: 400/),
    ).toBeInTheDocument();
  });
});

describe("vision-formatted images", () => {
  test("shows only the full frame before any replay has run", async () => {
    installWorkshopMock({ "shot-1": makeShotDetail() });

    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <ShotReplay />
        </MemoryRouter>,
      ),
    );

    // Nothing is known yet about whether a zoom followed, so only the full
    // frame shows -- not the zoom images the endpoint also returns.
    expect(
      await screen.findByAltText("Full frame as vision sees it"),
    ).toHaveAttribute("src", "data:image/jpeg;base64,vision-full-shot-1");
    expect(
      screen.getByText("Full frame (as vision sees it)"),
    ).toBeInTheDocument();
    expect(
      screen.queryByAltText(/Zoom \d centre as vision sees it/),
    ).not.toBeInTheDocument();

    expect(getLastAPICall("admin_get_shot_vision_images").query).toEqual({
      shot_id: "shot-1",
    });
  });

  test("shows only as many zoom images as the replay actually spent", async () => {
    installWorkshopMock(
      { "shot-1": makeShotDetail() },
      { admin_replay_shot_review: { ...hitReview, zoom_count: 1 } },
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

    expect(
      screen.getByAltText("Zoom 1 centre as vision sees it"),
    ).toHaveAttribute("src", "data:image/jpeg;base64,vision-zoomed-shot-1");
    expect(
      screen.queryByAltText("Zoom 2 centre as vision sees it"),
    ).not.toBeInTheDocument();
  });

  test("shows both zoom images when the replay spent a second zoom", async () => {
    installWorkshopMock(
      { "shot-1": makeShotDetail() },
      { admin_replay_shot_review: { ...hitReview, zoom_count: 2 } },
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

    expect(
      screen.getByAltText("Zoom 1 centre as vision sees it"),
    ).toHaveAttribute("src", "data:image/jpeg;base64,vision-zoomed-shot-1");
    expect(
      screen.getByAltText("Zoom 2 centre as vision sees it"),
    ).toHaveAttribute("src", "data:image/jpeg;base64,vision-zoomed2-shot-1");
  });

  test("renders the full frame for every shot in the list", async () => {
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
