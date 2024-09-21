import React, { useCallback, useEffect, useState } from "react";
import { sendAPIRequest } from "./utils";

import mapSrc from "./images/art/medkit.png";
import dotSrc from "./images/art/helmet.png";

import styles from "./MapView.module.css";

const map_bottom_left = {
  long: -2.742,
  lat: 51.787,
};

const map_top_right = {
  long: -2.730,
  lat: 51.796,
};


function Dot({ x, y, color = null }) {
  return (
    color === null ? (
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
    )
  );
}

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

function MapView({ grayedOut = false, ownPosition = null, other_positions_and_colors = [
  { position: { coords: { latitude: 51.787, longitude: -2.731 } }, color: "brown" },
  { position: { coords: { latitude: 51.788, longitude: -2.733 } }, color: "black" },
  { position: { coords: { latitude: 51.789, longitude: -2.735 } }, color: "red" },
  { position: { coords: { latitude: 51.790, longitude: -2.736 } }, color: "blue" },
  { position: { coords: { latitude: 51.791, longitude: -2.737 } }, color: "green" },
  { position: { coords: { latitude: 51.792, longitude: -2.738 } }, color: "yellow" },
  { position: { coords: { latitude: 51.793, longitude: -2.739 } }, color: "purple" },
  { position: { coords: { latitude: 51.794, longitude: -2.740 } }, color: "orange" },
  { position: { coords: { latitude: 51.793, longitude: -2.741 } }, color: "pink" },
  { position: { coords: { latitude: 51.792, longitude: -2.742 } }, color: "cyan" },

  // FIXME
] }) {
  const posToXY = useCallback((pos) => {
    const x =
    (pos?.coords.longitude - map_bottom_left.long) /
    (map_top_right.long - map_bottom_left.long);

    const y =(pos?.coords.latitude - map_bottom_left.lat) /
    (map_top_right.lat - map_bottom_left.lat);
    return { x, y };
  }, []);

  const { x, y } = posToXY(ownPosition);

  const otherDots = other_positions_and_colors.map(({ position, color }, index) => {
    const { x, y } = posToXY(position);
    return <Dot key={index} x={x} y={y} color={color} />;
  });

  return (
    <>
      <div className={styles.mapContainer}>
        {grayedOut ? <div className={styles.mapOverlay}></div> : null}
        <img className={styles.mapImage} src={mapSrc} alt="Map" />
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
  useEffect(() => {
    sendAPIRequest("admin_get_locations").then(async (response) => {
      if (!response.ok) return;
      const data = await response.json();
      console.log(data);
    });
  });

  return <MapView />;
}
