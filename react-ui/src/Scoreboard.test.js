import React from "react";
import { render, screen, act, fireEvent } from "@testing-library/react";

import Scoreboard, { ButtonAndScoreboard } from "./Scoreboard";
import { UpdateSSEConnection } from "./UpdateListener";
import { installFetchMock, getAPICalls, emitUpdate } from "./testUtils";
import styles from "./Scoreboard.module.css";

function scoreRow(overrides = {}) {
  return {
    name: "Alice",
    team: "Red",
    hitpoints: 3,
    total_damage: 5,
    state: "alive",
    ...overrides,
  };
}

describe("Scoreboard", () => {
  test("renders a row per player with name/team/armour/damage", async () => {
    installFetchMock({
      get_scoreboard: {
        table: [
          scoreRow({ name: "Alice", hitpoints: 3, total_damage: 5 }),
          scoreRow({ name: "Bob", hitpoints: 0, total_damage: 0 }),
        ],
      },
    });

    render(<Scoreboard />);

    const aliceRow = (await screen.findByText("Alice")).closest("tr");
    expect(aliceRow).toHaveTextContent("Alice");
    expect(aliceRow).toHaveTextContent("Red");
    // armour = hitpoints - 1
    const aliceCells = aliceRow.querySelectorAll("td");
    expect(aliceCells[2]).toHaveTextContent("2");
    expect(aliceCells[3]).toHaveTextContent("5");

    // armour is clamped at 0, not negative, when hitpoints is 0.
    const bobRow = screen.getByText("Bob").closest("tr");
    expect(bobRow.querySelectorAll("td")[2]).toHaveTextContent("0");
  });

  test("gives each row the style class matching the player's state", async () => {
    installFetchMock({
      get_scoreboard: {
        table: [
          scoreRow({ name: "Alice", state: "alive" }),
          scoreRow({ name: "Bob", state: "knocked out" }),
          scoreRow({ name: "Carl", state: "dead" }),
        ],
      },
    });

    render(<Scoreboard />);

    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Alice").closest("tr")).toHaveClass(styles.alive);
    // The space in "knocked out" is replaced with an underscore to look up
    // the style class.
    expect(screen.getByText("Bob").closest("tr")).toHaveClass(
      styles.knocked_out,
    );
    expect(screen.getByText("Carl").closest("tr")).toHaveClass(styles.dead);
  });

  test("renders nothing before the fetch resolves", async () => {
    installFetchMock({ get_scoreboard: { table: [] } });
    render(<Scoreboard />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    // Let the (empty) response resolve so no state update leaks past the
    // end of this test.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  });

  test("does not blow up when the endpoint fails", async () => {
    installFetchMock({
      get_scoreboard: { status: 500, body: { error: "boom" } },
    });

    render(<Scoreboard />);

    // Give the failed fetch a chance to resolve; the component should stay
    // tableless rather than throwing.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  test("refreshes when a ticker SSE update arrives", async () => {
    let call = 0;
    installFetchMock({
      get_scoreboard: () => {
        call += 1;
        return { table: [scoreRow({ name: `Player${call}` })] };
      },
    });

    render(
      <>
        <Scoreboard />
        <UpdateSSEConnection />
      </>,
    );

    await screen.findByText("Player1");
    expect(getAPICalls("get_scoreboard")).toHaveLength(1);

    act(() => {
      emitUpdate("ticker");
    });

    await screen.findByText("Player2");
    expect(getAPICalls("get_scoreboard")).toHaveLength(2);
  });
});

describe("ButtonAndScoreboard", () => {
  test("the scoreboard is hidden until 'Show scores >>' is clicked", async () => {
    installFetchMock({
      get_scoreboard: { table: [scoreRow({ name: "Alice" })] },
    });

    render(<ButtonAndScoreboard />);

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(getAPICalls("get_scoreboard")).toHaveLength(0);

    fireEvent.click(screen.getByText("Show scores >>"));

    expect(await screen.findByText("Alice")).toBeInTheDocument();
  });

  test("the standalone prop adds its style class to the button", () => {
    render(<ButtonAndScoreboard standalone />);
    expect(screen.getByText("Show scores >>")).toHaveClass(styles.standalone);
  });

  test("without standalone, the button does not have the standalone class", () => {
    render(<ButtonAndScoreboard />);
    expect(screen.getByText("Show scores >>")).not.toHaveClass(
      styles.standalone,
    );
  });
});
