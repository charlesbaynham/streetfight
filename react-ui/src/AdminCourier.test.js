import React from "react";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CourierPanel } from "./AdminCourier";
import { installFetchMock, getAPICalls, getLastAPICall } from "./testUtils";

const GAME = { id: "game-1", teams: [{ name: "Red" }] };

const FIX = {
  coords: { latitude: 51.5, longitude: -0.13, accuracy: 8 },
};

// A server that actually keeps the crates, so the page's list is what came
// back rather than what it hoped for: placing adds a row, clearing removes it.
function routes(extra = {}) {
  let drops = [];
  let next = 0;

  return {
    admin_list_games: [GAME],
    admin_set_courier_location: {},
    admin_clear_courier: {},
    admin_list_drops: () => drops,
    admin_place_drop: ({ query }) => {
      const id = `drop-${(next += 1)}`;
      drops = [
        ...drops,
        {
          id,
          lat: Number(query.lat),
          long: Number(query.long),
          radius: Number(query.radius_km),
          time_created: 1758000000 + next,
        },
      ];
      return id;
    },
    admin_clear_drop: ({ query }) => {
      drops = drops.filter((drop) => drop.id !== query.drop_id);
      return {};
    },
    ...extra,
  };
}

async function clickAndFlush(element) {
  await act(async () => {
    await userEvent.click(element);
  });
}

// Hands the registered watchPosition callback a fix, as the browser would
async function emitFix(fix = FIX) {
  const onPosition = navigator.geolocation.watchPosition.mock.calls.at(-1)[0];
  await act(async () => {
    onPosition(fix);
  });
}

// Broadcast, take a fix, and put a crate down: the whole of a courier's trip
async function placeADrop() {
  await startBroadcasting();
  await emitFix();
  const place = screen.getByRole("button", { name: /place drop here/i });
  await clickAndFlush(place);
  await clickAndFlush(place);
}

async function startBroadcasting() {
  await clickAndFlush(
    await screen.findByRole("button", { name: /broadcast my location/i }),
  );
}

describe("AdminCourier", () => {
  test("broadcasting posts the fix and says so in words", async () => {
    installFetchMock(routes());
    render(<CourierPanel />);

    expect(await screen.findByText(/not broadcasting/i)).toBeInTheDocument();

    await startBroadcasting();
    await emitFix();

    const calls = getAPICalls("admin_set_courier_location");
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].query).toMatchObject({
      game_id: "game-1",
      lat: "51.5",
      long: "-0.13",
      accuracy: "8",
    });

    expect(screen.getByText(/broadcasting - last fix/i)).toHaveTextContent(
      "±8 m",
    );
  });

  test("stopping clears the courier server-side", async () => {
    installFetchMock(routes());
    render(<CourierPanel />);

    await startBroadcasting();
    await emitFix();
    await clickAndFlush(
      screen.getByRole("button", { name: /stop broadcasting/i }),
    );

    expect(getAPICalls("admin_clear_courier")).toHaveLength(1);
    expect(screen.getByText(/not broadcasting/i)).toBeInTheDocument();
  });

  test("placing the drop takes two taps, then stops broadcasting", async () => {
    installFetchMock(routes());
    render(<CourierPanel />);

    await startBroadcasting();
    await emitFix();

    const place = screen.getByRole("button", { name: /place drop here/i });
    await clickAndFlush(place);

    // Armed, nothing sent yet
    expect(getAPICalls("admin_place_drop")).toHaveLength(0);
    expect(place).toHaveTextContent(/tap again/i);

    await clickAndFlush(place);

    // Its own row (M4.3), not the game's one drop circle, so a second crate
    // leaves the first where it is
    const placed = getLastAPICall("admin_place_drop");
    expect(placed.method).toBe("POST");
    expect(placed.query).toMatchObject({
      game_id: "game-1",
      lat: "51.5",
      long: "-0.13",
    });

    // The crate is down, so the courier is no longer worth following
    expect(getAPICalls("admin_clear_courier")).toHaveLength(1);
    expect(screen.getByText(/not broadcasting/i)).toBeInTheDocument();
  });

  test("a placed crate joins the list, with the time it went down", async () => {
    installFetchMock(routes());
    render(<CourierPanel />);

    expect(await screen.findByText(/nothing is out/i)).toBeInTheDocument();

    await placeADrop();

    expect(screen.queryByText(/nothing is out/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/^dropped at /i)).toHaveLength(1);
    expect(
      screen.getAllByRole("button", { name: /^collected$/i }),
    ).toHaveLength(1);
  });

  test("clearing a crate takes two taps and removes only that row", async () => {
    installFetchMock(routes());
    render(<CourierPanel />);

    await placeADrop();
    await placeADrop();
    expect(screen.getAllByText(/^dropped at /i)).toHaveLength(2);

    const clear = screen.getAllByRole("button", { name: /^collected$/i })[0];
    await clickAndFlush(clear);

    // Armed, and nothing has gone off any map yet
    expect(getAPICalls("admin_clear_drop")).toHaveLength(0);
    expect(clear).toHaveTextContent(/tap again/i);

    await clickAndFlush(clear);

    expect(getLastAPICall("admin_clear_drop").query).toMatchObject({
      drop_id: "drop-1",
    });
    expect(screen.getAllByText(/^dropped at /i)).toHaveLength(1);
  });

  test("cannot place a drop before there is a fix to place it at", async () => {
    installFetchMock(routes());
    render(<CourierPanel />);

    expect(
      await screen.findByRole("button", { name: /place drop here/i }),
    ).toBeDisabled();
  });
});
