import { useEffect, useState } from "react";

import MAP_IMAGES from "./mapImages";
import { sendAPIRequest } from "./utils";

// The venue - the place this game is played - is defined once, on the server,
// in backend/venues.py. This module fetches it and works out everything the
// map view needs to draw it: where the map image sits on the globe, and how
// big it is on the ground.

const DEGREES_LATITUDE_PER_KM = 1 / 110.574;

// Turn a venue's two reference points into the corners of its map, and the
// scale factors for converting degrees to km at that latitude. The map is
// assumed to be north-up and linear in latitude / longitude, which is close
// enough over the couple of km a game covers.
export function mapGeometry(venue) {
  const { image, width_px, height_px, ref_1, ref_2, corner_width_km } =
    venue.map;

  const long_per_width_px = (ref_2.long - ref_1.long) / (ref_2.x - ref_1.x);
  const lat_per_height_px = (ref_2.lat - ref_1.lat) / (ref_2.y - ref_1.y);

  const bottomLeft = {
    long: ref_1.long - ref_1.x * long_per_width_px,
    lat: ref_1.lat + (height_px - ref_1.y) * lat_per_height_px,
  };
  const topRight = {
    long: ref_1.long + (width_px - ref_1.x) * long_per_width_px,
    lat: ref_1.lat - ref_1.y * lat_per_height_px,
  };

  const degreesLongitudePerKm =
    1 /
    (111.32 *
      Math.cos(((bottomLeft.lat + topRight.lat) / 2) * (Math.PI / 180)));

  return {
    mapSrc: MAP_IMAGES[image],
    bottomLeft,
    topRight,
    degreesLongitudePerKm,
    degreesLatitudePerKm: DEGREES_LATITUDE_PER_KM,
    widthKm: (topRight.long - bottomLeft.long) / degreesLongitudePerKm,
    heightKm: (topRight.lat - bottomLeft.lat) / DEGREES_LATITUDE_PER_KM,
    // Width of the mini map shown in the corner of the player's screen
    cornerWidthKm: corner_width_km,
  };
}

// Where a latitude / longitude falls inside a box of pixels showing part of
// that map, given how much ground the box covers and what it is centred on.
// Shared by the player's map view and the admin's per-shot thumbnail: both
// draw the same georeferenced image and differ only in those two things.
// Pixel coordinates are measured from the bottom left of the box, matching how
// the dots are positioned in CSS (`left` and `bottom`).
export function mapProjection({
  degreesLatitudePerKm,
  degreesLongitudePerKm,
  centreLat,
  centreLong,
  boxWidthKm,
  boxHeightKm,
  boxWidthPx,
  boxHeightPx,
}) {
  const coordsToKm = (lat, long) => [
    (long - centreLong) / degreesLongitudePerKm + boxWidthKm / 2,
    (lat - centreLat) / degreesLatitudePerKm + boxHeightKm / 2,
  ];

  const kmToPixels = (x_km, y_km) => [
    (x_km / boxWidthKm) * boxWidthPx,
    (y_km / boxHeightKm) * boxHeightPx,
  ];

  const coordsToPixels = (lat, long) => kmToPixels(...coordsToKm(lat, long));

  return { coordsToKm, kmToPixels, coordsToPixels };
}

// The venue can't change under a running client, so fetch it once per page
// load and share it between every map on the page.
let venuePromise = null;

function fetchVenue() {
  if (!venuePromise) {
    venuePromise = sendAPIRequest("get_venue").then(async (response) => {
      if (!response.ok) {
        venuePromise = null;
        return null;
      }
      return await response.json();
    });
  }
  return venuePromise;
}

// Null until the venue has loaded (or if it failed to).
export function useVenue() {
  const [venue, setVenue] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchVenue().then((v) => {
      if (!cancelled) setVenue(v);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return venue;
}
