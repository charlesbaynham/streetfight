import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import CircleControl from "./CircleControl";
import {
  actAndFlush,
  getLastAPICall,
  installFetchMock,
  makeGame,
} from "./testUtils";

const PLAN = [
  { index: 0, name: "CIRCLE0", radius_km: 0.7, known: true },
  { index: 1, name: "CIRCLE1", radius_km: 0.42, known: true },
  { index: 2, name: "CIRCLE2", radius_km: 0.18, known: false },
  { index: 3, name: "CIRCLE3", radius_km: null, known: false },
];

const renderControl = (overrides = {}, plan = PLAN) => {
  installFetchMock({
    admin_get_landmarks: ["BIG_BEN"],
    admin_get_circle_plan: plan,
    admin_arm_planned_circle: {},
    admin_set_circle_by_location: {},
  });
  return actAndFlush(() =>
    render(<CircleControl game={makeGame({ id: "game-1", ...overrides })} />),
  );
};

test("it says which planned circle is up and whether it is on the map", async () => {
  await renderControl({ circle_plan_index: 1, next_circle_lat: 51.5 });

  expect(screen.getByText("CIRCLE1")).toBeInTheDocument();
  expect(screen.getByText(/private/)).toBeInTheDocument();
});

test("a planned circle with no coordinates says so rather than looking armed", async () => {
  await renderControl({ circle_plan_index: 2, next_circle_lat: null });

  expect(screen.getByText(/no coordinates/)).toBeInTheDocument();
});

test("a planned circle with no radius says which half is missing", async () => {
  await renderControl({ circle_plan_index: 3, next_circle_lat: null });

  expect(screen.getByText(/no radius/)).toBeInTheDocument();
});

test("a plan that has run out is not a circle waiting to be placed", async () => {
  await renderControl({ circle_plan_index: 4 });

  expect(screen.getByText("finished")).toBeInTheDocument();
});

test("skipping arms the entry after the one the game is on", async () => {
  await renderControl({ circle_plan_index: 1 });

  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", { name: /Skip to the next one/ }),
    ),
  );

  expect(getLastAPICall("admin_arm_planned_circle").query).toEqual({
    game_id: "game-1",
    index: "2",
  });
});
