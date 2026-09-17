import React from "react";
import { act, render, screen } from "@testing-library/react";

import NextEventStrip from "./NextEventStrip";
import { makeUser, proseFragment } from "./testUtils";
import prose from "./prose";

// Epoch *seconds*, as the backend stores them.
const inSeconds = (seconds) => Date.now() / 1000 + seconds;

const renderStrip = (overrides) =>
  render(<NextEventStrip user={makeUser(overrides)} />);

const strip = () => screen.queryByTestId("next-event-strip");

test("nothing is drawn when nothing is cued", () => {
  renderStrip();
  expect(strip()).toBeNull();
});

test("a cued drop says so, counts down, and carries the admin's note", () => {
  renderStrip({
    next_event_kind: "drop",
    next_event_at: inSeconds(125),
    next_event_note: "a medpack and two armour",
  });

  expect(strip()).not.toBeNull();
  expect(screen.getByText(prose.nextEvent.dropLabel)).toBeInTheDocument();
  expect(screen.getByText(/02:0[45]/)).toBeInTheDocument();
  expect(
    screen.getByText(proseFragment("a medpack and two armour")),
  ).toBeInTheDocument();
});

test("a cued circle is a different announcement from a drop", () => {
  renderStrip({ next_event_kind: "circle", next_event_at: inSeconds(60) });

  expect(screen.getByText(prose.nextEvent.circleLabel)).toBeInTheDocument();
  expect(screen.queryByText(prose.nextEvent.dropLabel)).toBeNull();
});

test("a kind this bundle does not know is not guessed at", () => {
  renderStrip({ next_event_kind: "fireworks", next_event_at: inSeconds(60) });
  expect(strip()).toBeNull();
});

test("the clock is replaced by what is happening once it runs out", () => {
  jest.useFakeTimers();
  try {
    renderStrip({ next_event_kind: "circle", next_event_at: inSeconds(5) });

    expect(screen.getByText(prose.nextEvent.circleLabel)).toBeInTheDocument();

    // The server clears the cue when it fires, but that arrives as an
    // ordinary "user" update a moment later: until it does, the strip must
    // not sit on a stopped 00:00.
    act(() => {
      jest.advanceTimersByTime(6000);
    });

    expect(screen.getByText(prose.nextEvent.circleNow)).toBeInTheDocument();
    expect(screen.queryByText(prose.nextEvent.circleLabel)).toBeNull();
  } finally {
    jest.useRealTimers();
  }
});
