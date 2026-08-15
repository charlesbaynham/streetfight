// Tests for the admin identity workbench.
//
// The one thing worth pinning down here is the null appearance: the backend
// deliberately sends `appearance: null` for a codeword a restricted channel
// (trousers) has no colour for, and the real default scheme produces several
// of those, so any table that reads through it crashes the whole page on
// mount. routes.test.js only smoke-tests the mount, and never mocks
// admin_identity_scheme, so it never renders a codebook row.

import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import IdentityDemo from "./IdentityDemo";
import { installFetchMock } from "./testUtils";

const defaults = {
  palette: ["black", "purple", "red", "blue", "green", "orange", "yellow"],
  channels: [
    { name: "tshirt", labels: null },
    { name: "trousers", labels: ["black", "blue", "green", "red", "white"] },
  ],
  thresholds: {
    confident_threshold: 0.6,
    ambiguous_margin: 0.15,
    epsilon: 0.000001,
  },
  target_distance: 3,
};

const channels = [
  { name: "tshirt", labels: defaults.palette },
  { name: "trousers", labels: defaults.channels[1].labels },
];

// Two codebook rows, one of each kind - slot 1 asks trousers for symbol 5,
// which that restricted palette has no colour for.
const scheme = {
  n: 2,
  k: 1,
  q: 7,
  capacity: 7,
  usable_capacity: 4,
  min_distance: 2,
  min_distance_source: "computed",
  code_type: "parity",
  channels,
  guarantees: { summary: "d=2: corrects 0 misread(s)." },
  codebook: [
    {
      slot: 0,
      codeword: [0, 0],
      wearable: true,
      appearance: { tshirt: "black", trousers: "black" },
    },
    { slot: 1, codeword: [1, 5], wearable: false, appearance: null },
  ],
  codebook_truncated: false,
};

// The scheme rebuild is debounced by 300ms; drain that plus the promise
// chain behind it.
async function renderWorkbench(routes = {}) {
  jest.useFakeTimers();
  render(
    <MemoryRouter>
      <IdentityDemo />
    </MemoryRouter>,
  );
  await act(async () => {
    jest.advanceTimersByTime(500);
  });
  await act(async () => {
    jest.advanceTimersByTime(500);
  });
  jest.useRealTimers();
  return routes;
}

beforeEach(() => {
  installFetchMock({
    admin_identity_defaults: defaults,
    admin_identity_scheme: scheme,
  });
});

afterEach(() => {
  jest.useRealTimers();
});

describe("codebook", () => {
  test("renders unwearable codewords instead of crashing on a null appearance", async () => {
    await renderWorkbench();

    expect(
      screen.getByRole("heading", { name: "Scheme built" }),
    ).toBeInTheDocument();

    // The wearable row shows its colours...
    expect(screen.getAllByText("black").length).toBeGreaterThan(0);
    // ...and the unwearable one is dashed out, one cell per channel.
    expect(screen.getAllByText("—")).toHaveLength(channels.length);
    expect(screen.getByText("no")).toBeInTheDocument();
  });

  test("reports how many slots are actually assignable", async () => {
    await renderWorkbench();

    expect(screen.getByText("4")).toBeInTheDocument();
  });
});

describe("loading a slot into the reading", () => {
  test("refuses an unwearable slot with an explanation", async () => {
    await renderWorkbench();

    fireEvent.change(screen.getByRole("textbox", { name: /slot/i }), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "load" }));

    expect(screen.getByText(/slot 1 is not wearable/)).toBeInTheDocument();
  });

  test("loads a wearable slot's appearance", async () => {
    await renderWorkbench();

    fireEvent.change(screen.getByRole("textbox", { name: /slot/i }), {
      target: { value: "0" },
    });
    fireEvent.click(screen.getByRole("button", { name: "load" }));

    expect(screen.queryByText(/is not wearable/)).not.toBeInTheDocument();
    const selects = screen.getAllByRole("combobox");
    // Two "kind" selects plus the two symbol selects, which now hold slot 0.
    const symbols = selects.filter((s) => s.value === "black");
    expect(symbols).toHaveLength(channels.length);
  });
});
