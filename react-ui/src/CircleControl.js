import React, { useEffect, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";
import { adminPost } from "./AdminCommon";

// Place, move or clear the game circles - either at a named landmark or at raw
// coordinates. The circle-type selector is shared by all three actions.
//
// Above all of that is the plan (backend/circles.py), which is what the night
// actually runs on: the game arms each circle as the one before it closes, so
// this panel usually only has to say which one is sitting privately on the map
// waiting to be cued.
export default function CircleControl({ game }) {
  const game_id = game.id;
  const [landmarks, setLandmarks] = useState([]);
  const [plan, setPlan] = useState([]);
  useEffect(() => {
    sendAPIRequest("admin_get_landmarks", {}, "GET", (landmarks) => {
      setLandmarks(landmarks);
    });
    sendAPIRequest("admin_get_circle_plan", {}, "GET", (plan) => {
      setPlan(plan);
    });
  }, [setLandmarks, setPlan]);

  const armed = plan.find((circle) => circle.index === game.circle_plan_index);
  const placed = game.next_circle_lat !== null;

  const circleTypeInput = useRef(null);
  const locationInput = useRef(null);
  const landmarkRadiusInput = useRef(null);
  const latInput = useRef(null);
  const longInput = useRef(null);
  const coordsRadiusInput = useRef(null);

  return (
    <>
      <p>
        {armed ? (
          <>
            Plan: <b>{armed.name}</b> ({armed.radius_km} km),{" "}
            {!armed.known ? (
              <b>no coordinates &mdash; place it by hand</b>
            ) : placed ? (
              <>
                on the map and <b>private</b> until you cue it
              </>
            ) : (
              <b>not placed</b>
            )}
          </>
        ) : (
          <>
            Plan: <b>finished</b> &mdash; every planned circle has closed
          </>
        )}{" "}
        {armed ? (
          <button
            onClick={() =>
              adminPost("admin_arm_planned_circle", { game_id: game_id })
            }
          >
            Place planned circle
          </button>
        ) : null}{" "}
        {plan.some((circle) => circle.index === game.circle_plan_index + 1) ? (
          <button
            onClick={() =>
              adminPost("admin_arm_planned_circle", {
                game_id: game_id,
                index: game.circle_plan_index + 1,
              })
            }
          >
            Skip to the next one
          </button>
        ) : null}
      </p>
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
