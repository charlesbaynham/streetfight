import { render, screen } from "@testing-library/react";

import ShotMap, { shooterFix } from "./ShotMap";
import { installFetchMock } from "./testUtils";

// The venue the admin map is drawn against - the same shape backend/venues.py
// serves, sized so the arithmetic is easy to follow.
const VENUE = {
  name: "Test venue",
  map: {
    image: "koyao_resort",
    width_px: 100,
    height_px: 100,
    ref_1: { x: 0, y: 0, lat: 51.51, long: -0.11 },
    ref_2: { x: 100, y: 100, lat: 51.49, long: -0.09 },
    corner_width_km: 0.08,
  },
  landmarks: {},
};

function locationEntry(overrides) {
  return {
    user_id: "u-shooter",
    team_id: "t-red",
    user: "Shooty McShootface",
    team: "Red",
    latitude: 51.5,
    longitude: -0.1,
    state: "alive",
    timestamp: 0,
    accuracy: null,
    ...overrides,
  };
}

function makeShot(overrides = {}, fixOverrides = {}) {
  return {
    id: "shot-1",
    user_id: "u-shooter",
    heading: null,
    location_context: JSON.stringify([
      locationEntry(fixOverrides),
      locationEntry({ user_id: "u-other", user: "Someone else" }),
    ]),
    ...overrides,
  };
}

// The numbers in the rendered path's `d` attribute, in order.
function pathNumbers(path) {
  return path
    .getAttribute("d")
    .match(/-?\d+(\.\d+)?(e-?\d+)?/g)
    .map(Number);
}

describe("shooterFix", () => {
  test("picks the shooter's own entry out of the location context", () => {
    const fix = shooterFix(makeShot({}, { latitude: 51.4, longitude: -0.2 }));
    expect(fix.latitude).toBe(51.4);
    expect(fix.longitude).toBe(-0.2);
  });

  test.each([
    ["no location context at all", { location_context: null }],
    ["unparseable context", { location_context: "{not json" }],
    ["a context the shooter isn't in", { user_id: "u-nobody" }],
  ])("reports no fix for %s", (_label, overrides) => {
    expect(shooterFix(makeShot(overrides))).toBeNull();
  });

  test("reports no fix for a shooter whose phone never reported a position", () => {
    const shot = makeShot({}, { latitude: null, longitude: null });
    expect(shooterFix(shot)).toBeNull();
  });
});

describe("ShotMap", () => {
  async function renderMap(shot) {
    installFetchMock({ get_venue: VENUE });
    render(<ShotMap shot={shot} />);
    return await screen.findByTestId("shot-map");
  }

  test("says so, quietly, when a shot has no position recorded", async () => {
    installFetchMock({ get_venue: VENUE });
    render(<ShotMap shot={makeShot({ location_context: null })} />);

    expect(
      await screen.findByText(/no position recorded/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("shot-map")).not.toBeInTheDocument();
  });

  test("draws the heading cone in the direction the shot was fired", async () => {
    const box = await renderMap(makeShot({ heading: 90 }));
    const path = box.querySelector("svg path");

    // Cone apex first, then the two edges. Due east: both edges are to the
    // right of the apex, and straddle it vertically.
    const [apexX, apexY, edge1X, edge1Y, ...rest] = pathNumbers(path);
    const edge2X = rest[rest.length - 2];
    const edge2Y = rest[rest.length - 1];

    expect(edge1X).toBeGreaterThan(apexX);
    expect(edge2X).toBeGreaterThan(apexX);
    // SVG y grows downwards, so one edge is above the apex and one below.
    expect(Math.sign(edge1Y - apexY)).toBe(-Math.sign(edge2Y - apexY));
  });

  test("points the cone north for a heading of zero", async () => {
    const box = await renderMap(makeShot({ heading: 0 }));
    const [apexX, apexY, edge1X, edge1Y] = pathNumbers(
      box.querySelector("svg path"),
    );

    expect(edge1Y).toBeLessThan(apexY); // north is up the screen
    expect(edge1X).toBeLessThan(apexX); // ...and this is the anticlockwise edge
  });

  test("omits the cone, but still shows the map, when there is no heading", async () => {
    const box = await renderMap(makeShot({ heading: null }));

    expect(box.querySelector("svg")).toBeNull();
    expect(screen.getByText(/no heading/)).toBeInTheDocument();
  });

  test("shows the accuracy of the fix when there is one", async () => {
    await renderMap(makeShot({ heading: 12 }, { accuracy: 17.4 }));
    expect(screen.getByText(/±17 m/)).toBeInTheDocument();
  });

  test("says the accuracy is unknown for a fix recorded before it was captured", async () => {
    await renderMap(makeShot({}, { accuracy: null }));
    expect(screen.getByText(/accuracy unknown/)).toBeInTheDocument();
  });
});
