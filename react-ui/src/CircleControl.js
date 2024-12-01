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
}
