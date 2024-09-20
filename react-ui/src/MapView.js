import React from "react";

import mapSrc from "./images/art/medkit.png";
import dotSrc from "./images/art/bullet.png";

import styles from "./MapView.module.css";

const map_top_left = {
  lat: 51.503021862376734,
  long: -0.18977085858990242,
};
const map_bottom_right = {
  lat: 51.4930475913438,
  long: -0.17170030380316062,
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

export default function MapView({ position }) {
  if (!position) return <p>Unknown</p>;

  const x =
    (position.coords.latitude - map_top_left.lat) /
    (map_bottom_right.lat - map_top_left.lat);
  const y =
    (position.coords.longitude - map_top_left.long) /
    (map_bottom_right.long - map_top_left.long);

  const out = (
    <>
      <p>Timestamp: {position.timestamp},</p>
      <p>Latitude: {position.coords.latitude},</p>
      <p>Longitude: {position.coords.longitude},</p>
      <p>Accuracy: {position.coords.accuracy}</p>
      <p>x = {x}</p>
      <p>y = {y}</p>
    </>
  );

  return (
    <>
      <h3>Details:</h3>
      {out}

      <h3>Map:</h3>
      <div className={styles.mapContainer}>
        <img
          className={styles.mapImage}
          src={mapSrc}
          alt="Map"
        />
        <Dot x={x} y={y} />
      </div>
    </>
  );
}
