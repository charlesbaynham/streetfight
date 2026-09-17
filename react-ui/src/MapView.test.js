import { fireEvent, render, screen } from "@testing-library/react";

import { VenueMapView } from "./MapView";
import { mapGeometry } from "./venue";
import prose from "./prose";

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
    screen.queryByRole("button", { name: prose.mapView.closeMapLabel }),
  ).not.toBeInTheDocument();

  fireEvent.click(clickCatcher());

  expect(onExpandedChange).toHaveBeenLastCalledWith(true);
  expect(
    screen.getByRole("button", { name: prose.mapView.closeMapLabel }),
  ).toBeInTheDocument();
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
  expect(
    screen.getByRole("button", { name: prose.mapView.closeMapLabel }),
  ).toBeInTheDocument();
});

test("the explicit close button collapses a popped-out map", () => {
  const onExpandedChange = jest.fn();
  renderMap({ onExpandedChange });

  fireEvent.click(clickCatcher());
  expect(
    screen.getByRole("button", { name: prose.mapView.closeMapLabel }),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", { name: prose.mapView.closeMapLabel }),
  );

  expect(onExpandedChange).toHaveBeenLastCalledWith(false);
  expect(
    screen.queryByRole("button", { name: prose.mapView.closeMapLabel }),
  ).not.toBeInTheDocument();
});

test("an always-expanded map (admin view) shows no close button and ignores taps", () => {
  const onExpandedChange = jest.fn();
  renderMap({ alwaysExpanded: true, onExpandedChange });

  expect(
    screen.queryByRole("button", { name: prose.mapView.closeMapLabel }),
  ).not.toBeInTheDocument();

  fireEvent.click(clickCatcher());

  expect(
    screen.queryByRole("button", { name: prose.mapView.closeMapLabel }),
  ).not.toBeInTheDocument();
});

// -- the courier and the crate (M4.2) ---------------------------------------

const DROP = {
  drop_circle_lat: 51.5,
  drop_circle_long: -0.1,
  drop_circle_radius: 0.01,
};

const courier = () => screen.queryByTestId("map-courier-dot");
const crate = () => screen.queryByTestId("map-drop-crate");

test("no drop and no courier means neither is drawn", () => {
  renderMap({ circles: {} });
  expect(crate()).toBeNull();
  expect(courier()).toBeNull();
});

test("a drop circle gets a crate at its centre", () => {
  renderMap({ circles: DROP });
  expect(crate()).not.toBeNull();
});

test("every crate the courier has out gets its own circle and marker", () => {
  // The admin's single map-placed drop and two of the courier's (M4.3): three
  // crates, because a second courier drop must not take the first off the map.
  renderMap({
    circles: {
      ...DROP,
      drops: [
        { id: "a", lat: 51.51, long: -0.11, radius: 0.02 },
        { id: "b", lat: 51.52, long: -0.12, radius: 0.02 },
      ],
    },
  });

  expect(screen.getAllByTestId("map-drop-crate")).toHaveLength(3);
});

test("a server too old to send any drops draws none", () => {
  renderMap({ circles: { drops: undefined } });
  expect(crate()).toBeNull();
});

test("the courier is drawn from either shape the server sends", () => {
  // /get_circles nests it...
  renderMap({
    circles: {
      courier: { lat: 51.5, long: -0.1, timestamp: Date.now() / 1000 },
    },
  });
  expect(courier()).not.toBeNull();

  // ...and a GameModel, which is what the spectator screen passes, is flat.
  renderMap({
    circles: {
      courier_lat: 51.5,
      courier_long: -0.1,
      courier_timestamp: Date.now() / 1000,
    },
  });
  expect(screen.getAllByTestId("map-courier-dot")).toHaveLength(2);
});

test("a courier who stopped broadcasting fades out and then goes", () => {
  const { unmount } = renderMap({
    circles: {
      courier: { lat: 51.5, long: -0.1, timestamp: Date.now() / 1000 - 120 },
    },
  });

  // Two minutes of silence from a courier who reports once a second is
  // somebody who is no longer there, and a plausible aeroplane sitting where
  // they used to be is worse than none.
  expect(courier()).toBeNull();
  unmount();

  renderMap({
    circles: {
      courier: { lat: 51.5, long: -0.1, timestamp: Date.now() / 1000 - 30 },
    },
  });
  expect(courier()).not.toBeNull();
});
