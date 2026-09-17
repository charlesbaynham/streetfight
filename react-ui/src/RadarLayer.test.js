import React from "react";
import { render, screen } from "@testing-library/react";

import RadarLayer, { RadarStrip } from "./RadarLayer";
import prose from "./prose";
import {
  actAndFlush,
  getAPICalls,
  installFetchMock,
  makeUser,
} from "./testUtils";

// Epoch *seconds*, as the backend stores User.radar_until.
const inSeconds = (seconds) => Date.now() / 1000 + seconds;

// The map hands the layer a projection; where a dot lands on screen is
// MapView's business, not this component's.
const calculators = { coordsToPixels: () => [10, 20] };

const contact = (overrides = {}) => ({
  name: "Alice",
  team: "Blue Team",
  lat: 51.0,
  long: -1.0,
  seconds_ago: 0,
  accuracy: 8,
  state: "alive",
  ...overrides,
});

// Both halves together, as user mode mounts them: the strip is what tells the
// layer inside the map that there is a radar to draw.
const renderRadar = (userOverrides = {}, contacts = []) => {
  installFetchMock({ radar: contacts });
  return actAndFlush(() =>
    render(
      <>
        <RadarStrip user={makeUser(userOverrides)} />
        <RadarLayer calculators={calculators} />
      </>,
    ),
  );
};

test("without a radar card nothing is drawn and nothing is asked for", async () => {
  await renderRadar({}, [contact()]);

  expect(screen.queryByTestId("radar-strip")).toBeNull();
  expect(screen.queryByTestId("radar-layer")).toBeNull();
  expect(getAPICalls("radar")).toHaveLength(0);
});

test("a radar that has already run out is the same as none at all", async () => {
  await renderRadar({ radar_until: inSeconds(-1) }, [contact()]);

  expect(screen.queryByTestId("radar-strip")).toBeNull();
  expect(getAPICalls("radar")).toHaveLength(0);
});

test("a live radar counts down and draws each contact with the age of its fix", async () => {
  await renderRadar({ radar_until: inSeconds(300), team_name: "Red Team" }, [
    contact(),
    contact({ name: "Bob", team: "Red Team", seconds_ago: 200 }),
  ]);

  expect(screen.getByTestId("radar-strip")).toBeInTheDocument();
  expect(screen.getByText(/0[45]:\d\d/)).toBeInTheDocument();

  expect(screen.getByText("Alice")).toBeInTheDocument();
  expect(screen.getByText(prose.radar.justNow)).toBeInTheDocument();

  expect(screen.getByText("Bob")).toBeInTheDocument();
  expect(screen.getByText(prose.radar.lastSeen(3))).toBeInTheDocument();
});

test("somebody who is out says so instead of how long ago they were seen", async () => {
  await renderRadar({ radar_until: inSeconds(300) }, [
    contact({ state: "dead", seconds_ago: 200 }),
  ]);

  expect(screen.getByText(prose.radar.out)).toBeInTheDocument();
  expect(screen.queryByText(prose.radar.lastSeen(3))).toBeNull();
});
