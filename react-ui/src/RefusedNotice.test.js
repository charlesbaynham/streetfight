import { act, render, screen } from "@testing-library/react";

import RefusedNotice, { VISIBLE_FOR_MS } from "./RefusedNotice";
import prose from "./prose";
import { clearRefusal, reportRefusal } from "./refusalStore";

beforeEach(() => {
  jest.useFakeTimers();
  clearRefusal();
});

afterEach(() => {
  jest.useRealTimers();
});

test("says nothing until something is refused", () => {
  render(<RefusedNotice />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("shows the server's reason, then takes itself away", () => {
  render(<RefusedNotice />);

  act(() => {
    reportRefusal(
      prose.fireButton.shotRefused("Still reloading - 12.3 s of cooldown left"),
    );
  });
  expect(
    screen.getByText(
      prose.fireButton.shotRefused("Still reloading - 12.3 s of cooldown left"),
    ),
  ).toBeInTheDocument();

  act(() => {
    jest.advanceTimersByTime(VISIBLE_FOR_MS);
  });
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("renders whatever sentence the caller published", () => {
  render(<RefusedNotice />);

  act(() => {
    reportRefusal(prose.fireButton.shotRefusedUnknown);
  });

  expect(
    screen.getByText(prose.fireButton.shotRefusedUnknown),
  ).toBeInTheDocument();
});

test("a second identical refusal restarts the countdown", () => {
  // Two taps inside the cooldown produce the same sentence twice, and the
  // second tap is a thing the player did that has to be answered - keying on
  // the message rather than the refusal would let it expire on the first
  // tap's schedule.
  render(<RefusedNotice />);

  act(() => {
    reportRefusal(
      prose.fireButton.shotRefused("Still reloading - 20.0 s of cooldown left"),
    );
  });
  act(() => {
    jest.advanceTimersByTime(VISIBLE_FOR_MS - 100);
  });
  act(() => {
    reportRefusal(
      prose.fireButton.shotRefused("Still reloading - 20.0 s of cooldown left"),
    );
  });

  act(() => {
    jest.advanceTimersByTime(200);
  });
  expect(screen.getByRole("button")).toBeInTheDocument();

  act(() => {
    jest.advanceTimersByTime(VISIBLE_FOR_MS);
  });
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("tapping it dismisses it early", () => {
  render(<RefusedNotice />);

  act(() => {
    reportRefusal(
      prose.fireButton.shotRefused("Still reloading - 20.0 s of cooldown left"),
    );
  });
  act(() => {
    screen.getByRole("button").click();
  });

  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
