// Smoke test over the route table in src/index.js: every route component
// mounts, inside a router, without throwing, and reaches its expected first
// paint. Deliberately shallow - this exists to catch a route that's dead
// (import error, crash on mount), not to exercise each page's full behaviour.
//
// index.js itself is not imported, since it calls ReactDOM.createRoot on a
// real DOM node at import time. Instead each route's element is built the
// same way index.js builds it and rendered directly inside a MemoryRouter.

import { render, screen, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { installFetchMock } from "./testUtils";

import UserMode from "./UserMode";
import PickOutfit from "./PickOutfit";
import AdminMode from "./AdminMode";
import ShotQueue from "./ShotQueue";
import ShotReplay from "./ShotReplay";
import TestPage from "./TestPage";
import IdentityDemo from "./IdentityDemo";
import AdminIdentity from "./AdminIdentity";
import AdminLogin from "./AdminLogin";
import { AdminPage } from "./AdminCommon";

// The map and webcam are heavy (geolocation watches, canvas, camera streams)
// and not what this smoke test is checking - every route that uses them is
// exercised well past "does the map mount" territory. Stand in for both.
jest.mock("./MapView", () => ({
  MapViewSelf: () => <div>Mock MapViewSelf</div>,
  MapViewAdmin: () => <div>Mock MapViewAdmin</div>,
}));
jest.mock("./WebcamView", () => () => <div>Mock WebcamView</div>);

// jsdom doesn't implement matchMedia. FullscreenButton (mounted by UserMode)
// uses it via the add-to-homescreen library's install-prompt detection - not
// stubbed globally in setupTests.js, so provide a minimal one here.
beforeEach(() => {
  window.matchMedia =
    window.matchMedia ||
    (() => ({
      matches: false,
      addListener: () => {},
      removeListener: () => {},
    }));
});

// AdminPage's authenticated views mount ShotQueueLink (and ShotQueue mounts
// its own queue-fetching effect), each firing its own fire-and-forget
// sendAPIRequest on mount. A plain `render()` + `findByText()` only mostly
// catches its eventual state update inside act() - draining a few ticks
// inside one continuous act(async) call is what reliably does.
async function renderAndFlush(ui, ticks = 6) {
  let result;
  await act(async () => {
    result = render(ui);
    for (let i = 0; i < ticks; i++) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
  return result;
}

const identityDefaults = {
  palette: ["red", "blue", "green"],
  channels: [{ name: "hat", labels: null }],
  thresholds: {
    confident_threshold: 0.6,
    ambiguous_margin: 0.15,
    epsilon: 0.000001,
  },
  target_distance: 3,
};

describe("/ (UserMode)", () => {
  test("mounts and shows the loading state before user_info resolves", () => {
    installFetchMock({ user_info: null });

    render(
      <MemoryRouter>
        <UserMode />
      </MemoryRouter>,
    );

    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });
});

describe("/pick (PickOutfit)", () => {
  test("mounts and shows the team header once join_options resolves", async () => {
    installFetchMock({
      join_options: {
        team_id: "team-1",
        team_name: "Reds",
        team_colour: "red",
        team_channel: "hat",
        provided_channel: "armbands",
        wardrobe_channels: ["tshirt", "trousers"],
        channels: [
          { name: "tshirt", labels: ["black"], hex: { black: "#222222" } },
          { name: "trousers", labels: ["black"], hex: { black: "#222222" } },
          { name: "hat", labels: ["red"], hex: { red: "#B00020" } },
          { name: "armbands", labels: ["red"], hex: { red: "#B00020" } },
        ],
        colour_notes: {},
        you: null,
      },
    });

    await renderAndFlush(
      <MemoryRouter initialEntries={["/pick?j=ABC123"]}>
        <PickOutfit />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Team Reds" }),
    ).toBeInTheDocument();
  });
});

describe("/admin (AdminMode)", () => {
  test("mounts and reaches the admin panel once authenticated", async () => {
    installFetchMock({
      admin_is_authed: true,
      admin_get_shots_info: [],
      admin_list_games: [],
      get_users: [],
    });

    render(
      <MemoryRouter>
        <AdminMode />
      </MemoryRouter>,
    );
    expect(screen.getByText("Checking admin login...")).toBeInTheDocument();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(
      screen.getByRole("heading", { name: "Admin", level: 1 }),
    ).toBeInTheDocument();
  });
});

describe("/admin/login (AdminLogin)", () => {
  test("mounts and shows the logged-in message once authenticated", async () => {
    installFetchMock({ admin_is_authed: true, admin_get_shots_info: [] });

    await renderAndFlush(
      <MemoryRouter>
        <AdminLogin />
      </MemoryRouter>,
    );

    expect(screen.getByText(/You are logged in as admin/)).toBeInTheDocument();
  });
});

describe("/admin/shots (ShotQueue)", () => {
  test("mounts and shows an empty queue once authenticated", async () => {
    installFetchMock({ admin_is_authed: true, admin_get_shots_info: [] });

    await renderAndFlush(
      <MemoryRouter>
        <ShotQueue />
      </MemoryRouter>,
    );

    // Surprising: with an empty queue, ShotQueuePanel clamps currentShotIdx
    // to shot_ids.length - 1 = -1, so the heading reads "Shot 0 of 0:"
    // rather than "Shot 1 of 0:".
    expect(screen.getByText("Shot 0 of 0:")).toBeInTheDocument();
  });
});

describe("/admin/replay (ShotReplay)", () => {
  test("mounts and shows the workbench once authenticated", async () => {
    installFetchMock({
      admin_is_authed: true,
      admin_get_shots_info: [],
      admin_get_default_vision_prompt: { prompt: "The live prompt" },
    });

    await renderAndFlush(
      <MemoryRouter>
        <ShotReplay />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Shot replay workbench" }),
    ).toBeInTheDocument();
  });
});

describe("/admin/identity (AdminPage wrapping IdentityDemo)", () => {
  test("mounts and shows the workbench once authenticated", async () => {
    installFetchMock({
      admin_is_authed: true,
      admin_get_shots_info: [],
      admin_identity_defaults: identityDefaults,
    });

    await renderAndFlush(
      <MemoryRouter>
        <AdminPage>
          <IdentityDemo />
        </AdminPage>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Identity code workbench" }),
    ).toBeInTheDocument();
  });
});

describe("/admin/identity-overrides (AdminPage wrapping AdminIdentity)", () => {
  test("mounts and shows the player table once authenticated", async () => {
    installFetchMock({
      admin_is_authed: true,
      admin_get_shots_info: [],
      admin_list_games: [{ id: "game-1", teams: [{ name: "Red" }] }],
      admin_identity_report: {
        nominal_min_distance: 3,
        effective_min_distance: null,
        pairs: [],
        free_slots: [2],
        channels: [
          {
            name: "hat",
            labels: ["red", "blue"],
            hex: { red: "#ff0000", blue: "#0000ff" },
          },
        ],
        players: [
          {
            user_id: "u1",
            name: "Alice",
            team_name: "Red",
            slot: 1,
            overridden: false,
            overrides: {},
            canonical_appearance: { hat: "red" },
            effective_appearance: { hat: "red" },
          },
        ],
      },
    });

    await renderAndFlush(
      <MemoryRouter>
        <AdminPage>
          <AdminIdentity />
        </AdminPage>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Identity overrides" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });
});

describe("/test (TestPage)", () => {
  test("mounts and shows its heading", () => {
    render(
      <MemoryRouter>
        <TestPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "This is a test" }),
    ).toBeInTheDocument();
  });
});
