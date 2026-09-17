import React from "react";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ResetToStartButton from "./ResetToStartButton";
import { installFetchMock, getAPICalls } from "./testUtils";

const pausedGame = { id: "game-1", active: false };
const runningGame = { id: "game-1", active: true };

async function clickAndFlush(element) {
  await act(async () => {
    await userEvent.click(element);
  });
}

describe("ResetToStartButton", () => {
  test("takes two taps to fire", async () => {
    installFetchMock({ admin_reset_to_start_state: {} });

    render(<ResetToStartButton game={pausedGame} />);

    const button = screen.getByRole("button");
    await clickAndFlush(button);

    // Armed, and saying so - but nothing has been sent
    expect(getAPICalls("admin_reset_to_start_state")).toHaveLength(0);
    expect(button).toHaveTextContent(/tap again/i);

    await clickAndFlush(button);

    const calls = getAPICalls("admin_reset_to_start_state");
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].query.game_id).toBe("game-1");
  });

  test("refuses to arm at all while the game is running", async () => {
    installFetchMock({ admin_reset_to_start_state: {} });

    render(<ResetToStartButton game={runningGame} />);

    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(screen.getByText(/pause it first/i)).toBeInTheDocument();
  });

  test("says why the server refused, beside the button", async () => {
    installFetchMock({
      admin_reset_to_start_state: {
        status: 400,
        body: {
          detail: "Pause the game before resetting it to the start state",
        },
      },
    });

    render(<ResetToStartButton game={pausedGame} />);

    const button = screen.getByRole("button");
    await clickAndFlush(button);
    await clickAndFlush(button);

    expect(
      await screen.findByText(/pause the game before resetting/i),
    ).toBeInTheDocument();
  });
});
