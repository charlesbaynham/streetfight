import React, { useCallback, useEffect, useRef, useState } from "react";

import { sendAPIRequest } from "./utils";

import mapSrc from "./images/mapsample.png";

import styles from "./MapView.module.css";
import Dot from "./Dot";

// Top squiggly road tip to the star
const map_bottom_left = {
  long: -2.741752117059972,
  lat: 51.79127318746444,
};

const map_top_right = {
  long: -2.734091728069985,
  lat: 51.794378768913234,
};

const degreesLongitudePerKm =
  1 /
  (111.32 *
    Math.cos(
      ((map_bottom_left.lat + map_top_right.lat) / 2) * (Math.PI / 180),
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
const CORNER_BOX_WIDTH_KM = 0.1;

function sendLocationUpdate(lat, long) {
  sendAPIRequest(
    "set_location",
    {
      latitude: lat,
      longitude: long,
    },
    "POST",
    null,
  );
}

function MapView({
  grayedOut = false,
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
  const box_width_km = expanded ? (Math.max(MAP_WIDTH_KM, MAP_HEIGHT_KM * box_aspect_ratio)) : CORNER_BOX_WIDTH_KM;
  const box_height_km = box_width_km / box_aspect_ratio;
  const map_size_x = (MAP_WIDTH_KM * boxWidthPx) / box_width_km;
  const map_size_y = (MAP_HEIGHT_KM * boxHeightPx) / box_height_km;

  const coordsToPixels = useCallback(
    (lat, long, map_centre_lat, map_centre_long) => {
      // Convert from lat / long to km from the bottom left corner
      const x_km =
        (long - map_centre_long) / degreesLongitudePerKm + box_width_km / 2;
      const y_km =
        (lat - map_centre_lat) / degreesLatitudePerKm + box_height_km / 2;

      // Convert from km to pixels
      const x_px = (x_km / box_width_km) * boxWidthPx;
      const y_px = (y_km / box_height_km) * boxHeightPx;

      return [x_px, y_px];
    },
    [boxWidthPx, boxHeightPx, box_height_km, box_width_km],
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

  useEffect(() => {
    // Calculate the centre of the box, using our own position if provided
    var box_centre_lat, box_centre_long;
    if (!expanded && ownPosition) {
      box_centre_lat = ownPosition.coords.latitude;
      box_centre_long = ownPosition.coords.longitude;
    } else {
      box_centre_lat = (map_bottom_left.lat + map_top_right.lat) / 2;
      box_centre_long = (map_bottom_left.long + map_top_right.long) / 2;
    }

    // Calculate map position based on box position
    const [map_x0, map_y0] = coordsToPixels(
      map_bottom_left.lat,
      map_bottom_left.long,
      box_centre_lat,
      box_centre_long,
    );

    // Calculate our own dot
    const [dot_x, dot_y] = ownPosition
      ? coordsToPixels(
        ownPosition.coords.latitude,
        ownPosition.coords.longitude,
        box_centre_lat,
        box_centre_long,
      )
      : [0, 0];

    // Calculate all the other dots
    const otherDots = other_positions_and_details.map(
      ({ position, color, tooltip }, index) => {
        const [x, y] = coordsToPixels(
          position.coords.latitude,
          position.coords.longitude,
          box_centre_lat,
          box_centre_long,
        );
        const dt = 1e-3 * Date.now() - position.timestamp;
        const alpha = Math.max(
          1 - ((1 - MIN_ALPHA) * dt) / TIME_UNTIL_TRANSPARENT,
          MIN_ALPHA,
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
    boxWidthPx,
    boxHeightPx,
    ownPosition,
    otherPositionsAndDetailsString,
    coordsToPixels,
    setMapData,
  ]);

  const { map_x0, map_y0, dot_x, dot_y, otherDots } = mapData;

  const containerClasses = [styles.mapContainer];
  if (expanded) containerClasses.push(styles.mapContainerExpanded);
  else containerClasses.push(styles.mapContainerCorner);

  if (poppedOut) containerClasses.push(styles.mapContainerPoppedOut);

  return (
    <>
      <div className={containerClasses.join(" ")} ref={mapContainerRef}>
        {grayedOut ? <div className={styles.mapOverlay}></div> : null}
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
        {!grayedOut && ownPosition !== null ? (
          <Dot x={dot_x} y={dot_y} />
        ) : null}
        {otherDots}
        <div
          className={styles.clickCatcher}
          onClick={
            alwaysExpanded
              ? null
              : () => {
                console.log("Click!");
                setPoppedOut(!poppedOut);
                handleResize();
              }
          }
        ></div>
      </div>
    </>
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
              position.coords.longitude,
            );
            lastUpdateTime = currentTime;
          }
        },

        (error) => {
          console.error("Error watching position:", error);
        },
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
