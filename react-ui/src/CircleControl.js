import React, { useCallback, useEffect, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";

export default function CircleControl({ game_id }) {
  const setCircle = useCallback(
    (circle_type, location, radius_km) => {
      sendAPIRequest(
        "admin_set_circle_by_location",
        {
          game_id: game_id,
          name: circle_type,
          location: location,
          radius_km: radius_km,
        },
        "POST"
      );
    },
    [game_id]
  );

  const clearCircle = useCallback(
    (circle_type) => {
      sendAPIRequest(
        "admin_clear_circle",
        {
          game_id: game_id,
          name: circle_type,
        },
        "POST"
      );
    },
    [game_id]
  );

  // On load, get the location strings for the circles
  const [landmarks, setLandmarks] = useState([]);
  useEffect(() => {
    sendAPIRequest("admin_get_landmarks", {}, "GET", (landmarks) => {
      setLandmarks(landmarks);
    });
  }, [setLandmarks]);

  const circleTypeInput = useRef(null);
  const locationInput = useRef(null);
  const radiusInput = useRef(null);

  return (
    <>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const circle_type = circleTypeInput.current.value;
          const location = locationInput.current.value;
          const radius_km = parseFloat(radiusInput.current.value);
          setCircle(circle_type, location, radius_km);
        }}
      >
        <label>
          Circle Type:
          <select ref={circleTypeInput} required>
            <option value="EXCLUSION">EXCLUSION</option>
            <option value="NEXT">NEXT</option>
            <option value="BOTH">BOTH</option>
            <option value="DROP">DROP</option>
          </select>
        </label>
        <label>
          Location:
          <select ref={locationInput} required>
            {landmarks.map((landmark, idx) => (
              <option key={idx} value={landmark}>
                {landmark}
              </option>
            ))}
          </select>
        </label>
        <label>
          Radius (km):
          <input type="number" step="0.01" ref={radiusInput} required />
        </label>
        <button type="submit">Set Circle</button>
      </form>
      <button onClick={() => clearCircle(circleTypeInput.current.value)}>
        Clear Circle
      </button>

      <h4>Reminders</h4>
      <ul>
        <li>Circle 1: 0.70 km</li>
        <li>Circle 2: 0.42 km</li>
        <li>Circle 3: 0.18 km</li>
        <li>Circle 4: 0.05 km</li>
        <li>All drops: 0.01 km</li>
      </ul>
    </>
  );
}
