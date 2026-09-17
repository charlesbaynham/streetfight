import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

import { sendAPIRequest } from "./utils";
import { mapGeometry, mapProjection, useVenue } from "./venue";
import { fallbackTeamColour } from "./teamColours";
import prose from "./prose";

import styles from "./MapView.module.css";
import Dot from "./Dot";
import RadarLayer from "./RadarLayer";
import courierSrc from "./images/art/courier.svg";
import crateSrc from "./images/art/crate.svg";
import { deregisterListener, registerListener } from "./UpdateListener";

const MAP_POLL_TIME = 5 * 1000;

// Geolocation settings, picked from how closely the player is watching the map.
// Expanded (popped out, or the admin's full-screen map) means they're reading
// positions off it, so refresh as fast as we reasonably can. Foreground-but-
// cornered still shows our dot, so we pay for the GNSS radio but refresh less
// often. Once the app is backgrounded nobody can see the map at all, so we fall
// back to the cheap providers, tolerate stale fixes and upload rarely.
// `uploadInterval` throttles uploads to the server only - the local map dot
// still updates on every position callback in all three cases.
const EXPANDED_GEO_SETTINGS = {
  geoOptions: {
    enableHighAccuracy: true,
    maximumAge: 1 * 1000,
    timeout: 20 * 1000,
  },
  uploadInterval: 1 * 1000,
};
const FOREGROUND_GEO_SETTINGS = {
  geoOptions: {
    enableHighAccuracy: true,
    maximumAge: 5 * 1000,
    timeout: 20 * 1000,
  },
  uploadInterval: 5 * 1000,
};
const BACKGROUND_GEO_SETTINGS = {
  geoOptions: {
    enableHighAccuracy: false,
    maximumAge: 15 * 1000,
    timeout: 20 * 1000,
  },
  uploadInterval: 15 * 1000,
};

// After 5 minutes, the dots will be almost completely transparent
const TIME_UNTIL_TRANSPARENT = 5 * 60;
const MIN_ALPHA = 0.5;

// How faded a fix of this age is drawn. The admin map has always done this to
// its player dots; the courier is drawn by the same rule so that one stale
// dot on a map does not mean two different things (M4.2).
function alphaForAge(seconds) {
  return Math.max(
    1 - ((1 - MIN_ALPHA) * seconds) / TIME_UNTIL_TRANSPARENT,
    MIN_ALPHA,
  );
}

// Past this, the dot goes altogether. The courier's fixes arrive about once a
// second while they are walking, so a minute of silence is somebody who has
// stopped broadcasting, lost signal or gone indoors - and a plausible-looking
// aeroplane sitting where somebody used to be is worse than no aeroplane.
const COURIER_STALE_AFTER_S = 60;

// How often the courier's fade is recomputed. Nothing arrives from the server
// between fixes, so without a tick of its own the dot would freeze at whatever
// age it had when the last "circle" event landed.
const COURIER_FADE_TICK_MS = 5 * 1000;

// `accuracy` is the browser's own radius-in-metres estimate for the fix. It is
// recorded but not yet used by anything: it is how good each fix was, which
// cannot be recovered after the game (docs/roadmap.md R5a).
function sendLocationUpdate(lat, long, accuracy = null) {
  const params = { latitude: lat, longitude: long };
  if (typeof accuracy === "number" && !Number.isNaN(accuracy)) {
    params.accuracy = accuracy;
  }
  sendAPIRequest("set_location", params, "POST", null);
}

// Draw the exclusion zone and next target zone on the map, if they exist. This
// component is responsible for calculating the position of the circles and also
// for querying them from the server. It uses an UpdateListener to listen for
// "circle" events and change the drawn circles appropriately.
function MapCirclesFromAPI({ calculators }) {
  const CIRCLE_UPDATE_TYPE = "circle";

  const [circlesData, setCirclesData] = useState(null);

  const getCircles = useCallback(async () => {
    const response = await sendAPIRequest("get_circles");
    if (!response.ok) return;
    const circles = await response.json();
    setCirclesData(circles);
  }, []);

  useEffect(() => {
    // On mount, register a listener for circle updates and run one update
    console.log("Registering circle update listener");

    const handle = registerListener(CIRCLE_UPDATE_TYPE, () => {
      getCircles();
    });

    console.log("Initial circle update");
    getCircles();

    return () => {
      // On unmount, deregister the listener
      console.log("Deregistering circle update listener");
      deregisterListener(CIRCLE_UPDATE_TYPE, handle);
    };
  }, [getCircles]);

  return <MapCirclesFromData calculators={calculators} circles={circlesData} />;
}

// The nine flat circle fields the server uses (whether they come from
// /get_circles or off a GameModel) turned into the three triplets MapCircles
// draws. One place, so both callers agree on the field names.
function circleTriplet(circles, name) {
  if (!circles) return null;
  return [
    circles[`${name}_circle_lat`],
    circles[`${name}_circle_long`],
    circles[`${name}_circle_radius`],
  ];
}

// Where the courier is, out of either shape the server sends it in: nested
// under `courier` from /get_circles, or flat as courier_lat / courier_long /
// courier_timestamp off a GameModel, which is what the spectator screen
// passes. Same reason circleTriplet exists - one place that knows the field
// names, so the two callers cannot drift apart. Null when nobody is walking.
function courierPosition(circles) {
  if (!circles) return null;
  const nested = circles.courier;
  const lat = nested ? nested.lat : circles.courier_lat;
  const long = nested ? nested.long : circles.courier_long;
  if (typeof lat !== "number" || typeof long !== "number") return null;
  return {
    lat,
    long,
    timestamp: nested ? nested.timestamp : circles.courier_timestamp,
  };
}

// The courier's crates (M4.3), as the triplets MapCircles draws. They arrive
// under the same key in both shapes the server sends - nested in /get_circles
// and on a GameModel - so unlike the circles there is nothing to reconcile,
// only a server too old to send them at all to defend against.
function dropTriplets(circles) {
  if (!circles || !Array.isArray(circles.drops)) return [];
  return circles.drops.map((drop) => [drop.lat, drop.long, drop.radius]);
}

export function MapCirclesFromData({ calculators, circles }) {
  return (
    <MapCircles
      calculators={calculators}
      exclusionCircle={circleTriplet(circles, "exclusion")}
      nextCircle={circleTriplet(circles, "next")}
      dropCircle={circleTriplet(circles, "drop")}
      drops={dropTriplets(circles)}
      courier={courierPosition(circles)}
    />
  );
}

// The courier's aeroplane, faded by how old its fix is and gone once that fix
// is too old to believe. Its own component so that the tick which keeps the
// fade moving re-renders the dot and not the whole circle layer.
function CourierDot({ courier, styleFor }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const handle = setInterval(() => setNow(Date.now()), COURIER_FADE_TICK_MS);
    return () => clearInterval(handle);
  }, []);

  // A fix with no timestamp is drawn at full strength rather than hidden: it
  // is a courier who is definitely somewhere, on a server too old to say when.
  const age =
    typeof courier.timestamp === "number" ? 1e-3 * now - courier.timestamp : 0;
  if (age > COURIER_STALE_AFTER_S) return null;

  // Hidden rather than dropped when the projection has nothing to say yet (a
  // box that has not been measured gives NaN), matching what the circles do
  // with the same problem.
  const placed = styleFor(courier.lat, courier.long);
  const hidden = placed.display === "none";

  return (
    <Dot
      x={placed.left}
      y={placed.bottom}
      src={courierSrc}
      alpha={alphaForAge(age)}
      className={
        hidden
          ? `${styles.mapDotCourier} ${styles.hiddenOverlay}`
          : styles.mapDotCourier
      }
      tooltip="The courier"
      testId="map-courier-dot"
    />
  );
}

// This component is responsible for drawing the circles on the map. It just
// draws - querying the circles' position is out of scope.
//
// The courier and the crate are drawn here too, despite being dots rather
// than circles (M4.2). They arrive on the circles' own payload and refresh on
// the circles' own SSE event, and this is the layer that already holds the
// coordinate calculators - so drawing them anywhere else would mean a second
// copy of all three, and MapViewSelf, MapViewAdmin and the spectator screen
// get them here for nothing.
function MapCircles({
  calculators,
  exclusionCircle = null,
  nextCircle = null,
  dropCircle = null,
  drops = [],
  courier = null,
}) {
  const calculateCircleStyles = useCallback(
    (lat, long, radiusKM) => {
      const { coordsToKm, kmToPixels } = calculators;

      const [x_km, y_km] = coordsToKm(lat, long);
      const [x_px, y_px] = kmToPixels(x_km, y_km);
      const radius_px = kmToPixels(radiusKM, 0)[0];

      // if any of the values are nan, don't render the circle
      if (isNaN(x_px) || isNaN(y_px) || isNaN(radius_px)) {
        return { display: "none" };
      }

      return {
        left: x_px - radius_px,
        bottom: y_px - radius_px,
        width: radius_px * 2,
        height: radius_px * 2,
      };
    },
    [calculators],
  );

  // A point on the map rather than a circle round one: the crate sits at the
  // drop's centre, and the courier wherever they last reported from.
  const calculateCentreStyles = useCallback(
    (lat, long) => {
      const [x_px, y_px] = calculators.coordsToPixels(lat, long);
      if (isNaN(x_px) || isNaN(y_px)) return { display: "none" };
      return { left: x_px, bottom: y_px };
    },
    [calculators],
  );

  const circles = [];

  if (exclusionCircle) {
    const [lat, long, radiusKM] = exclusionCircle;
    if (lat && long && radiusKM)
      circles.push(
        <div
          className={styles.exclusionCircle}
          style={calculateCircleStyles(lat, long, radiusKM)}
        />,
      );
  }

  if (nextCircle) {
    const [lat, long, radiusKM] = nextCircle;
    if (lat && long && radiusKM)
      circles.push(
        <div
          className={styles.nextCircle}
          style={calculateCircleStyles(lat, long, radiusKM)}
        />,
      );
  }

  // The admin's own map-placed drop, then every crate the courier has put
  // out, oldest first (M4.3). Which of the two put a crate somewhere is
  // nobody's business but the admin's, so they are drawn the same way - but
  // only the newest gets the blue ping. The ping means "this is the one that
  // has just landed, go"; leaving one on every crate would have the map
  // shouting about a drop that has been sitting there for half an hour, and
  // three of them shouting at once. The crates left behind keep their icon
  // until somebody marks them collected, because they are still there.
  const allDrops = [];
  if (dropCircle) {
    const [lat, long, radiusKM] = dropCircle;
    if (lat && long && radiusKM) allDrops.push([lat, long, radiusKM]);
  }
  allDrops.push(...drops.filter(([lat, long, r]) => lat && long && r));

  allDrops.forEach(([lat, long, radiusKM], index) => {
    if (index === allDrops.length - 1) {
      circles.push(
        <div
          className={styles.dropCircle}
          style={calculateCircleStyles(lat, long, radiusKM)}
          data-testid="map-drop-ping"
        />,
      );
    }
    // A sibling of the ping, never a child of it: .dropCircle carries the
    // `zoom` keyframe that scales it to 5x and fades it out, which would
    // take the crate with it. The ping says "look here"; the crate says
    // what is here, and has to stay legible while the ping does its thing -
    // and outlive it, on every drop but the newest.
    circles.push(
      <img
        src={crateSrc}
        alt=""
        className={styles.dropCrate}
        style={calculateCentreStyles(lat, long)}
        data-testid="map-drop-crate"
      />,
    );
  });

  return (
    <div className={styles.mapCirclesContainer}>
      {circles.map((circle, index) =>
        React.cloneElement(circle, { key: index }),
      )}
      {courier ? (
        <CourierDot courier={courier} styleFor={calculateCentreStyles} />
      ) : null}
    </div>
  );
}

// The map, once we know which venue we're playing at. Split out from MapView
// so that all of this can assume it has a geometry to draw against. Exported
// for tests only - MapView is the one thing anything outside this file
// should ever mount.
export function VenueMapView({
  geometry,
  ownPosition = null,
  other_positions_and_details = [],
  alwaysExpanded = false,
  onExpandedChange = null,
  circles = undefined,
  fillContainer = false,
}) {
  const {
    mapSrc,
    bottomLeft,
    topRight,
    degreesLongitudePerKm,
    degreesLatitudePerKm,
    widthKm: MAP_WIDTH_KM,
    heightKm: MAP_HEIGHT_KM,
    cornerWidthKm: CORNER_BOX_WIDTH_KM,
  } = geometry;

  const [poppedOut, setPoppedOut] = useState(false);
  const expanded = alwaysExpanded || poppedOut;

  // Let the parent know when the map opens / closes, so it can decide how hard
  // to work for a position fix. Pass a stable callback (e.g. a setState).
  useEffect(() => {
    if (onExpandedChange) onExpandedChange(expanded);
  }, [expanded, onExpandedChange]);

  const mapContainerRef = useRef(null);
  const [boxWidthPx, setBoxWidthPx] = useState(0);
  const [boxHeightPx, setBoxHeightPx] = useState(0);

  // Measure the width and height of the map container so that we can scale the
  // map image. Tolerate resizes / screen rotations.
  const handleResize = useCallback(() => {
    if (mapContainerRef.current) {
      setBoxWidthPx(mapContainerRef.current.clientWidth);
      setBoxHeightPx(mapContainerRef.current.clientHeight);
    }
  }, [mapContainerRef]);

  useEffect(() => {
    window.addEventListener("resize", handleResize);

    // Initial measurement
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [mapContainerRef, poppedOut, handleResize]);

  // Calculate map size based on box size
  const box_aspect_ratio = boxWidthPx / boxHeightPx;
  const box_width_km = expanded
    ? Math.max(MAP_WIDTH_KM, MAP_HEIGHT_KM * box_aspect_ratio)
    : CORNER_BOX_WIDTH_KM;
  const box_height_km = box_width_km / box_aspect_ratio;
  const map_size_x = (MAP_WIDTH_KM * boxWidthPx) / box_width_km;
  const map_size_y = (MAP_HEIGHT_KM * boxHeightPx) / box_height_km;

  // For the map position, we need to know where its centre should be. This will
  // change every time we move, so hold it in a ref to prevent rerendering
  const mapCentreLatRef = useRef((bottomLeft.lat + topRight.lat) / 2);
  const mapCentreLongRef = useRef((bottomLeft.long + topRight.long) / 2);

  // Built afresh on every call rather than memoised: the map centre lives in
  // refs that move with the player, and a memo would freeze it at whatever it
  // was when the box was last resized.
  const projection = useCallback(
    () =>
      mapProjection({
        degreesLatitudePerKm,
        degreesLongitudePerKm,
        centreLat: mapCentreLatRef.current,
        centreLong: mapCentreLongRef.current,
        boxWidthKm: box_width_km,
        boxHeightKm: box_height_km,
        boxWidthPx,
        boxHeightPx,
      }),
    [
      box_height_km,
      box_width_km,
      boxHeightPx,
      boxWidthPx,
      degreesLatitudePerKm,
      degreesLongitudePerKm,
    ],
  );

  const coordsToKm = useCallback(
    (lat, long) => projection().coordsToKm(lat, long),
    [projection],
  );

  const kmToPixels = useCallback(
    (x_km, y_km) => projection().kmToPixels(x_km, y_km),
    [projection],
  );

  const coordsToPixels = useCallback(
    (lat, long) => projection().coordsToPixels(lat, long),
    [projection],
  );

  const [mapData, setMapData] = useState({
    map_x0: 0,
    map_y0: 0,
    dot_x: 0,
    dot_y: 0,
    otherDots: [],
  });

  const otherPositionsAndDetailsString = JSON.stringify(
    other_positions_and_details,
  );

  // Calculate the centre of the box, using our own position if provided
  const recalculateMapCentre = useCallback(() => {
    var box_centre_lat, box_centre_long;
    if (!expanded && ownPosition) {
      box_centre_lat = ownPosition.coords.latitude;
      box_centre_long = ownPosition.coords.longitude;
    } else {
      box_centre_lat = (bottomLeft.lat + topRight.lat) / 2;
      box_centre_long = (bottomLeft.long + topRight.long) / 2;
    }
    mapCentreLatRef.current = box_centre_lat;
    mapCentreLongRef.current = box_centre_long;
  }, [expanded, ownPosition, bottomLeft, topRight]);

  // Recalculate things that move when things move. Except circles: those
  // calculate themselves, like these things ought to.
  useEffect(() => {
    // Nothing has a position until the box has been measured: every pixel
    // below is a fraction of its size, so they'd all come out NaN
    if (!boxWidthPx || !boxHeightPx) return;

    // Update the map coordinate functions
    recalculateMapCentre();

    // Calculate map position based on box position
    const [map_x0, map_y0] = coordsToPixels(bottomLeft.lat, bottomLeft.long);

    // Calculate our own dot
    const [dot_x, dot_y] = ownPosition
      ? coordsToPixels(
          ownPosition.coords.latitude,
          ownPosition.coords.longitude,
        )
      : [0, 0];

    // Calculate all the other dots
    const otherDots = other_positions_and_details.map(
      ({ position, color, tooltip }, index) => {
        const [x, y] = coordsToPixels(
          position.coords.latitude,
          position.coords.longitude,
        );
        const alpha = alphaForAge(1e-3 * Date.now() - position.timestamp);
        return (
          <Dot
            key={index}
            x={x}
            y={y}
            color={color}
            alpha={alpha}
            tooltip={tooltip}
          />
        );
      },
    );

    setMapData({
      map_x0,
      map_y0,
      dot_x,
      dot_y,
      otherDots,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    expanded,
    recalculateMapCentre,
    boxWidthPx,
    boxHeightPx,
    ownPosition,
    otherPositionsAndDetailsString,
    coordsToPixels,
    setMapData,
  ]);

  const { map_x0, map_y0, dot_x, dot_y, otherDots } = mapData;

  const containerClasses = [styles.mapContainer];
  if (fillContainer) containerClasses.push(styles.mapContainerFill);
  else if (alwaysExpanded) containerClasses.push(styles.mapContainerExpanded);
  else if (poppedOut) containerClasses.push(styles.mapContainerPoppedOut);
  else containerClasses.push(styles.mapContainerCorner);

  return (
    // This wrapper allows you to zoom / scale the whole of its contents.
    // "pixels" in the map coordinates therefore refer to unscaled pixels.: the
    // map is not aware of scaling, it's done purely in CSS
    <TransformWrapper
      disabled={!poppedOut && !expanded} // Disable zoom / pan if the map is in the corner
    >
      {
        // This interface allows you to request functions related to the scaling,
        // e.g. imperative methods like "resetTransform". There are plenty more
        // available:
        ({ resetTransform }) => (
          // Outer container for the map. Could probably be merged with the
          // TransformComponent
          <div className={containerClasses.join(" ")} ref={mapContainerRef}>
            <TransformComponent
              wrapperStyle={{ height: "100%", width: "100%" }}
              contentStyle={{ height: "100%", width: "100%" }}
            >
              {/* The map itself. Implemented as a div with a background image: the div fills
              the displayed box, the background is resized appropriately */}
              <div
                className={styles.mapImage}
                src={mapSrc}
                alt={prose.mapView.mapAlt}
                style={{
                  backgroundImage: `url(${mapSrc})`,
                  backgroundPosition: `left ${map_x0}px bottom ${map_y0}px`,
                  backgroundRepeat: "no-repeat",
                  backgroundSize: map_size_x + "px " + map_size_y + "px",
                }}
              />

              {/* Dots */}
              {ownPosition !== null ? <Dot x={dot_x} y={dot_y} /> : null}
              {otherDots}

              {/* Circles. Note how the coordinate calculators are passed down
              to the circles so they can handle their own positioning. It would
              be better to do this for other elements too.

              Given a `circles` prop we draw those and never call the API:
              /get_circles resolves the game from the caller's own player
              session, so a browser that never joined a game (a screen wired to
              a TV) gets null from it and would draw nothing. */}
              {circles === undefined ? (
                <MapCirclesFromAPI
                  calculators={{ coordsToKm, coordsToPixels, kmToPixels }}
                />
              ) : (
                <MapCirclesFromData
                  calculators={{ coordsToKm, coordsToPixels, kmToPixels }}
                  circles={circles}
                />
              )}

              {/* Radar contacts (M6.1). Draws nothing, and polls for nothing,
              unless the player is holding a live radar card - so the admin
              map and the spectator screen, which mount this same view, are
              unaffected. */}
              <RadarLayer calculators={{ coordsToPixels }} />

              {/* A box that intercepts clicks - transparent and at the top z-order.
              Only wired for the unexpanded corner map (tap to pop out): once
              popped out this sits inside the zoomable TransformComponent, so
              leaving it wired to "any tap toggles" made a pinch-zoom gesture's
              own closing tap collapse the map straight back to its corner and
              reset the zoom on the same gesture. Closing a popped-out map goes
              through the explicit close button below instead. */}
              <div
                className={styles.clickCatcher}
                data-testid="map-click-catcher"
                onClick={
                  alwaysExpanded || poppedOut
                    ? null
                    : () => {
                        setPoppedOut(true);
                        resetTransform();
                        handleResize();
                      }
                }
              />
            </TransformComponent>
            {poppedOut && !alwaysExpanded ? (
              <button
                type="button"
                className={styles.closeButton}
                aria-label={prose.mapView.closeMapLabel}
                onClick={() => {
                  setPoppedOut(false);
                  resetTransform();
                  handleResize();
                }}
              >
                {prose.mapView.closeMapSymbol}
              </button>
            ) : null}
          </div>
        )
      }
    </TransformWrapper>
  );
}

// Wait for the server to tell us where we're playing before drawing anything -
// until then there's no map image and no idea what the ground coordinates of
// the box are. Holds the container's shape so the layout doesn't jump.
function MapView(props) {
  const venue = useVenue();
  const geometry = useMemo(() => (venue ? mapGeometry(venue) : null), [venue]);

  if (!geometry) {
    const containerClasses = [
      styles.mapContainer,
      props.fillContainer
        ? styles.mapContainerFill
        : props.alwaysExpanded
          ? styles.mapContainerExpanded
          : styles.mapContainerCorner,
    ];
    return <div className={containerClasses.join(" ")} />;
  }

  return <VenueMapView geometry={geometry} {...props} />;
}

export function MapViewSelf() {
  const [position, setPosition] = useState(null);

  // Track the last upload time per-mount so it resets correctly if the
  // component remounts. Deliberately outside the watch effect below, so
  // re-registering the watch on a visibility change doesn't reset the throttle.
  const lastUpdateTime = useRef(0);

  // Is the app in the foreground? The map is always on screen while playing (in
  // the corner if not popped out), so app visibility is what decides whether
  // anyone can actually see our dot.
  const [isVisible, setIsVisible] = useState(!document.hidden);

  // Has the player popped the map out to look at it properly?
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    const handleVisibilityChange = () => setIsVisible(!document.hidden);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, []);

  useEffect(() => {
    if (navigator.geolocation) {
      // The accuracy / battery tradeoff depends on how closely the player is
      // watching. Backgrounded wins over expanded: a popped-out map that's
      // offscreen still isn't being read. An existing watch can't be
      // reconfigured, so this effect re-registers it whenever the tier changes.
      let settings;
      if (!isVisible) settings = BACKGROUND_GEO_SETTINGS;
      else if (isExpanded) settings = EXPANDED_GEO_SETTINGS;
      else settings = FOREGROUND_GEO_SETTINGS;
      const { geoOptions, uploadInterval } = settings;

      // Register a callback for changes to the user's position.
      // This a) updates the location on the map (every callback, so our own
      // dot stays smooth) and b) throttles uploads to the server to save
      // battery and network.
      const watchId = navigator.geolocation.watchPosition(
        (position) => {
          setPosition(position);

          const currentTime = Date.now();
          if (currentTime - lastUpdateTime.current >= uploadInterval) {
            sendLocationUpdate(
              position.coords.latitude,
              position.coords.longitude,
              position.coords.accuracy,
            );
            lastUpdateTime.current = currentTime;
          }
        },

        (error) => {
          console.error("Error watching position:", error);
        },

        geoOptions,
      );

      return () => {
        // Clean up the watch when this component is unmounted, or before
        // re-registering it with different settings.
        navigator.geolocation.clearWatch(watchId);
      };
    } else {
      console.error("Geolocation is not supported by this browser.");
    }
  }, [isVisible, isExpanded]);

  return <MapView ownPosition={position} onExpandedChange={setIsExpanded} />;
}

export function MapViewAdmin({
  gameId = null,
  colourForTeam = null,
  circles = undefined,
  fillContainer = false,
}) {
  const [locationWithDetails, setLocationWithDetails] = useState([]);

  const updateLocations = useCallback(() => {
    // Passed explicitly where we know it: with no game_id the backend picks
    // whichever game the database returns first, which is arbitrary.
    const params = gameId ? { game_id: gameId } : {};
    sendAPIRequest("admin_get_locations", params).then(async (response) => {
      if (!response.ok) return;
      const locations = await response.json();

      const unique_team_ids = [
        ...new Set(locations.map((user) => user.team_id)),
      ];
      const fallbackColors = {};
      unique_team_ids.forEach((team_id, index) => {
        fallbackColors[team_id] = fallbackTeamColour(index);
      });

      const locs = locations
        // A player who has never reported a fix has no position to draw. The
        // dots have no NaN guard of their own, unlike the circles.
        .filter(
          (user) =>
            typeof user.latitude === "number" &&
            typeof user.longitude === "number",
        )
        .map((user) => ({
          position: {
            timestamp: user.timestamp,
            coords: { latitude: user.latitude, longitude: user.longitude },
          },
          color:
            user.state === "alive"
              ? (colourForTeam && colourForTeam(user.team_id)) ||
                fallbackColors[user.team_id]
              : "gray",
          tooltip: `${user.user} - ${user.team}`,
        }));
      setLocationWithDetails(locs);
    });
  }, [gameId, colourForTeam]);

  useEffect(() => {
    const handle = setInterval(updateLocations, MAP_POLL_TIME);
    updateLocations();
    return () => {
      clearInterval(handle);
    };
  }, [updateLocations]);

  return (
    <MapView
      other_positions_and_details={locationWithDetails}
      alwaysExpanded={true}
      circles={circles}
      fillContainer={fillContainer}
    />
  );
}
