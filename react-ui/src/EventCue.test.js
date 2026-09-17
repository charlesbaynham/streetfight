import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import EventCue from "./EventCue";
import { getLastAPICall, installFetchMock, makeGame } from "./testUtils";

const renderCue = (overrides = {}) => {
  installFetchMock({ admin_cue_next_event: {}, admin_cancel_cue: {} });
  return render(<EventCue game={makeGame({ id: "game-1", ...overrides })} />);
};

test("it says whether anything is cued, and what", () => {
  renderCue();
  expect(screen.getByText(/Nothing cued/)).toBeInTheDocument();

  renderCue({
    next_event_kind: "drop",
    next_event_at: Date.now() / 1000 + 300,
    next_event_note: "a medpack",
  });
  expect(screen.getByText(/Counting down to/)).toBeInTheDocument();
  expect(screen.getByText(/in 5 min/)).toBeInTheDocument();
  expect(screen.getByText(/a medpack/)).toBeInTheDocument();
});

test("the circle default is ten minutes, and it posts what is on screen", async () => {
  renderCue();

  await userEvent.click(
    screen.getByRole("button", { name: /Start countdown/ }),
  );

  expect(getLastAPICall("admin_cue_next_event").query).toEqual({
    game_id: "game-1",
    kind: "circle",
    minutes: "10",
  });
});

test("a drop asks what is in it; a circle does not", async () => {
  renderCue();
  const contents = /what's in it/;
  expect(screen.queryByPlaceholderText(contents)).toBeNull();

  await userEvent.selectOptions(screen.getByRole("combobox"), "drop");

  const box = screen.getByPlaceholderText(contents);
  await userEvent.type(box, "two armour");
  await userEvent.click(
    screen.getByRole("button", { name: /Start countdown/ }),
  );

  const query = getLastAPICall("admin_cue_next_event").query;
  expect(query.kind).toBe("drop");
  expect(query.note).toBe("two armour");
  // Switching kind takes that kind's own default with it, rather than leaving
  // the circle's ten minutes in the box.
  expect(query.minutes).toBe("5");
});

test("cancelling posts the cancel", async () => {
  renderCue({
    next_event_kind: "circle",
    next_event_at: Date.now() / 1000 + 60,
  });

  await userEvent.click(
    screen.getByRole("button", { name: /Cancel countdown/ }),
  );

  expect(getLastAPICall("admin_cancel_cue").query).toEqual({
    game_id: "game-1",
  });
});
