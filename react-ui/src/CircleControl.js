import React, { useEffect, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";
import { adminPost } from "./AdminCommon";

// Place, move or clear the game circles - either at a named landmark or at raw
// coordinates. The circle-type selector is shared by all three actions.
export default function CircleControl({ game_id }) {
  const [landmarks, setLandmarks] = useState([]);
  useEffect(() => {
    sendAPIRequest("admin_get_landmarks", {}, "GET", (landmarks) => {
      setLandmarks(landmarks);
    });
  }, [setLandmarks]);

  const circleTypeInput = useRef(null);
  const locationInput = useRef(null);
  const landmarkRadiusInput = useRef(null);
  const latInput = useRef(null);
  const longInput = useRef(null);
  const coordsRadiusInput = useRef(null);

  return (
    <>
      <label>
        Circle:{" "}
        <select ref={circleTypeInput}>
          <option value="EXCLUSION">EXCLUSION</option>
          <option value="NEXT">NEXT</option>
          <option value="BOTH">BOTH</option>
          <option value="DROP">DROP</option>
        </select>
      </label>{" "}
      <button
        onClick={() =>
          adminPost("admin_clear_circle", {
            game_id: game_id,
            name: circleTypeInput.current.value,
          })
        }
      >
        Clear circle
      </button>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          adminPost("admin_set_circle_by_location", {
            game_id: game_id,
            name: circleTypeInput.current.value,
            location: locationInput.current.value,
            radius_km: parseFloat(landmarkRadiusInput.current.value),
          });
        }}
      >
        <select ref={locationInput} required>
          {landmarks.map((landmark, idx) => (
            <option key={idx} value={landmark}>
              {landmark}
            </option>
          ))}
        </select>{" "}
        <input
          type="number"
          step="0.01"
          placeholder="radius (km)"
          ref={landmarkRadiusInput}
          required
        />{" "}
        <button type="submit">Set at landmark</button>
      </form>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          adminPost("admin_set_circle", {
            game_id: game_id,
            name: circleTypeInput.current.value,
            lat: parseFloat(latInput.current.value),
            long: parseFloat(longInput.current.value),
            radius_km: parseFloat(coordsRadiusInput.current.value),
          });
        }}
      >
        <input
          type="number"
          step="any"
          placeholder="lat"
          ref={latInput}
          required
        />{" "}
        <input
          type="number"
          step="any"
          placeholder="long"
          ref={longInput}
          required
        />{" "}
        <input
          type="number"
          step="0.01"
          placeholder="radius (km)"
          ref={coordsRadiusInput}
          required
        />{" "}
        <button type="submit">Set at coordinates</button>
      </form>
      <p>
        Radius reminders: circle 1: 0.70, circle 2: 0.42, circle 3: 0.18, circle
        4: 0.05, drops: 0.01 km
      </p>
    </>
  );
}
