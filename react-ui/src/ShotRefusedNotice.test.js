import { act, render, screen } from "@testing-library/react";

import ShotRefusedNotice, { VISIBLE_FOR_MS } from "./ShotRefusedNotice";
import prose from "./prose";
import { clearShotRefusal, reportShotRefusal } from "./shotRefusalStore";

beforeEach(() => {
  jest.useFakeTimers();
  clearShotRefusal();
});

afterEach(() => {
  jest.useRealTimers();
});

test("says nothing until a shot is refused", () => {
  render(<ShotRefusedNotice />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("shows the server's reason, then takes itself away", () => {
  render(<ShotRefusedNotice />);

  act(() => {
    reportShotRefusal("Still reloading - 12.3 s of cooldown left");
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

test("a refusal with no reason still says the shot did not happen", () => {
  render(<ShotRefusedNotice />);

  act(() => {
    reportShotRefusal(null);
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
  render(<ShotRefusedNotice />);

  act(() => {
    reportShotRefusal("Still reloading - 20.0 s of cooldown left");
  });
  act(() => {
    jest.advanceTimersByTime(VISIBLE_FOR_MS - 100);
  });
  act(() => {
    reportShotRefusal("Still reloading - 20.0 s of cooldown left");
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
  render(<ShotRefusedNotice />);

  act(() => {
    reportShotRefusal("Still reloading - 20.0 s of cooldown left");
  });
  act(() => {
    screen.getByRole("button").click();
  });

  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
