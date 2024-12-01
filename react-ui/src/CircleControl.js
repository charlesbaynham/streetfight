import React, { useCallback, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";

export default function CircleControl() {
  const [status, setStatus] = useState("idle");

  const setCircle = useCallback((game_id, circle_type, location, radius_km) => {
    sendAPIRequest(
      "admin_set_circle_by_location",
      {
        game_id: game_id,
        name: circle_type,
        location: location,
        radius_km: radius_km,
      },
      "POST"
    ).then((response) => {
      if (response.ok) {
        setStatus("success");
      } else {
        setStatus("failure");
      }
    });
  }, []);

  const circleTypeInput = useRef(null);
  const locationInput = useRef(null);
  const radiusInput = useRef(null);

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const game_id = e.target.elements.game_id.value;
          const circle_type = circleTypeInput.current.value;
          const location = locationInput.current.value;
          const radius_km = radiusInput.current.value;
          setCircle(game_id, circle_type, location, radius_km);
        }}
      >
        <div>
          <label>
            Game ID:
            <input type="text" name="game_id" required />
          </label>
        </div>
        <div>
          <label>
            Circle Type:
            <select ref={circleTypeInput} required>
              <option value="EXCLUSION">EXCLUSION</option>
              <option value="NEXT">NEXT</option>
              <option value="BOTH">BOTH</option>
            </select>
          </label>
        </div>
        <div>
          <label>
            Location:
            <input type="text" ref={locationInput} required />
          </label>
        </div>
        <div>
          <label>
            Radius (km):
            <input type="number" ref={radiusInput} required />
          </label>
        </div>
        <button type="submit">Set Circle</button>
      </form>
      <div>Status: {status}</div>
    </div>
  );
}
