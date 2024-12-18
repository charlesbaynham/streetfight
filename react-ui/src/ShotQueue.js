import React, { useCallback, useEffect, useState } from "react";
import { sendAPIRequest } from "./utils";
import { getShotFromCache } from "./ShotCache";
import { Container, Row, Col } from "react-bootstrap";

import styles from "./ShotQueue.module.css";

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

// TODO: Needs to automatically update on new shots

export default function ShotQueue() {
  const [shot, setShot] = useState(null);
  const [shotsInQueue, setShotsInQueue] = useState([]);
  const [currentShotIdx, setCurrentShotIdx] = useState(0);

  // On update, get the current list of shot IDs in the queue and pre-load them all
  const update = useCallback(() => {
    sendAPIRequest("admin_get_shots_info").then(async (response) => {
      if (!response.ok) return;
      const shot_ids = await response.json();

      setShotsInQueue(shot_ids);

      if (currentShotIdx >= shot_ids.length) {
        setCurrentShotIdx(shot_ids.length - 1);
      }

      // Load shots in background
      await Promise.all(
        shot_ids.map((id) => {
          console.log("Pre-loading shot", id);
          return getShotFromCache(id);
        }),
      );
    });
  }, [currentShotIdx]);

  // If current shot ID changes, load the shot from the cache into the state
  useEffect(() => {
    getShotFromCache(shotsInQueue[currentShotIdx]).then((shot) => {
      console.log("Setting shot", shot);
      setShot(shot);
    });
  }, [currentShotIdx, shotsInQueue]);

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

  const markShotMissed = useCallback(() => {
    sendAPIRequest("admin_mark_shot_missed", { shot_id: shot.id }, "POST").then(
      (_) => {
        update();
      },
    );
  }, [shot, update]);

  const refundShot = useCallback(() => {
    sendAPIRequest("admin_refund_shot", { shot_id: shot.id }, "POST").then(
      (_) => {
        update();
      },
    );
  }, [shot, update]);

  useEffect(update, [update]);

  const nextShot = useCallback(() => {
    if (currentShotIdx < shotsInQueue.length - 1) {
      setCurrentShotIdx(currentShotIdx + 1);
    }
  }, [currentShotIdx, shotsInQueue]);

  const previousShot = useCallback(() => {
    if (currentShotIdx > 0) {
      setCurrentShotIdx(currentShotIdx - 1);
    }
  }, [currentShotIdx]);

  return (
    <Container>
      <Row>
        <Col>
          <h1>
            Shot {currentShotIdx + 1} of {shotsInQueue.length}:
          </h1>
        </Col>
      </Row>
      <Row>
        <button
          onClick={() => {
            nextShot();
          }}
        >
          Next
        </button>
        <button
          onClick={() => {
            previousShot();
          }}
        >
          Previous
        </button>
      </Row>

      {shot ? (
        <>
          <Row>
            <Col>
              <em>By {shot.user.name}</em>
              <img
                className={styles.shotImg}
                alt="The next shot in the queue"
                src={shot.image_base64}
              />
            </Col>
            <Col>
              <NearestPlayers shot_data={shot} />
              {shot.game.teams.map((team, idx_team) => (
                <div key={idx_team}>
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
                </div>
              ))}
            </Col>
          </Row>
          <Row>
            <button
              onClick={() => {
                markShotMissed();
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
          </Row>
        </>
      ) : null}
    </Container>
  );
}
