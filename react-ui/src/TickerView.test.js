import React from "react";
import { fireEvent, render, screen, act } from "@testing-library/react";

import TickerView from "./TickerView";
import { ShotHistoryController } from "./ShotHistory";
import { UpdateSSEConnection } from "./UpdateListener";
import {
  actAndFlush,
  installFetchMock,
  getAPICalls,
  getLastAPICall,
  emitUpdate,
  makeShot,
} from "./testUtils";
import styles from "./TickerView.module.css";

describe("player mode (no game_id)", () => {
  test("calls ticker_messages with num_messages", async () => {
    installFetchMock({ ticker_messages: [["ticker", "Something happened"]] });

    render(<TickerView num_messages={4} />);

    await screen.findByText("Something happened");
    const call = getLastAPICall("ticker_messages");
    expect(call.query).toEqual({ num_messages: "4" });
    expect(getAPICalls("admin_ticker_messages")).toHaveLength(0);
  });

  test("renders each message as a list item using [class, text]", async () => {
    installFetchMock({
      ticker_messages: [
        ["ticker", "Plain message"],
        ["highlight", "Big event"],
      ],
    });

    render(<TickerView />);

    const plain = await screen.findByText("Plain message");
    expect(plain.tagName).toBe("LI");
    expect(plain).toHaveClass("ticker");

    const highlight = screen.getByText("Big event");
    expect(highlight.tagName).toBe("LI");
    expect(highlight).toHaveClass("highlight");
  });

  test("refreshes on a ticker update, not on an admin update", async () => {
    let call = 0;
    installFetchMock({
      ticker_messages: () => {
        call += 1;
        return [["ticker", `message ${call}`]];
      },
    });

    render(
      <>
        <TickerView />
        <UpdateSSEConnection />
      </>,
    );

    await screen.findByText("message 1");

    act(() => {
      emitUpdate("ticker");
    });
    await screen.findByText("message 2");

    act(() => {
      emitUpdate("admin");
    });
    // Give any (unwanted) refetch a chance to happen before asserting it
    // didn't.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(getAPICalls("ticker_messages")).toHaveLength(2);
  });

  // The private "you were hit" line carries the shot id so the line itself is
  // the way in to the shot - and to appealing it (roadmap R8).
  test("a private line about one of this player's shots opens it in the history", async () => {
    installFetchMock({
      ticker_messages: [["user", "You were hit by Bob!", "shot-7"]],
      user_shots: [makeShot({ id: "shot-7", checked: true, result: "hit" })],
      user_shots_received: [],
      user_info: { appeals_remaining: 3 },
      user_shot_image: { image_base64: null },
    });

    await actAndFlush(() =>
      render(
        <>
          <TickerView />
          <ShotHistoryController />
        </>,
      ),
    );

    await actAndFlush(() =>
      fireEvent.click(
        screen.getByRole("button", { name: "You were hit by Bob!" }),
      ),
    );

    expect(screen.getByText(/All shots/)).toBeInTheDocument();
  });

  test("a line with no shot attached stays plain text", async () => {
    installFetchMock({
      ticker_messages: [
        ["user", "You were given 1x ammo!", null],
        ["public", "The next circle has been announced!", "shot-7"],
      ],
    });

    render(<TickerView />);

    const line = await screen.findByText("You were given 1x ammo!");
    expect(line.tagName).toBe("LI");
    // A public line about somebody else's shot is not this player's to open.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  test("uses the user-mode style class", async () => {
    installFetchMock({ ticker_messages: [] });
    const { container } = render(<TickerView />);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const div = container.querySelector(`.${styles.tickerview}`);
    expect(div).toHaveClass(styles.userTickerview);
    expect(div).not.toHaveClass(styles.adminTickerview);
  });
});

describe("admin mode (with game_id)", () => {
  test("calls admin_ticker_messages with game_id and num_messages", async () => {
    installFetchMock({
      admin_ticker_messages: [["ticker", "Admin message"]],
    });

    render(<TickerView admin game_id="game-42" num_messages={7} />);

    await screen.findByText("Admin message");
    const call = getLastAPICall("admin_ticker_messages");
    expect(call.query).toEqual({ game_id: "game-42", num_messages: "7" });
    expect(getAPICalls("ticker_messages")).toHaveLength(0);
  });

  test("refreshes on an admin update, not on a ticker update", async () => {
    let call = 0;
    installFetchMock({
      admin_ticker_messages: () => {
        call += 1;
        return [["ticker", `admin message ${call}`]];
      },
    });

    render(
      <>
        <TickerView admin game_id="game-42" />
        <UpdateSSEConnection />
      </>,
    );

    await screen.findByText("admin message 1");

    act(() => {
      emitUpdate("admin");
    });
    await screen.findByText("admin message 2");

    act(() => {
      emitUpdate("ticker");
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(getAPICalls("admin_ticker_messages")).toHaveLength(2);
  });

  test("uses the admin-mode style class", async () => {
    installFetchMock({ admin_ticker_messages: [] });
    const { container } = render(<TickerView admin game_id="game-42" />);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const div = container.querySelector(`.${styles.tickerview}`);
    expect(div).toHaveClass(styles.adminTickerview);
    expect(div).not.toHaveClass(styles.userTickerview);
  });
});
