import React from "react";

import mapSrc from "./images/art/medkit.png";
import dotSrc from "./images/art/bullet.png";

import styles from "./MapView.module.css";

const map_top_left = {
  lat: 51.4163,
  long: -0.275,
}
const map_bottom_right = {
  lat: 51.4162,
  long: -0.2753,
}

function Dot({ x, y }) {
  return <img
    className={styles.mapDot}
    src={dotSrc}
    style={{
      left: 100*x + "%",
      bottom: 100*y + "%",
    }}
  />
}

export default function MapView({ position }) {

  if (!position) return <p>Unknown</p>


  const x = (position.coords.latitude - map_top_left.lat) / (map_bottom_right.lat - map_top_left.lat);
  const y = (position.coords.longitude - map_top_left.long) / (map_bottom_right.long - map_top_left.long);

  const out = <>
    <p>Timestamp: {position.timestamp},</p>
    <p>Latitude: {position.coords.latitude},</p>
    <p>Longitude: {position.coords.longitude},</p>
    <p>Accuracy: {position.coords.accuracy}</p>
    <p>x = {x}</p>
    <p>y = {y}</p>
  </>

  return <>
    {out}
    <div className={styles.mapContainer}>
      <img className={styles.mapImage} src={mapSrc} />
      <Dot x={x} y={y} />
    </div>
  </>

};


