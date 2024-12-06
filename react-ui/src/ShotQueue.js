import React, { useCallback, useEffect, useState } from "react";
import { sendAPIRequest } from "./utils";

function NearestPlayers({ shot_data }) {
  if (shot_data === null) return;

  const shooting_user_id = shot_data.user_id;
  const context = JSON.parse(shot_data.location_context);

  // Get user location in context array
  const userIndex = context.findIndex(
    (location) => location.user_id === shooting_user_id,
  );
  console.log("User index in context array:", userIndex);

  const shooting_user_data = context[userIndex];
  const shooting_user_latitude = shooting_user_data.latitude;
  const shooting_user_longitude = shooting_user_data.longitude;

  // Remove the user from the context array
  const otherUsersContext = context.filter(
    (location) => location.user_id !== shooting_user_id,
  );
  console.log("Updated context array:", otherUsersContext);

  // For each remaining player, calculate the distance from them to the shooting player
  const shooting_users = otherUsersContext.map(
    ({
      user_id,
      team_id,
      user,
      team,
      latitude,
      longitude,
      state,
      timestamp,
    }) => {
      // Calculate distance between two points
      const R = 6371e3; // metres
      const φ1 = (shooting_user_latitude * Math.PI) / 180; // φ, λ in radians
      const φ2 = (latitude * Math.PI) / 180;
      const Δφ = ((latitude - shooting_user_latitude) * Math.PI) / 180;
      const Δλ = ((longitude - shooting_user_longitude) * Math.PI) / 180;

      const a =
        Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
        Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

      const distance = R * c; // in metres

      return {
        distance,
        user_id,
        team_id,
        user,
        team,
        latitude,
        longitude,
        state,
        timestamp,
      };
    },
  );

  // Sort shooting_users by distance
  shooting_users.sort((a, b) => (a.distance > b.distance ? 1 : -1));

  return (
    <>
      <h3>Candidates:</h3>
      <ul>
        {shooting_users.map((user, idx) => (
          <li key={idx}>
            {user.user} - {user.team} - ({user.distance.toFixed(2)}m)
          </li>
        ))}
      </ul>
    </>
  );
}

export default function ShotQueue() {
  const [shot, setShot] = useState(null);
  const [numShots, setNumShots] = useState("");

  const update = useCallback(() => {
    sendAPIRequest("admin_get_shots", { limit: 1 }).then(async (response) => {
      if (!response.ok) return;
      const data = await response.json();
      setNumShots(data.numInQueue);
      if (data.shots.length > 0) {
        const newShot = data.shots[0];
        console.log("New shot:");
        console.dir(newShot);
        console.log(JSON.parse(newShot.location_context));
        setShot(newShot);
      } else {
        setShot(null);
      }
    });
  }, []);

  const hitUser = useCallback(
    (shot_id, target_user_id) => {
      sendAPIRequest(
        "admin_shot_hit_user",
        {
          shot_id: shot_id,
          target_user_id: target_user_id,
        },
        "POST",
      ).then((_) => {
        update();
      });
    },
    [update],
  );

  const dismissShot = useCallback(() => {
    sendAPIRequest(
      "admin_mark_shot_checked",
      { shot_id: shot.id },
      "POST",
    ).then((_) => {
      update();
    });
  }, [shot, update]);

  const refundShot = useCallback(() => {
    sendAPIRequest("admin_refund_shot", { shot_id: shot.id }, "POST").then(
      (_) => {
        update();
      }
    );
  }, [shot, update]);

  useEffect(update, [update]);

  return (
    <>
      <h1>Next unchecked shot ({numShots} in queue):</h1>

      {shot ? (
        <>
          <em>By {shot.user.name}</em>
          <img alt="The next shot in the queue" src={shot.image_base64} />
          <NearestPlayers shot_data={shot} />
          {shot.game.teams.map((team, idx_team) => (
            <>
              <h3>{team.name}</h3>
              <ul>
                {team.users.map((target_user, idx_target_user) => (
                  <li key={idx_target_user ** 2 + idx_team ** 3}>
                    {target_user.name}
                    <button
                      onClick={() => {
                        hitUser(shot.id, target_user.id);
                      }}
                    >
                      Hit
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ))}
          <button
            onClick={() => {
              dismissShot();
            }}
          >
            Missed
          </button>
          <button
            onClick={() => {
              refundShot();
            }}
          >
            Refund
          </button>
        </>
      ) : null}
    </>
  );
}
