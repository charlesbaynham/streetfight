import { render, screen } from "@testing-library/react";

import ShotMap, { otherFixes, shooterFix } from "./ShotMap";
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

// The moment the photograph was taken. Naive UTC, exactly as the backend
// serialises it - reading it as local time is the bug shotEpochSeconds exists
// to avoid, so the fixtures must not paper over it with a "Z".
const SHOT_TIME = "2026-08-30T12:00:00";
const SHOT_EPOCH = Date.parse(`${SHOT_TIME}Z`) / 1000;

// A tenth of a degree of latitude is 11 km; these are the fractions of that
// which put somebody inside or outside the 200 m box.
const METRE_IN_DEGREES_LAT = 1 / 110574;

// The shooter is always the middle of the 220 px box (ShotMap's BOX_PX).
const BOX_CENTRE_PX = 110;

function locationEntry(overrides) {
  return {
    user_id: "u-shooter",
    team_id: "t-red",
    user: "Shooty McShootface",
    team: "Red",
    latitude: 51.5,
    longitude: -0.1,
    state: "alive",
    timestamp: SHOT_EPOCH,
    accuracy: null,
    ...overrides,
  };
}

// A player standing `metres` north of the shooter, on the other team unless
// told otherwise.
function otherEntry(metres, overrides = {}) {
  return locationEntry({
    user_id: `u-${metres}`,
    team_id: "t-blue",
    user: `Player at ${metres} m`,
    team: "Blue",
    latitude: 51.5 + metres * METRE_IN_DEGREES_LAT,
    ...overrides,
  });
}

function makeShot(overrides = {}, fixOverrides = {}) {
  return {
    id: "shot-1",
    user_id: "u-shooter",
    heading: null,
    time_created: SHOT_TIME,
    location_context: JSON.stringify([
      locationEntry(fixOverrides),
      locationEntry({ user_id: "u-other", user: "Someone else" }),
    ]),
    ...overrides,
  };
}

// A shot whose context is the shooter plus whatever entries are given.
function makeShotWithOthers(entries, overrides = {}) {
  return makeShot({
    location_context: JSON.stringify([locationEntry({}), ...entries]),
    ...overrides,
  });
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

describe("otherFixes", () => {
  test("orders everybody else by how far they were from the shooter", () => {
    const shot = makeShotWithOthers([otherEntry(120), otherEntry(30)]);

    const [nearest, furthest] = otherFixes(shot);

    expect(nearest.fix.user).toBe("Player at 30 m");
    // Precision -1: the fixtures place people with a flat metres-per-degree
    // constant, which the great circle disagrees with by well under a metre.
    expect(nearest.distance).toBeCloseTo(30, -1);
    expect(furthest.distance).toBeCloseTo(120, -1);
  });

  test("ages each fix against the shot, not against the wall clock", () => {
    const shot = makeShotWithOthers([
      otherEntry(30, { timestamp: SHOT_EPOCH - 300 }),
    ]);

    expect(otherFixes(shot)[0].ageSeconds).toBe(300);
  });

  test("reports an unknown age rather than a fresh one when there is no timestamp", () => {
    const shot = makeShotWithOthers([otherEntry(30, { timestamp: null })]);

    expect(otherFixes(shot)[0].ageSeconds).toBeNull();
  });

  test("marks the shooter's own team, and anybody who isn't alive", () => {
    const shot = makeShotWithOthers([
      otherEntry(30, { team_id: "t-red" }),
      otherEntry(60, { state: "knocked out" }),
    ]);

    const [teammate, down] = otherFixes(shot);

    expect(teammate.teammate).toBe(true);
    expect(down.teammate).toBe(false);
    expect(down.down).toBe(true);
  });

  test("drops players whose phone had never reported a position", () => {
    const shot = makeShotWithOthers([
      otherEntry(30),
      otherEntry(60, { latitude: null, longitude: null }),
    ]);

    expect(otherFixes(shot).map((other) => other.fix.user)).toEqual([
      "Player at 30 m",
    ]);
  });

  test("has nothing to measure against when the shooter has no fix", () => {
    const shot = makeShot({ user_id: "u-nobody" });

    expect(otherFixes(shot)).toEqual([]);
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

  test("draws the other players who were in the area, by name", async () => {
    const box = await renderMap(
      makeShotWithOthers([otherEntry(40), otherEntry(80)]),
    );

    expect(screen.getByText("Player at 40 m")).toBeInTheDocument();
    expect(screen.getByText("Player at 80 m")).toBeInTheDocument();
    expect(screen.getByText(/2 others in view/)).toBeInTheDocument();
    // North of the shooter, so above the centre of the box, and the further
    // player is the higher of the two.
    const [near, far] = ["Player at 40 m", "Player at 80 m"].map((name) =>
      Number.parseFloat(screen.getByText(name).parentElement.style.bottom),
    );
    expect(near).toBeGreaterThan(BOX_CENTRE_PX);
    expect(far).toBeGreaterThan(near);
    expect(box).toBeInTheDocument();
  });

  test("leaves out players too far away to fit on the map, and says how many", async () => {
    await renderMap(makeShotWithOthers([otherEntry(40), otherEntry(400)]));

    expect(screen.getByText("Player at 40 m")).toBeInTheDocument();
    expect(screen.queryByText("Player at 400 m")).not.toBeInTheDocument();
    expect(screen.getByText(/1 other in view/)).toBeInTheDocument();
    expect(screen.getByText(/1 off the map/)).toBeInTheDocument();
  });

  test("says so when nobody else was about", async () => {
    await renderMap(makeShotWithOthers([]));

    expect(screen.getByText(/nobody else in view/)).toBeInTheDocument();
  });

  test("labels a fix too old to place somebody by with its age", async () => {
    await renderMap(
      makeShotWithOthers([otherEntry(40, { timestamp: SHOT_EPOCH - 600 })]),
    );

    expect(screen.getByText("Player at 40 m (10m old)")).toBeInTheDocument();
  });

  test("says in words that a player was out, rather than only greying them", async () => {
    await renderMap(
      makeShotWithOthers([otherEntry(40, { state: "knocked out" })]),
    );

    expect(
      screen.getByText("Player at 40 m (knocked out)"),
    ).toBeInTheDocument();
  });

  test("draws only the nearest few when a crowd was in the box", async () => {
    const crowd = [10, 20, 30, 40, 50, 60, 70, 80, 90].map((m) =>
      otherEntry(m),
    );

    await renderMap(makeShotWithOthers(crowd));

    expect(screen.getByText("Player at 10 m")).toBeInTheDocument();
    expect(screen.queryByText("Player at 90 m")).not.toBeInTheDocument();
    expect(screen.getByText(/nearest 8 drawn/)).toBeInTheDocument();
  });

  test("explains what the hollow dots mean, but only when there are some", async () => {
    await renderMap(makeShotWithOthers([otherEntry(40, { team_id: "t-red" })]));
    expect(screen.getByText(/hollow dots/)).toBeInTheDocument();
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
