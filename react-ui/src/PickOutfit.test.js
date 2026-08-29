import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
    provided_channel: "wristbands",
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
        notes: { black: "black or charcoal" },
      },
      { name: "hat", labels: ["red"], hex: { red: "#B00020" } },
      {
        name: "wristbands",
        labels: ["red", "green"],
        hex: { red: "#B00020", green: "#00A651" },
      },
    ],
    you: makeYou(),
    ...overrides,
  };
}

// The caller's own row as join_options returns it (backend/identity_admin.py's
// _player_row). The default is somebody who has given their name but not yet
// claimed an outfit - the ordinary state for everything past the name gate;
// pass `you: null` to land on the page as a brand new scanner.
function makeYou(overrides = {}) {
  return {
    user_id: "u1",
    name: "Alice",
    team_name: "Reds",
    slot: null,
    overrides: null,
    wardrobe: {},
    canonical_appearance: null,
    effective_appearance: null,
    overridden: false,
    ...overrides,
  };
}

function makeOption(overrides = {}) {
  return {
    appearance: {
      tshirt: "black",
      trousers: "black",
      hat: "red",
      wristbands: "red",
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

async function showOutfits() {
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Show me outfits" })),
  );
}

// Only the canonical options are shown until this is pressed - see the
// nudge test below.
async function showOtherOutfits() {
  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", {
        name: "Show more outfits",
      }),
    ),
  );
}

test("ticking colours and submitting (with no confirm checkbox on this step) posts the wardrobe and renders ranked options, badged best-first", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: {
      options: [
        makeOption({
          appearance: {
            tshirt: "black",
            trousers: "black",
            hat: "red",
            wristbands: "red",
          },
          overrides_needed: 0,
          is_canonical: true,
        }),
        makeOption({
          appearance: {
            tshirt: "red",
            trousers: "black",
            hat: "red",
            wristbands: "green",
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

  // The confirm checkbox has moved off this step entirely.
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

  const tshirtGroup = screen.getByRole("group", { name: "T-shirt" });
  userEvent.click(within(tshirtGroup).getByRole("button", { name: "black" }));
  const trousersGroup = screen.getByRole("group", { name: "Trousers" });
  userEvent.click(within(trousersGroup).getByRole("button", { name: "black" }));

  await showOutfits();

  expect(getLastAPICall("outfit_options").body).toEqual({
    data: "CODE1",
    wardrobe: { tshirt: ["black"], trousers: ["black"] },
    relaxed: false,
    page: 0,
  });

  expect(screen.getByText("recommended")).toBeInTheDocument();
  expect(screen.getByText("Exact match")).toBeInTheDocument();
  expect(screen.queryByText("1 colour different")).not.toBeInTheDocument();

  await showOtherOutfits();
  expect(screen.getByText("1 colour different")).toBeInTheDocument();
  expect(screen.getByText("not ideal")).toBeInTheDocument();

  // Only the player-supplied garments show on an option row - no hat/wristband.
  expect(screen.getByText("T-shirt: black")).toBeInTheDocument();
  expect(screen.queryByText(/^Hat:/)).not.toBeInTheDocument();
  expect(screen.queryByText(/^Wristbands:/)).not.toBeInTheDocument();
});

test("the wardrobe form collapses to a summary once options are showing, and Change what I own reopens it", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult(),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  // The twelve colour swatch buttons are gone from view; a summary + link
  // affordance stands in for them.
  expect(
    screen.queryByRole("group", { name: "T-shirt" }),
  ).not.toBeInTheDocument();
  const reopen = screen.getByRole("button", { name: "Change what I own" });

  await actAndFlush(() => userEvent.click(reopen));

  expect(screen.getByRole("group", { name: "T-shirt" })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Change what I own" }),
  ).not.toBeInTheDocument();
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
              trousers: body.page === 0 ? "black" : "blue",
              hat: "red",
              wristbands: "red",
            },
          }),
        ],
      }),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  expect(screen.getByText("Trousers: black")).toBeInTheDocument();

  await showOtherOutfits();
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Next" })),
  );

  expect(getLastAPICall("outfit_options").body.page).toBe(1);
  expect(screen.getByText("Trousers: blue")).toBeInTheDocument();
  expect(screen.queryByText("Trousers: black")).not.toBeInTheDocument();
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
  await showOutfits();

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

test("tapping an option shows the confirmation screen without claiming it, and Lock in my choice is disabled until ticked", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult(),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  const row = screen.getByRole("button", { name: /Choose:/ });
  await actAndFlush(() => userEvent.click(row));

  expect(getAPICalls("pick_outfit")).toHaveLength(0);
  expect(screen.getByText("Wear this outfit?")).toBeInTheDocument();

  const lockIn = screen.getByRole("button", { name: /Lock in my choice/ });
  expect(lockIn).toBeDisabled();

  userEvent.click(
    screen.getByRole("checkbox", { name: /wear this on the night/ }),
  );
  expect(lockIn).not.toBeDisabled();
});

test("a player who has not given their name cannot lock in an outfit until they do", async () => {
  installFetchMock({
    join_options: makeJoinData({ you: null }),
    outfit_options: makeOptionsResult(),
    set_name: {},
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: /Choose:/ })),
  );
  userEvent.click(
    screen.getByRole("checkbox", { name: /wear this on the night/ }),
  );

  // Ticked, but still nameless - an outfit claimed anonymously is an outfit
  // nobody can be handed a card for.
  const lockIn = screen.getByRole("button", { name: /Lock in my choice/ });
  expect(lockIn).toBeDisabled();

  const nameBox = screen.getByPlaceholderText("Enter your name...");
  await actAndFlush(() => {
    fireEvent.change(nameBox, { target: { value: "Alice" } });
    fireEvent.keyDown(nameBox, { key: "Enter" });
  });

  expect(getLastAPICall("set_name").query).toEqual({ name: "Alice" });
  expect(
    screen.getByRole("button", { name: /Lock in my choice/ }),
  ).not.toBeDisabled();
});

test("whitespace is not a name - it neither posts set_name nor unlocks the claim", async () => {
  installFetchMock({
    join_options: makeJoinData({ you: null }),
    outfit_options: makeOptionsResult(),
    set_name: {},
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: /Choose:/ })),
  );
  userEvent.click(
    screen.getByRole("checkbox", { name: /wear this on the night/ }),
  );

  const nameBox = screen.getByPlaceholderText("Enter your name...");
  await actAndFlush(() => {
    fireEvent.change(nameBox, { target: { value: "   " } });
    fireEvent.keyDown(nameBox, { key: "Enter" });
  });

  expect(getAPICalls("set_name")).toHaveLength(0);
  expect(
    screen.getByRole("button", { name: /Lock in my choice/ }),
  ).toBeDisabled();
});

test("a name already set in a previous session shows pre-filled, not blank, and stays editable on every step", async () => {
  installFetchMock({
    join_options: makeJoinData({ you: makeYou({ name: "Bob" }) }),
    outfit_options: makeOptionsResult(),
  });

  renderPickOutfit();
  await goPastHeader();

  // join_options already reported a name - the box must show it, not
  // resurface blank and ask again.
  expect(screen.getByPlaceholderText("Enter your name...")).toHaveValue("Bob");

  await showOutfits();
  expect(screen.getByPlaceholderText("Enter your name...")).toHaveValue("Bob");

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: /Choose:/ })),
  );

  // Still pre-filled, and still editable, on the confirm screen.
  expect(screen.getByPlaceholderText("Enter your name...")).toHaveValue("Bob");

  userEvent.click(
    screen.getByRole("checkbox", { name: /wear this on the night/ }),
  );
  expect(
    screen.getByRole("button", { name: /Lock in my choice/ }),
  ).not.toBeDisabled();
  expect(getAPICalls("set_name")).toHaveLength(0);
});

test("ticking the confirm box and pressing Lock in my choice claims the outfit and renders the result screen", async () => {
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
  await showOutfits();

  const row = screen.getByRole("button", { name: /Choose:/ });
  await actAndFlush(() => userEvent.click(row));
  userEvent.click(
    screen.getByRole("checkbox", { name: /wear this on the night/ }),
  );

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: /Lock in my choice/ })),
  );

  expect(screen.getByText("This is final. Screenshot it.")).toBeInTheDocument();
  expect(getLastAPICall("pick_outfit").body).toEqual({
    data: "CODE1",
    wardrobe: {},
    appearance: makeOption().appearance,
    confirmed: true,
  });

  // The result screen shows only the player-supplied garments too.
  expect(screen.queryByText("Hat")).not.toBeInTheDocument();
  expect(screen.queryByText("Wristbands")).not.toBeInTheDocument();
});

test("Choose a different outfit returns to the options list without claiming anything", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult(),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  const row = screen.getByRole("button", { name: /Choose:/ });
  await actAndFlush(() => userEvent.click(row));
  expect(screen.getByText("Wear this outfit?")).toBeInTheDocument();

  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", { name: "Choose a different outfit" }),
    ),
  );

  expect(screen.queryByText("Wear this outfit?")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Choose:/ })).toBeInTheDocument();
  expect(getAPICalls("pick_outfit")).toHaveLength(0);
});

test("a returning visitor whose slot is already set sees the result, not the form", async () => {
  installFetchMock({
    join_options: makeJoinData({
      you: makeYou({
        slot: 3,
        wardrobe: { tshirt: ["black"] },
        canonical_appearance: makeOption().appearance,
        effective_appearance: makeOption().appearance,
      }),
    }),
  });

  renderPickOutfit();

  expect(
    await screen.findByText("This is final. Screenshot it."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});

test("a 409 from pick_outfit shows the choose-again message, returns to the options and refetches them", async () => {
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
  await showOutfits();

  const row = screen.getByRole("button", { name: /Choose:/ });
  await actAndFlush(() => userEvent.click(row));
  userEvent.click(
    screen.getByRole("checkbox", { name: /wear this on the night/ }),
  );

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: /Lock in my choice/ })),
  );

  expect(
    await screen.findByText(
      "Someone just took that outfit - please choose again.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText("Wear this outfit?")).not.toBeInTheDocument();
  expect(getAPICalls("outfit_options")).toHaveLength(2);
});

test("only the canonical outfits show until the player asks for the rest, which also unhides the pagination", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult({
      options: [
        makeOption({
          appearance: {
            tshirt: "black",
            trousers: "black",
            hat: "red",
            wristbands: "red",
          },
        }),
        makeOption({
          appearance: {
            tshirt: "red",
            trousers: "blue",
            hat: "red",
            wristbands: "green",
          },
          overrides_needed: 1,
          is_canonical: false,
        }),
      ],
      page_size: 2,
      total: 4,
    }),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  expect(screen.getByText("Trousers: black")).toBeInTheDocument();
  expect(screen.queryByText("Trousers: blue")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Next" }),
  ).not.toBeInTheDocument();

  await showOtherOutfits();

  expect(screen.getByText("Trousers: blue")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Show more outfits" }),
  ).not.toBeInTheDocument();
});

test("the recommended badge marks only the top of the list, ties included", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult({
      options: [
        makeOption({
          appearance: {
            tshirt: "black",
            trousers: "black",
            hat: "red",
            wristbands: "red",
          },
          rarity: 0.9,
        }),
        makeOption({
          appearance: {
            tshirt: "black",
            trousers: "blue",
            hat: "red",
            wristbands: "red",
          },
          rarity: 0.9,
        }),
        makeOption({
          appearance: {
            tshirt: "red",
            trousers: "black",
            hat: "red",
            wristbands: "red",
          },
          rarity: 0.4,
        }),
      ],
      total: 3,
    }),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  // The two rarest canonical outfits tie at the top, so both are badged;
  // the third is canonical but simply goes unbadged.
  expect(screen.getAllByText("recommended")).toHaveLength(2);
  expect(screen.queryByText("not ideal")).not.toBeInTheDocument();

  const rows = screen.getAllByRole("button", { name: /Choose:/ });
  expect(within(rows[2]).queryByText("recommended")).not.toBeInTheDocument();
});

test("a later page badges nothing as recommended - only the first page holds the best", async () => {
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
              trousers: body.page === 0 ? "black" : "blue",
              hat: "red",
              wristbands: "red",
            },
          }),
        ],
      }),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();
  expect(screen.getByText("recommended")).toBeInTheDocument();

  await showOtherOutfits();
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Next" })),
  );

  expect(screen.getByText("Trousers: blue")).toBeInTheDocument();
  expect(screen.queryByText("recommended")).not.toBeInTheDocument();
});

test("a wardrobe with no canonical outfit at all shows the whole list rather than an empty one", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult({
      options: [
        makeOption({
          appearance: {
            tshirt: "red",
            trousers: "blue",
            hat: "red",
            wristbands: "green",
          },
          overrides_needed: 1,
          is_canonical: false,
        }),
      ],
    }),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();

  expect(screen.getByText("Trousers: blue")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Show more outfits" }),
  ).not.toBeInTheDocument();
});

test("reopening the wardrobe collapses the list back to the canonical outfits", async () => {
  installFetchMock({
    join_options: makeJoinData(),
    outfit_options: makeOptionsResult({
      options: [
        makeOption(),
        makeOption({
          appearance: {
            tshirt: "red",
            trousers: "blue",
            hat: "red",
            wristbands: "green",
          },
          overrides_needed: 1,
          is_canonical: false,
        }),
      ],
      total: 2,
    }),
  });

  renderPickOutfit();
  await goPastHeader();
  await showOutfits();
  await showOtherOutfits();
  expect(screen.getByText("Trousers: blue")).toBeInTheDocument();

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Change what I own" })),
  );
  await showOutfits();

  expect(screen.queryByText("Trousers: blue")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Show more outfits" }),
  ).toBeInTheDocument();
});
