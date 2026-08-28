import { useMemo } from "react";

import { mapGeometry, mapProjection, useVenue } from "./venue";

import styles from "./ShotMap.module.css";

// Where the shooter was standing and which way they were pointing, drawn on
// the venue's own map. A thumbnail beside the photo in the admin queue, not
// the interactive three-mode map: fixed size, fixed span, no panning.
const BOX_PX = 220;
// How much ground the box covers, edge to edge.
const SPAN_KM = 0.2;
// The heading indicator is a cone rather than an arrow: the compass is not
// that good, and neither is the way a phone is held.
const CONE_HALF_ANGLE_DEG = 22;
const CONE_LENGTH_PX = 0.38 * BOX_PX;

// The shooter's own fix out of a shot's location_context, or null when there
// isn't one - a shot from before locations were recorded, or a shooter whose
// phone had never reported a position.
export function shooterFix(shot) {
  if (!shot || !shot.location_context) return null;

  let context;
  try {
    context = JSON.parse(shot.location_context);
  } catch (err) {
    return null;
  }
  if (!Array.isArray(context)) return null;

  const fix = context.find((entry) => entry && entry.user_id === shot.user_id);
  if (!fix) return null;
  if (typeof fix.latitude !== "number" || typeof fix.longitude !== "number")
    return null;

  return fix;
}

// A wedge centred on (cx, cy) - SVG coordinates, so y grows downwards -
// pointing `heading` degrees clockwise from north.
function conePath(cx, cy, heading) {
  const edge = (degrees) => {
    const radians = (degrees * Math.PI) / 180;
    return [
      cx + CONE_LENGTH_PX * Math.sin(radians),
      cy - CONE_LENGTH_PX * Math.cos(radians),
    ];
  };

  const [x1, y1] = edge(heading - CONE_HALF_ANGLE_DEG);
  const [x2, y2] = edge(heading + CONE_HALF_ANGLE_DEG);

  return [
    `M ${cx} ${cy}`,
    `L ${x1} ${y1}`,
    `A ${CONE_LENGTH_PX} ${CONE_LENGTH_PX} 0 0 1 ${x2} ${y2}`,
    "Z",
  ].join(" ");
}

export default function ShotMap({ shot }) {
  const venue = useVenue();
  const geometry = useMemo(() => (venue ? mapGeometry(venue) : null), [venue]);

  const fix = shooterFix(shot);
  const heading =
    shot && typeof shot.heading === "number" && !Number.isNaN(shot.heading)
      ? shot.heading
      : null;

  // Old and test shots have neither, and that is not an error worth shouting
  // about - say so quietly and let the admin get on with the photo.
  if (!fix) {
    return <p className={styles.noFix}>No position recorded for this shot</p>;
  }
  if (!geometry) return null;

  const { coordsToPixels, kmToPixels } = mapProjection({
    degreesLatitudePerKm: geometry.degreesLatitudePerKm,
    degreesLongitudePerKm: geometry.degreesLongitudePerKm,
    centreLat: fix.latitude,
    centreLong: fix.longitude,
    boxWidthKm: SPAN_KM,
    boxHeightKm: SPAN_KM,
    boxWidthPx: BOX_PX,
    boxHeightPx: BOX_PX,
  });

  // The map image is placed by its bottom left corner, exactly as MapView
  // does it, and scaled so that SPAN_KM fills the box.
  const [mapX0, mapY0] = coordsToPixels(
    geometry.bottomLeft.lat,
    geometry.bottomLeft.long,
  );
  const mapSizeX = (geometry.widthKm * BOX_PX) / SPAN_KM;
  const mapSizeY = (geometry.heightKm * BOX_PX) / SPAN_KM;

  // The shooter is the centre of the box by construction, but go through the
  // projection anyway rather than hard-coding the middle.
  const [dotX, dotY] = coordsToPixels(fix.latitude, fix.longitude);

  const accuracy =
    typeof fix.accuracy === "number" && !Number.isNaN(fix.accuracy)
      ? fix.accuracy
      : null;
  const accuracyRadiusPx =
    accuracy === null ? null : kmToPixels(accuracy / 1000, 0)[0];

  const caption = [
    accuracy === null ? "accuracy unknown" : `±${Math.round(accuracy)} m`,
    heading === null
      ? "no heading"
      : `facing ${String(Math.round(heading)).padStart(3, "0")}°`,
  ].join(" · ");

  return (
    <>
      <div
        className={styles.shotMap}
        style={{ width: BOX_PX, height: BOX_PX }}
        data-testid="shot-map"
      >
        <div
          className={styles.mapImage}
          style={{
            backgroundImage: `url(${geometry.mapSrc})`,
            backgroundPosition: `left ${mapX0}px bottom ${mapY0}px`,
            backgroundSize: `${mapSizeX}px ${mapSizeY}px`,
          }}
        />

        {accuracyRadiusPx ? (
          <div
            className={styles.accuracyCircle}
            style={{
              left: dotX - accuracyRadiusPx,
              bottom: dotY - accuracyRadiusPx,
              width: accuracyRadiusPx * 2,
              height: accuracyRadiusPx * 2,
            }}
          />
        ) : null}

        {heading === null ? null : (
          <svg
            className={styles.cone}
            viewBox={`0 0 ${BOX_PX} ${BOX_PX}`}
            aria-label={`Facing ${Math.round(heading)} degrees`}
          >
            <path
              className={styles.conePath}
              d={conePath(dotX, BOX_PX - dotY, heading)}
            />
          </svg>
        )}

        <div className={styles.dot} style={{ left: dotX, bottom: dotY }} />
      </div>
      <p className={styles.caption}>{caption}</p>
    </>
  );
}
