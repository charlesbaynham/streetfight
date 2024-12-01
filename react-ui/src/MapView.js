import React, { useCallback, useEffect, useRef, useState } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

import { sendAPIRequest } from "./utils";

import mapSrc from "./images/map_lowres.png";

import styles from "./MapView.module.css";
import Dot from "./Dot";
import { deregisterListener, registerListener } from "./UpdateListener";

// Some important landmarks
const SPOONS = [51.411374997955264, -0.3007246028148721];
const THE_ALBION = [51.409136523603394, -0.29792437645324277];
const THE_FIGHTING_COCKS = [51.410615468068926, -0.2982569703905028];
const THE_BISHOP = [51.410287561454254, -0.30802021153922127];
const THE_GREY_HORSE = [51.41423566875311, -0.300628043344843];

// Based on calculations and markup in "map alignment.svg"
const ref_map_width_px = 1188.5;
const ref_map_height_px = 1233.5;
const ref_1_lat_long = [51.4076739525208, -0.30754164680355806]; // TODO put back
const ref_1_xy = [294.098, 963.464];
const ref_2_lat_long = [51.41383263398225, -0.30056843291595964]; // TODO put back
const ref_2_xy = [825.823, 212.722];

// These are fake, for testing. TODO: Undo
// const ref_1_lat_long = [51.40277852529075, -0.3123814839484815];
// const ref_2_lat_long = [51.42060545517807, -0.27796337627249573];

const long_per_width_px =
  (ref_2_lat_long[1] - ref_1_lat_long[1]) / (ref_2_xy[0] - ref_1_xy[0]);
const lat_per_height_px =
  (ref_2_lat_long[0] - ref_1_lat_long[0]) / (ref_2_xy[1] - ref_1_xy[1]);
const map_bottom_left = {
  long: ref_1_lat_long[1] - ref_1_xy[0] * long_per_width_px,
  lat:
    ref_1_lat_long[0] + (ref_map_height_px - ref_1_xy[1]) * lat_per_height_px,
};
const map_top_right = {
  long:
    ref_1_lat_long[1] + (ref_map_width_px - ref_1_xy[0]) * long_per_width_px,
  lat: ref_1_lat_long[0] - ref_1_xy[1] * lat_per_height_px,
};

const degreesLongitudePerKm =
  1 /
  (111.32 *
    Math.cos(
      ((map_bottom_left.lat + map_top_right.lat) / 2) * (Math.PI / 180)
    ));
const degreesLatitudePerKm = 1 / 110.574;

const MAP_WIDTH_KM =
  (map_top_right.long - map_bottom_left.long) / degreesLongitudePerKm;
const MAP_HEIGHT_KM =
  (map_top_right.lat - map_bottom_left.lat) / degreesLatitudePerKm;

const MAP_POLL_TIME = 5 * 1000;
const RATE_LIMIT_INTERVAL = 1 * 1000;

// After 5 minutes, the dots will be almost completely transparent
const TIME_UNTIL_TRANSPARENT = 5 * 60;
const MIN_ALPHA = 0.5;

// Width of the map in km when it's in the corner
// 10% of the map in view
const CORNER_BOX_WIDTH_KM = 0.1 * MAP_WIDTH_KM;

function sendLocationUpdate(lat, long) {
  sendAPIRequest(
    "set_location",
    {
      latitude: lat,
      longitude: long,
    },
    "POST",
    null
  );
}

// Draw the exclusion zone and next target zone on the map, if they exist. This
// component is responsible for calculating the position of the circles and also
// for querying them from the server. It uses an UpdateListener to listen for
// "circle" events and change the drawn circles appropriately.
function MapCirclesFromAPI({ calculators }) {
  const CIRCLE_UPDATE_TYPE = "circle";

  useEffect(() => {
    // On mount, register a listener for circle updates
    console.log("Registering circle update listener");
    const handle = registerListener(CIRCLE_UPDATE_TYPE, () => {
      console.log("A circle update happened");
    });

    return () => {
      // On unmount, deregister the listener
      console.log("Deregistering circle update listener");
      deregisterListener(CIRCLE_UPDATE_TYPE, handle);
    };
  }, []);

  return (
    <MapCircles
      calculators={calculators}
      exclusionCircle={[SPOONS[0], SPOONS[1], 0.7]}
      nextCircle={[THE_GREY_HORSE[0], THE_GREY_HORSE[1], 0.3]}
    />
  );
}

// This component is responsible for drawing the circles on the map. It just
// draws - querying the circles' position is out of scope
function MapCircles({
  calculators,
  exclusionCircle = null,
  nextCircle = null,
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
    [calculators]
  );

  const circles = [];

  if (exclusionCircle) {
    const [lat, long, radiusKM] = exclusionCircle;
    circles.push(
      <div
        className={styles.exclusionCircle}
        style={calculateCircleStyles(lat, long, radiusKM)}
      />
    );
  }

  if (nextCircle) {
    const [lat, long, radiusKM] = nextCircle;
    circles.push(
      <div
        className={styles.nextCircle}
        style={calculateCircleStyles(lat, long, radiusKM)}
      />
    );
  }

  return (
    <div className={styles.mapCirclesContainer}>
      {circles.map((circle, index) =>
        React.cloneElement(circle, { key: index })
      )}
    </div>
  );
}

function MapView({
  ownPosition = null,
  other_positions_and_details = [],
  alwaysExpanded = false,
}) {
  const [poppedOut, setPoppedOut] = useState(false);
  const expanded = alwaysExpanded || poppedOut;

  const mapContainerRef = useRef(null);
  const [boxWidthPx, setMapWidth] = useState(0);
  const [boxHeightPx, setMapHeight] = useState(0);

  // Measure the width and height of the map container so that we can scale the
  // map image. Tolerate resizes / screen rotations.
  const handleResize = useCallback(() => {
    if (mapContainerRef.current) {
      setMapWidth(mapContainerRef.current.clientWidth);
      setMapHeight(mapContainerRef.current.clientHeight);
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
  const mapCentreLatRef = useRef((map_bottom_left.lat + map_top_right.lat) / 2);
  const mapCentreLongRef = useRef(
    (map_bottom_left.long + map_top_right.long) / 2
  );

  const coordsToKm = useCallback(
    (lat, long) => {
      // Convert from lat / long to km from the bottom left corner
      const x_km =
        (long - mapCentreLongRef.current) / degreesLongitudePerKm +
        box_width_km / 2;
      const y_km =
        (lat - mapCentreLatRef.current) / degreesLatitudePerKm +
        box_height_km / 2;

      return [x_km, y_km];
    },
    [box_height_km, box_width_km]
  );

  const kmToPixels = useCallback(
    (x_km, y_km) => {
      // Convert from km to pixels
      const x_px = (x_km / box_width_km) * boxWidthPx;
      const y_px = (y_km / box_height_km) * boxHeightPx;

      return [x_px, y_px];
    },
    [boxWidthPx, boxHeightPx, box_height_km, box_width_km]
  );

  const coordsToPixels = useCallback(
    (lat, long) => {
      const [x_km, y_km] = coordsToKm(lat, long);
      return kmToPixels(x_km, y_km);
    },
    [coordsToKm, kmToPixels]
  );

  const [mapData, setMapData] = useState({
    map_x0: 0,
    map_y0: 0,
    dot_x: 0,
    dot_y: 0,
    otherDots: [],
  });

  const otherPositionsAndDetailsString = JSON.stringify(
    other_positions_and_details
  );

  // Calculate the centre of the box, using our own position if provided
  const recalculateMapCentre = useCallback(() => {
    var box_centre_lat, box_centre_long;
    if (!expanded && ownPosition) {
      box_centre_lat = ownPosition.coords.latitude;
      box_centre_long = ownPosition.coords.longitude;
    } else {
      box_centre_lat = (map_bottom_left.lat + map_top_right.lat) / 2;
      box_centre_long = (map_bottom_left.long + map_top_right.long) / 2;
    }
    mapCentreLatRef.current = box_centre_lat;
    mapCentreLongRef.current = box_centre_long;
  }, [expanded, ownPosition]);

  // Recalculate things that move when things move. Except circles: those
  // calculate themselves, like these things ought to.
  useEffect(() => {
    // Update the map coordinate functions
    recalculateMapCentre();

    // Calculate map position based on box position
    const [map_x0, map_y0] = coordsToPixels(
      map_bottom_left.lat,
      map_bottom_left.long
    );

    // Calculate our own dot
    const [dot_x, dot_y] = ownPosition
      ? coordsToPixels(
          ownPosition.coords.latitude,
          ownPosition.coords.longitude
        )
      : [0, 0];

    // Calculate all the other dots
    const otherDots = other_positions_and_details.map(
      ({ position, color, tooltip }, index) => {
        const [x, y] = coordsToPixels(
          position.coords.latitude,
          position.coords.longitude
        );
        const dt = 1e-3 * Date.now() - position.timestamp;
        const alpha = Math.max(
          1 - ((1 - MIN_ALPHA) * dt) / TIME_UNTIL_TRANSPARENT,
          MIN_ALPHA
        );
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
      }
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
  if (alwaysExpanded) containerClasses.push(styles.mapContainerExpanded);
  else if (poppedOut) containerClasses.push(styles.mapContainerPoppedOut);
  else containerClasses.push(styles.mapContainerCorner);

  return (
    // This wrapper allows you to zoom / scale the whole of its contents.
    // "pixels" in the map coordinates therefore refer to unscaled pixels.: the
    // map is not aware of scaling, it's done purely in CSS
    <TransformWrapper
      disabled={!poppedOut} // Disable zoom / pan if the map is in the corner
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
                alt="Map"
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

              {/* Circles */}
              <MapCirclesFromAPI
                // Note how the coordinate calculators are passed down to the
                // circles so they can handle their own positioning. It would be
                // better to do this for other elements too.
                calculators={{ coordsToKm, coordsToPixels, kmToPixels }}
              />

              {/* A box that intercepts clicks - transparent and at the top z-order */}
              <div
                className={styles.clickCatcher}
                onClick={
                  alwaysExpanded
                    ? null
                    : () => {
                        setPoppedOut(!poppedOut);
                        resetTransform();
                        handleResize();
                      }
                }
              />
            </TransformComponent>
          </div>
        )
      }
    </TransformWrapper>
  );
}

var lastUpdateTime = 0;

export function MapViewSelf() {
  const [position, setPosition] = useState(null);

  useEffect(() => {
    if (navigator.geolocation) {
      // Register a callback for changes to the user's position.
      // This a) updates the location on the map and b) sends the location to the server.
      const watchId = navigator.geolocation.watchPosition(
        (position) => {
          const currentTime = Date.now();
          if (currentTime - lastUpdateTime >= RATE_LIMIT_INTERVAL) {
            setPosition(position);
            sendLocationUpdate(
              position.coords.latitude,
              position.coords.longitude
            );
            lastUpdateTime = currentTime;
          }
        },

        (error) => {
          console.error("Error watching position:", error);
        }
      );

      return () => {
        // Clean up the watch when this component is unmounted.
        navigator.geolocation.clearWatch(watchId);
      };
    } else {
      console.error("Geolocation is not supported by this browser.");
    }
  }, []);

  return <MapView ownPosition={position} />;
}

export function MapViewAdmin() {
  const [locationWithDetails, setLocationWithDetails] = useState([]);

  const updateLocations = useCallback(() => {
    sendAPIRequest("admin_get_locations").then(async (response) => {
      if (!response.ok) return;
      const locations = await response.json();

      const team_ids = locations.map((user) => user.team_id);
      const unique_team_ids = [...new Set(team_ids)];

      // Assign a color to each unique team
      const colors = [
        "red",
        "blue",
        "green",
        "yellow",
        "purple",
        "orange",
        "pink",
        "cyan",
        "brown",
        "black",
      ];
      const teamColors = {};
      unique_team_ids.forEach((team_id, index) => {
        teamColors[team_id] = colors[index % colors.length];
      });

      // Color each location point according to the team
      const locs = locations.map((user) => ({
        position: {
          timestamp: user.timestamp,
          coords: { latitude: user.latitude, longitude: user.longitude },
        },
        color: user.state === "alive" ? teamColors[user.team_id] : "gray",
        tooltip: `${user.user} - ${user.team}`,
      }));
      setLocationWithDetails(locs);
    });
  }, []);

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
    />
  );
}
