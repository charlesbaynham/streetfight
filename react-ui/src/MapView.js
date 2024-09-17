import React from "react";

export default function MapView({ position }) {

  const out = position ? <>
    <p>Timestamp: {position.timestamp},</p>
    <p>Latitude: {position.coords.latitude},</p>
    <p>Longitude: {position.coords.longitude},</p>
    <p>Accuracy: {position.coords.accuracy}</p>
  </> : <p>Unknown</p>

  return out;
};


