import { fireEvent, render, screen } from "@testing-library/react";

import { VenueMapView } from "./MapView";
import { mapGeometry } from "./venue";

// The venue used to derive a real geometry object - same shape as
// ShotMap.test.js's fixture, since VenueMapView just wants whatever
// mapGeometry(venue) produces.
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

const GEOMETRY = mapGeometry(VENUE);

function renderMap(overrides = {}) {
  return render(
    <VenueMapView
      geometry={GEOMETRY}
      circles={[]}
      onExpandedChange={() => {}}
      {...overrides}
    />,
  );
}

function clickCatcher() {
  return screen.getByTestId("map-click-catcher");
}

test("tapping the corner map pops it out", () => {
  const onExpandedChange = jest.fn();
  renderMap({ onExpandedChange });

  expect(
    screen.queryByRole("button", { name: "Close map" }),
  ).not.toBeInTheDocument();

  fireEvent.click(clickCatcher());

  expect(onExpandedChange).toHaveBeenLastCalledWith(true);
  expect(screen.getByRole("button", { name: "Close map" })).toBeInTheDocument();
});

// The dry-run report: "zooming on the map is reliably terrible". Root cause
// was the click catcher sitting inside the zoomable TransformComponent with
// no gate on poppedOut, so any tap once popped out - including the tap a
// pinch-zoom gesture ends with - collapsed the map straight back down.
test("tapping the map again once popped out does not collapse it", () => {
  const onExpandedChange = jest.fn();
  renderMap({ onExpandedChange });

  fireEvent.click(clickCatcher());
  expect(onExpandedChange).toHaveBeenLastCalledWith(true);

  fireEvent.click(clickCatcher());

  expect(onExpandedChange).toHaveBeenLastCalledWith(true);
  expect(screen.getByRole("button", { name: "Close map" })).toBeInTheDocument();
});

test("the explicit close button collapses a popped-out map", () => {
  const onExpandedChange = jest.fn();
  renderMap({ onExpandedChange });

  fireEvent.click(clickCatcher());
  expect(screen.getByRole("button", { name: "Close map" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Close map" }));

  expect(onExpandedChange).toHaveBeenLastCalledWith(false);
  expect(
    screen.queryByRole("button", { name: "Close map" }),
  ).not.toBeInTheDocument();
});

test("an always-expanded map (admin view) shows no close button and ignores taps", () => {
  const onExpandedChange = jest.fn();
  renderMap({ alwaysExpanded: true, onExpandedChange });

  expect(
    screen.queryByRole("button", { name: "Close map" }),
  ).not.toBeInTheDocument();

  fireEvent.click(clickCatcher());

  expect(
    screen.queryByRole("button", { name: "Close map" }),
  ).not.toBeInTheDocument();
});
