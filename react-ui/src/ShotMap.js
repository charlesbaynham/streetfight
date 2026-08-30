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
// How many other players to draw. Everybody who was in the box is usually a
// handful; the cap is there so a crowd cannot turn the thumbnail into a smear.
const MAX_OTHERS = 8;
// A fix this much older than the photograph is drawn faded and labelled with
// its age: it says where somebody was, not where they were when the shutter
// went. The same staleness the location term discounts
// (backend/shot_identification.py, _effective_sigma_m), said in the crude way a
// thumbnail can say it.
const STALE_AFTER_S = 120;

const EARTH_RADIUS_M = 6371e3;

// Great-circle distance, matching backend/shot_identification.haversine_m.
export function haversineMetres(lat1, long1, lat2, long2) {
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((long2 - long1) * Math.PI) / 180;

  const a =
    Math.sin(dPhi / 2) * Math.sin(dPhi / 2) +
    Math.cos(phi1) *
      Math.cos(phi2) *
      Math.sin(dLambda / 2) *
      Math.sin(dLambda / 2);

  return 2 * EARTH_RADIUS_M * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// The fixes stored with a shot, or an empty list when there are none to be
// had. Entries without a position are dropped rather than defaulted, exactly
// as backend/shot_identification.parse_location_context does it.
function locationFixes(shot) {
  if (!shot || !shot.location_context) return [];

  let context;
  try {
    context = JSON.parse(shot.location_context);
  } catch (err) {
    return [];
  }
  if (!Array.isArray(context)) return [];

  return context.filter(
    (entry) =>
      entry &&
      typeof entry.latitude === "number" &&
      typeof entry.longitude === "number",
  );
}

// The shooter's own fix out of a shot's location_context, or null when there
// isn't one - a shot from before locations were recorded, or a shooter whose
// phone had never reported a position.
export function shooterFix(shot) {
  if (!shot) return null;

  return (
    locationFixes(shot).find((entry) => entry.user_id === shot.user_id) || null
  );
}

// When the photograph was taken, in epoch seconds, or null when the shot does
// not carry a time. The backend stores naive UTC and serialises it without a
// zone, which JS would otherwise read as local time - an hour of imaginary fix
// age for anybody east or west of Greenwich.
export function shotEpochSeconds(shot) {
  if (!shot || !shot.time_created) return null;

  const raw = String(shot.time_created);
  const stamped = /(Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : `${raw}Z`;
  const millis = new Date(stamped).getTime();

  return Number.isNaN(millis) ? null : millis / 1000;
}

// Everybody but the shooter who had a position when the shot was taken,
// nearest first, with how far away they were and how old their fix already was
// by then. This is the same evidence identification scores against - who else
// was actually about - shown rather than only summarised as a metres column.
export function otherFixes(shot) {
  const shooter = shooterFix(shot);
  if (!shooter) return [];

  const epoch = shotEpochSeconds(shot);

  return locationFixes(shot)
    .filter((fix) => fix.user_id !== shot.user_id)
    .map((fix) => ({
      fix,
      distance: haversineMetres(
        shooter.latitude,
        shooter.longitude,
        fix.latitude,
        fix.longitude,
      ),
      // Null rather than zero when either end of the subtraction is missing:
      // an unknown age must not read as a fresh fix.
      ageSeconds:
        epoch === null || typeof fix.timestamp !== "number"
          ? null
          : Math.max(0, epoch - fix.timestamp),
      teammate: fix.team_id === shooter.team_id,
      down: fix.state !== "alive",
    }))
    .sort((a, b) => a.distance - b.distance);
}

// What a dot is called on the map. Anything that makes the position less than
// a plain "they were here" is said in words rather than left to the styling:
// a player who is out, and a fix too old to place them by.
function otherLabel(other) {
  const caveats = [
    other.down ? other.fix.state : null,
    other.ageSeconds === null
      ? "fix age unknown"
      : other.ageSeconds > STALE_AFTER_S
        ? `${formatAge(other.ageSeconds)} old`
        : null,
  ].filter(Boolean);

  const name = other.fix.user || "unnamed";
  return caveats.length ? `${name} (${caveats.join(", ")})` : name;
}

// "43 m, fix 4 m old" - the facts behind one dot, for the title attribute.
function otherTitle(other) {
  const facts = [`${Math.round(other.distance)} m away`];
  if (other.ageSeconds === null) facts.push("fix age unknown");
  else facts.push(`fix ${formatAge(other.ageSeconds)} old`);
  if (other.down) facts.push(other.fix.state);
  return `${other.fix.user || "unnamed"} (${other.fix.team || "no team"}) - ${facts.join(", ")}`;
}

function formatAge(seconds) {
  if (seconds < 90) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
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

  // Who else was about, projected the same way and kept to what fits in the
  // box: a player 400 m away is not "in that area", and pinning them to the
  // edge would say they were when they weren't. The count says how many were
  // dropped, so the map never quietly under-reports the crowd.
  const others = otherFixes(shot);
  const inView = others
    .map((other) => ({
      ...other,
      pixels: coordsToPixels(other.fix.latitude, other.fix.longitude),
    }))
    .filter(
      ({ pixels: [x, y] }) => x >= 0 && x <= BOX_PX && y >= 0 && y <= BOX_PX,
    );
  const drawn = inView.slice(0, MAX_OTHERS);

  const caption = [
    accuracy === null ? "accuracy unknown" : `±${Math.round(accuracy)} m`,
    heading === null
      ? "no heading"
      : `facing ${String(Math.round(heading)).padStart(3, "0")}°`,
  ].join(" · ");

  const crowdCaption = [
    inView.length === 0
      ? "nobody else in view"
      : `${inView.length} other${inView.length === 1 ? "" : "s"} in view`,
    drawn.length < inView.length ? `nearest ${MAX_OTHERS} drawn` : null,
    others.length > inView.length
      ? `${others.length - inView.length} off the map`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

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

        {/* Furthest first, so the nearest dots - the ones the adjudication
            turns on - are painted over the top rather than under. */}
        {[...drawn].reverse().map((other) => (
          <div
            key={other.fix.user_id}
            className={[
              styles.other,
              // A name hung off a dot in the right-hand half would run out of
              // the box and be cut in half, so it goes on the inside.
              other.pixels[0] > BOX_PX / 2 ? styles.otherFlipped : null,
              other.teammate ? styles.otherTeammate : null,
              other.down ? styles.otherDown : null,
              other.ageSeconds === null || other.ageSeconds > STALE_AFTER_S
                ? styles.otherStale
                : null,
            ]
              .filter(Boolean)
              .join(" ")}
            style={
              other.pixels[0] > BOX_PX / 2
                ? {
                    right: BOX_PX - other.pixels[0],
                    bottom: other.pixels[1],
                  }
                : { left: other.pixels[0], bottom: other.pixels[1] }
            }
            title={otherTitle(other)}
          >
            <span className={styles.otherDot} />
            <span className={styles.otherName}>{otherLabel(other)}</span>
          </div>
        ))}

        <div className={styles.dot} style={{ left: dotX, bottom: dotY }} />
      </div>
      <p className={styles.caption}>{caption}</p>
      <p className={styles.caption}>
        {crowdCaption}
        {drawn.some((other) => other.teammate)
          ? " · hollow dots are the shooter's own team"
          : null}
      </p>
    </>
  );
}
