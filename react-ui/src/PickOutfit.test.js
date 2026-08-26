import React from "react";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";

import PickOutfit from "./PickOutfit";
import {
  installFetchMock,
  getAPICalls,
  getLastAPICall,
  actAndFlush,
} from "./testUtils";

function makeJoinData(overrides = {}) {
  return {
    team_id: "team-1",
    team_name: "Reds",
    team_colour: "red",
    team_channel: "hat",
    provided_channel: "armbands",
    wardrobe_channels: ["tshirt", "trousers"],
    channels: [
      {
        name: "tshirt",
        labels: ["black", "red"],
        hex: { black: "#222222", red: "#B00020" },
      },
      {
        name: "trousers",
        labels: ["black", "blue"],
        hex: { black: "#222222", blue: "#0072CE" },
      },
      { name: "hat", labels: ["red"], hex: { red: "#B00020" } },
      {
        name: "armbands",
        labels: ["red", "green"],
        hex: { red: "#B00020", green: "#00A651" },
      },
    ],
    colour_notes: { green: "includes olive and khaki" },
    you: null,
    ...overrides,
  };
}

function makeOption(overrides = {}) {
  return {
    appearance: {
      tshirt: "black",
      trousers: "black",
      hat: "red",
      armbands: "red",
    },
    slot: 1,
    overrides: {},
    overrides_needed: 0,
    rarity: 0.5,
    min_distance: 3,
    is_canonical: true,
    ...overrides,
  };
}

function makeOptionsResult(overrides = {}) {
  return {
    options: [makeOption()],
    page: 0,
    page_size: 12,
    total: 1,
    threshold: 3,
    relaxed: false,
    exhausted: false,
    ...overrides,
  };
}

function renderPickOutfit(initialEntry = "/pick?j=CODE1") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <PickOutfit />
    </MemoryRouter>,
  );
}

async function goPastHeader() {
  return screen.findByRole("heading", { name: "Team Reds" });
}

test("ticking colours and submitting posts the wardrobe and renders ranked options with a recommended badge on the canonical one", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: {
      options: [
        makeOption({
          appearance: {
            tshirt: "black",
            trousers: "black",
            hat: "red",
            armbands: "red",
          },
          overrides_needed: 0,
          is_canonical: true,
        }),
        makeOption({
          appearance: {
            tshirt: "red",
            trousers: "black",
            hat: "red",
            armbands: "green",
          },
          overrides_needed: 1,
          is_canonical: false,
        }),
      ],
      page: 0,
      page_size: 12,
      total: 2,
      threshold: 3,
      relaxed: false,
      exhausted: false,
    },
  });

  renderPickOutfit();
  await goPastHeader();

  const tshirtGroup = screen.getByRole("group", { name: "tshirt" });
  userEvent.click(within(tshirtGroup).getByRole("button", { name: "black" }));
  const trousersGroup = screen.getByRole("group", { name: "trousers" });
  userEvent.click(within(trousersGroup).getByRole("button", { name: "black" }));

  userEvent.click(screen.getByRole("checkbox"));

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Show me outfits" })),
  );

  expect(getLastAPICall("outfit_options").body).toEqual({
    data: "CODE1",
    wardrobe: { tshirt: ["black"], trousers: ["black"] },
    relaxed: false,
    page: 0,
  });

  expect(screen.getByText("recommended")).toBeInTheDocument();
  expect(screen.getByText("Exact match")).toBeInTheDocument();
  expect(screen.getByText("1 colour different")).toBeInTheDocument();
});

test("paging fetches the next page", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: ({ body }) =>
      makeOptionsResult({
        page: body.page,
        page_size: 1,
        total: 2,
        options: [
          makeOption({
            appearance: {
              tshirt: "black",
              trousers: "black",
              hat: "red",
              armbands: body.page === 0 ? "red" : "green",
            },
          }),
        ],
      }),
  });

  renderPickOutfit();
  await goPastHeader();
  userEvent.click(screen.getByRole("checkbox"));
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Show me outfits" })),
  );

  expect(screen.getByText("armbands: red")).toBeInTheDocument();

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Next" })),
  );

  expect(getLastAPICall("outfit_options").body.page).toBe(1);
  expect(screen.getByText("armbands: green")).toBeInTheDocument();
  expect(screen.queryByText("armbands: red")).not.toBeInTheDocument();
});

test("the empty state shows the are-you-sure prompt, and Yes I'm sure refetches at relaxed distance", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: ({ body }) =>
      body.relaxed
        ? makeOptionsResult({ relaxed: true })
        : makeOptionsResult({ options: [], total: 0 }),
  });

  renderPickOutfit();
  await goPastHeader();
  userEvent.click(screen.getByRole("checkbox"));
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Show me outfits" })),
  );

  expect(
    screen.getByText(
      "No outfits found. Are you sure you don't have any more clothes?",
    ),
  ).toBeInTheDocument();

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Yes, I'm sure" })),
  );

  expect(getLastAPICall("outfit_options").body.relaxed).toBe(true);
  expect(screen.getByText("recommended")).toBeInTheDocument();
});

test("choosing an option claims it and renders the result screen", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult(),
    pick_outfit: {
      user_id: "u1",
      name: "Alice",
      team_name: "Reds",
      slot: 1,
      overrides: null,
      wardrobe: {},
      canonical_appearance: makeOption().appearance,
      effective_appearance: makeOption().appearance,
      overridden: false,
    },
  });

  renderPickOutfit();
  await goPastHeader();
  userEvent.click(screen.getByRole("checkbox"));
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Show me outfits" })),
  );

  const row = screen.getByRole("button", { name: /Choose:/ });
  await actAndFlush(() => userEvent.click(row));

  expect(screen.getByText("This is final. Screenshot it.")).toBeInTheDocument();
  expect(getLastAPICall("pick_outfit").body).toEqual({
    data: "CODE1",
    wardrobe: {},
    appearance: makeOption().appearance,
    confirmed: true,
  });
});

test("a returning visitor whose slot is already set sees the result, not the form", async () => {
  installFetchMock({
    join_options: makeJoinData({
      you: {
        user_id: "u1",
        name: "Alice",
        team_name: "Reds",
        slot: 3,
        overrides: null,
        wardrobe: { tshirt: ["black"] },
        canonical_appearance: makeOption().appearance,
        effective_appearance: makeOption().appearance,
        overridden: false,
      },
    }),
  });

  renderPickOutfit();

  expect(
    await screen.findByText("This is final. Screenshot it."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});

test("a 409 from pick_outfit shows the choose-again message and refetches options", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult(),
    pick_outfit: {
      status: 409,
      body: { detail: "Someone just took that outfit - please choose again." },
    },
  });

  renderPickOutfit();
  await goPastHeader();
  userEvent.click(screen.getByRole("checkbox"));
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Show me outfits" })),
  );

  const row = screen.getByRole("button", { name: /Choose:/ });
  await actAndFlush(() => userEvent.click(row));

  expect(
    await screen.findByText(
      "Someone just took that outfit - please choose again.",
    ),
  ).toBeInTheDocument();
  expect(getAPICalls("outfit_options")).toHaveLength(2);
});
