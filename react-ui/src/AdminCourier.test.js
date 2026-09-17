import React from "react";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CourierPanel } from "./AdminCourier";
import { installFetchMock, getAPICalls, getLastAPICall } from "./testUtils";

const GAME = { id: "game-1", teams: [{ name: "Red" }] };

const FIX = {
  coords: { latitude: 51.5, longitude: -0.13, accuracy: 8 },
};

function routes(extra = {}) {
  return {
    admin_list_games: [GAME],
    admin_set_courier_location: {},
    admin_clear_courier: {},
    admin_set_circle: {},
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
    expect(getAPICalls("admin_set_circle")).toHaveLength(0);
    expect(place).toHaveTextContent(/tap again/i);

    await clickAndFlush(place);

    // It goes through the ordinary circle endpoint, so the ticker message and
    // the circle event are the ones an admin placing it from the map fires
    const circle = getLastAPICall("admin_set_circle");
    expect(circle.query).toMatchObject({
      game_id: "game-1",
      name: "DROP",
      lat: "51.5",
      long: "-0.13",
    });

    // The crate is down, so the courier is no longer worth following
    expect(getAPICalls("admin_clear_courier")).toHaveLength(1);
    expect(screen.getByText(/not broadcasting/i)).toBeInTheDocument();
  });

  test("cannot place a drop before there is a fix to place it at", async () => {
    installFetchMock(routes());
    render(<CourierPanel />);

    expect(
      await screen.findByRole("button", { name: /place drop here/i }),
    ).toBeDisabled();
  });
});
