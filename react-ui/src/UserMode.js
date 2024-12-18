import React, { useCallback, useEffect, useState } from "react";

import { FullScreen, useFullScreenHandle } from "react-full-screen";

import { CrosshairImage, DeadImage, KnockedOutView } from "./GuideImages";
import FireButton from "./FireButton";
import BulletCount from "./BulletCount";
import { sendAPIRequest } from "./utils";
import WebcamView from "./WebcamView";
import UpdateListener, { UpdateSSEConnection } from "./UpdateListener";
import TickerView from "./TickerView";

import styles from "./UserMode.module.css";
import OnboardingView from "./OnboardingView";
import FullscreenButton from "./FullscreenButton";
import { MapViewSelf } from "./MapView";

import {
  isLocationPermissionGranted,
  isCameraPermissionGranted,
} from "./utils";
import { ButtonAndScoreboard } from "./Scoreboard";

const isGameRunning = (user) => Boolean(user && user.active);

function GetView({ user }) {
  const [triggerShot, setTriggerShot] = useState(0);
  const [triggerPermissionsRecheck, setTriggerPermissionsRecheck] = useState(0);

  const [permissionsGranted, setPermissionsGranted] = useState(false);

  // Check if all the required permissions are granted
  useEffect(() => {
    Promise.all([
      isLocationPermissionGranted(),
      isCameraPermissionGranted(),
    ]).then(([locationGranted, cameraGranted]) => {
      setPermissionsGranted(locationGranted && cameraGranted);
    });
  }, [triggerPermissionsRecheck, user]);

  // Trigger a recheck of permissions every 5s or when the user's state changes
  useEffect(() => {
    const interval = setInterval(() => {
      console.log("Rechecking permissions");
      setTriggerPermissionsRecheck((prev) => prev + 1);
    }, 5000);

    return () => {
      clearInterval(interval);
    };
  }, []);

  if (user === null) {
    return <p>Loading...</p>;
  }

  const isAlive = user ? user.state === "alive" : false;

  // Show the user the onboarding view if they haven't set their name, the game
  // isn't running, or if permissions aren't granted properly
  if (user.name === null || !isGameRunning(user) || !permissionsGranted) {
    return <OnboardingView user={user} />;
  }

  return (
    <>
      <div className={styles.monitorsContainer}>
        {isAlive ? (
          <BulletCount user={user} />
        ) : (
          <div>
            <ButtonAndScoreboard standalone />
          </div>
        )}
        <div className={styles.mapAndTickerContainer}>
          <MapViewSelf />
          <TickerView />
        </div>
      </div>

      <WebcamView trigger={triggerShot} isDead={!isAlive} />

      {isAlive ? (
        <CrosshairImage />
      ) : user.state === "knocked out" ? (
        <KnockedOutView user={user} />
      ) : (
        <DeadImage />
      )}

      {isAlive ? (
        <FireButton
          user={user}
          onClick={() => {
            setTriggerShot(triggerShot + 1);
          }}
        />
      ) : null}
    </>
  );
}

export default function UserMode() {
  const [userHash, setuserHash] = useState(0);

  const handle = useFullScreenHandle();

  const [isFullscreen, setIsFullscreen] = useState(false);

  const [user, setuser] = useState(null);

  const updateuser = useCallback(() => {
    sendAPIRequest("user_info", null, "GET", (data) => {
      setuser(data);
    });
  }, [setuser]);

  useEffect(updateuser, [updateuser, userHash]);

  const reportFullscreenChange = useCallback((state, _) => {
    setIsFullscreen(state);
  }, []);

  const view = (
    <GetView
      user={user}
      isFullscreen={isFullscreen}
      className={styles.viewContainer}
    />
  );

  return (
    <>
      <UpdateSSEConnection />
      <UpdateListener
        update_type="user"
        callback={() => {
          setuserHash(userHash + 1);
        }}
      />

      <FullScreen
        handle={handle}
        onChange={reportFullscreenChange}
        className={styles.fullscreenContainer}
      >
        {view}
        <FullscreenButton
          handle={handle}
          keepHintVisible={!isGameRunning(user)}
          isFullscreen={isFullscreen}
        />
      </FullScreen>
    </>
  );
}
