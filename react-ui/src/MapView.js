import React, { useCallback, useEffect, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";

import mapSrc from "./images/art/medkit.png";
import dotSrc from "./images/art/helmet.png";

import styles from "./MapView.module.css";

const map_bottom_left = {
  long: -2.742,
  lat: 51.787,
};

const map_top_right = {
  long: -2.73,
  lat: 51.796,
};

const degreesLongitudePerKm = 1 / (111.32 * Math.cos((map_bottom_left.lat + map_top_right.lat) / 2 * (Math.PI / 180)));
const degreesLatitudePerKm = 1 / 110.574;

const MAP_WIDTH_KM = (map_top_right.long - map_bottom_left.long) / degreesLongitudePerKm;
const MAP_HEIGHT_KM = (map_top_right.lat - map_bottom_left.lat) / degreesLatitudePerKm;

const MAP_POLL_TIME = 5 * 1000;
const RATE_LIMIT_INTERVAL = 1 * 1000;

const CORNER_BOX_WIDTH_KM = 0.5;

// FIXME: needs to be centered in css
function Dot({ x, y, color = null }) {
  return color === null ? (
    <img
      className={styles.mapDotSelf}
      src={dotSrc}
      alt=""
      style={{
        left: 100 * x + "%",
        bottom: 100 * y + "%",
      }}
    />
  ) : (
    <div
      className={styles.mapDotGeneric}
      style={{
        left: 100 * x + "%",
        bottom: 100 * y + "%",
        backgroundColor: color,
      }}
    />
  );
}

let lastUpdateTime = 0;

function sendLocationUpdate(lat, long) {
  const currentTime = Date.now();
  if (currentTime - lastUpdateTime >= RATE_LIMIT_INTERVAL) {
    sendAPIRequest(
      "set_location",
      {
        latitude: lat,
        longitude: long,
      },
      "POST",
      null,
    );
    lastUpdateTime = currentTime;
  }
}

function MapView({
  grayedOut = false,
  ownPosition = null,
  other_positions_and_colors = [],
  expanded = false,
}) {
  const posToXY = useCallback((pos) => {
    const x =
      (pos?.coords.longitude - map_bottom_left.long) /
      (map_top_right.long - map_bottom_left.long);

    const y =
      (pos?.coords.latitude - map_bottom_left.lat) /
      (map_top_right.lat - map_bottom_left.lat);
    return { x, y };
  }, []);

  const { x, y } = posToXY(ownPosition);

  const otherDots = other_positions_and_colors.map(
    ({ position, color }, index) => {
      const { x, y } = posToXY(position);
      return <Dot key={index} x={x} y={y} color={color} />;
    },
  );

  const mapContainerRef = useRef(null);
  const [mapWidthPx, setMapWidth] = useState(0);
  const [mapHeightPx, setMapHeight] = useState(0);


  // Measure the width and height of the map container so that we can scale the
  // map image. Tolerate resizes / screen rotations.
  useEffect(() => {
    const handleResize = () => {
      if (mapContainerRef.current) {
        setMapWidth(mapContainerRef.current.clientWidth);
        setMapHeight(mapContainerRef.current.clientHeight);
      }
    };

    window.addEventListener("resize", handleResize);

    // Initial measurement
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [mapContainerRef]);

  const coordsToPixels = useCallback(
    (lat, long) => {
      const x_km = (long - map_bottom_left.long) / degreesLongitudePerKm;
      const y_km = (lat - map_bottom_left.lat) / degreesLatitudePerKm;

      const x_px = x_km / MAP_WIDTH_KM * mapWidthPx;
      const y_px = y_km / MAP_HEIGHT_KM * mapHeightPx;

      // FIXME this is completely wrong

      console.log(x_px, y_px);

      return [x_px, y_px ];
    },
    [mapWidthPx, mapHeightPx],
  );

  const [map_x0, map_y0]= coordsToPixels(map_bottom_left.lat, map_bottom_left.long);

  console.log(map_x0, map_y0);

  console.log(`left ${map_x0}px bottom ${map_y0}px`);


  return (
    <>
      <div
        className={`${styles.mapContainer} ${expanded ? styles.mapContainerExpanded : styles.mapContainerCorner}`}
        ref={mapContainerRef}
      >
        {grayedOut ? <div className={styles.mapOverlay}></div> : null}
        <div
          className={styles.mapImage}
          src={mapSrc}
          alt="Map"
          style={{
            backgroundImage: `url(${mapSrc})`,
            backgroundPosition: `left ${map_x0}px bottom ${map_y0}px`,
            backgroundRepeat: "no-repeat",
            // backgroundSize: MAP_WIDTH_KM / CORNER_BOX_WIDTH_KM * 100 + "% " + MAP_HEIGHT_KM / CORNER_BOX_WIDTH_KM * 100 + "%",
          }}
        />
        {!grayedOut && ownPosition !== null ? <Dot x={x} y={y} /> : null}
        {otherDots}
      </div>
    </>
  );
}

export function MapViewSelf() {
  const [position, setPosition] = useState(null);

  useEffect(() => {
    if (navigator.geolocation) {
      // Register a callback for changes to the user's position.
      // This a) updates the location on the map and b) sends the location to the server.
      const watchId = navigator.geolocation.watchPosition(
        (position) => {
          setPosition(position);
          sendLocationUpdate(
            position.coords.latitude,
            position.coords.longitude,
          );
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
  const [locationWithColors, setLocationWithColors] = useState([]);

  const updateLocations = useCallback(() => {
    sendAPIRequest("admin_get_locations").then(async (response) => {
      if (!response.ok) return;
      const locations = await response.json();

      const team_ids = locations.map((user) => user.team_id);
      const unique_team_ids = [...new Set(team_ids)];

      // Assign a color to each unique team
      const colors = [
        "brown",
        "black",
        "red",
        "blue",
        "green",
        "yellow",
        "purple",
        "orange",
        "pink",
        "cyan",
      ];
      const teamColors = {};
      unique_team_ids.forEach((team_id, index) => {
        teamColors[team_id] = colors[index % colors.length];
      });

      // Color each location point according to the team
      // FIXME: Should be gray if dead
      setLocationWithColors(
        locations.map((user) => ({
          position: {
            coords: { latitude: user.latitude, longitude: user.longitude },
          },
          color: teamColors[user.team_id],
        })),
      );
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
    <MapView other_positions_and_colors={locationWithColors} expanded={true} />
  );
}
