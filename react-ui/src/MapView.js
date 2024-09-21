import React, { useEffect, useState } from "react";

import mapSrc from "./images/art/medkit.png";
import dotSrc from "./images/art/bullet.png";

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

export default function MapView() {

  const [position, setPosition] = useState(null);

  useEffect(() => {
    if (navigator.geolocation) {
      const watchId = navigator.geolocation.watchPosition(
        (position) => {
          setPosition(position);
        },
        (error) => {
          console.error("Error watching position:", error);
        },
      );

      return () => {
        navigator.geolocation.clearWatch(watchId);
      };
    } else {
      console.error("Geolocation is not supported by this browser.");
    }
  }, []);


  const hideMap = position === null;

  // FIXME: Better view for a map with no location

  const x =
    (position?.coords.latitude - map_top_left.lat) /
    (map_bottom_right.lat - map_top_left.lat);
  const y =
    (position?.coords.longitude - map_top_left.long) /
    (map_bottom_right.long - map_top_left.long);


  return (
    <>
      <div className={styles.mapContainer}>
        <img className={styles.mapImage} src={mapSrc} alt="Map" />
        {hideMap ? null : <Dot x={x} y={y}  />}
      </div>
    </>
  );
}
