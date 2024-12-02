import React, { useCallback, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";

export default function CircleControl({ game_id }) {
  const [status, setStatus] = useState("idle");

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
        "POST",
      ).then((response) => {
        if (response.ok) {
          setStatus("success");
        } else {
          setStatus("failure");
        }
      });
    },
    [game_id],
  );

  const clearCircle = useCallback(
    (circle_type) => {
      sendAPIRequest(
        "admin_clear_circle",
        {
          game_id: game_id,
          name: circle_type,
        },
        "POST",
      ).then((response) => {
        if (response.ok) {
          setStatus("success");
        } else {
          setStatus("failure");
        }
      });
    },
    [game_id],
  );

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
          </select>
        </label>
        <label>
          Location:
          <input type="text" ref={locationInput} required />
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
    </>
  );
}
