import { mapGeometry, mapProjection } from "./venue";

// The georeferencing maths, checked against a map whose corners are known
// exactly: a 100 x 200 px image whose top left and bottom right pixels are the
// reference points. Coordinates are the resort's, so the km-per-degree
// conversions are exercised at a real latitude.
const venue = {
  name: "Test venue",
  map: {
    image: "koyao_resort",
    width_px: 100,
    height_px: 200,
    ref_1: { x: 0, y: 0, lat: 8.12, long: 98.62 },
    ref_2: { x: 100, y: 200, lat: 8.11, long: 98.63 },
    corner_width_km: 0.08,
  },
  landmarks: { MIDDLE: [8.115, 98.625] },
};

describe("mapGeometry", () => {
  it("puts the map corners at the reference points", () => {
    const { bottomLeft, topRight } = mapGeometry(venue);

    expect(bottomLeft.lat).toBeCloseTo(8.11, 10);
    expect(bottomLeft.long).toBeCloseTo(98.62, 10);
    expect(topRight.lat).toBeCloseTo(8.12, 10);
    expect(topRight.long).toBeCloseTo(98.63, 10);
  });

  it("scales longitude by the latitude the venue is at", () => {
    const { widthKm, heightKm } = mapGeometry(venue);

    // 0.01 degrees of latitude, and 0.01 degrees of longitude shrunk by
    // cos(8.115 degrees)
    expect(heightKm).toBeCloseTo(1.10574, 4);
    expect(widthKm).toBeCloseTo(1.1132 * Math.cos((8.115 * Math.PI) / 180), 4);
  });

  it("resolves the map image from the key the server sends", () => {
    expect(mapGeometry(venue).mapSrc).toBeTruthy();
    expect(
      mapGeometry({ ...venue, map: { ...venue.map, image: "nope" } }).mapSrc,
    ).toBeUndefined();
  });

  // The reference points don't have to be the corners: the hand-drawn Kingston
  // map's are two landmarks in the middle of it.
  it("extrapolates from reference points inside the image", () => {
    const inset = {
      ...venue,
      map: {
        ...venue.map,
        ref_1: { x: 25, y: 50, lat: 8.1175, long: 98.6225 },
        ref_2: { x: 75, y: 150, lat: 8.1125, long: 98.6275 },
      },
    };
    const { bottomLeft, topRight } = mapGeometry(inset);

    expect(bottomLeft.lat).toBeCloseTo(8.11, 10);
    expect(bottomLeft.long).toBeCloseTo(98.62, 10);
    expect(topRight.lat).toBeCloseTo(8.12, 10);
    expect(topRight.long).toBeCloseTo(98.63, 10);
  });
});

describe("mapProjection", () => {
  // A box 1 km across and 200 px across, so a metre is a fifth of a pixel and
  // the arithmetic is checkable by eye.
  const projection = () =>
    mapProjection({
      degreesLatitudePerKm: 1 / 110.574,
      degreesLongitudePerKm: 1 / 100,
      centreLat: 51.5,
      centreLong: -0.1,
      boxWidthKm: 1,
      boxHeightKm: 1,
      boxWidthPx: 200,
      boxHeightPx: 200,
    });

  it("puts whatever it is centred on in the middle of the box", () => {
    const [x, y] = projection().coordsToPixels(51.5, -0.1);
    expect(x).toBeCloseTo(100, 6);
    expect(y).toBeCloseTo(100, 6);
  });

  it("measures pixels up from the bottom left, like the dots do", () => {
    // 100 m north and 100 m east of the centre: 20 px each way, and north is
    // up, so y increases.
    const [x, y] = projection().coordsToPixels(
      51.5 + 0.1 / 110.574,
      -0.1 + 0.001,
    );
    expect(x).toBeCloseTo(120, 6);
    expect(y).toBeCloseTo(120, 6);
  });

  it("scales a distance in km to pixels", () => {
    const [radiusPx] = projection().kmToPixels(0.05, 0);
    expect(radiusPx).toBeCloseTo(10, 6);
  });
});
