import React, { useEffect, useState } from "react";
import { sendAPIRequest } from "./utils";

import mapSrc from "./images/art/medkit.png";
import dotSrc from "./images/art/helmet.png";

import styles from "./MapView.module.css";

const map_top_left = {
  lat: 51.79323378424228,
  long: -2.7384925628606496,
};
const map_bottom_right = {
  lat: 51.79136033583688,
  long: -2.733293938485373,
};

function Dot({ x, y }) {
  return (
    <img
      className={styles.mapDot}
      src={dotSrc}
      alt=""
      style={{
        left: 100 * x + "%",
        bottom: 100 * y + "%",
      }}
    />
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

function MapView({ grayedOut = false, ownPosition = null }) {
  const x =
    (ownPosition?.coords.latitude - map_top_left.lat) /
    (map_bottom_right.lat - map_top_left.lat);
  const y =
    (ownPosition?.coords.longitude - map_top_left.long) /
    (map_bottom_right.long - map_top_left.long);

  return (
    <>
      <div className={styles.mapContainer}>
        {grayedOut ? <div className={styles.mapOverlay}></div> : null}
        <img className={styles.mapImage} src={mapSrc} alt="Map" />
        {!grayedOut && ownPosition !== null ? <Dot x={x} y={y} /> : null}
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
