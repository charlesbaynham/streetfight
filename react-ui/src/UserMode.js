import React, { useCallback, useEffect, useState } from "react";

import { useSearchParams } from "react-router-dom";

import { FullScreen, useFullScreenHandle } from "react-full-screen";

import { CrosshairImage, DeadImage, KnockedOutView } from "./GuideImages";
import FireButton from "./FireButton";
import BulletCount from "./BulletCount";
import { sendAPIRequest } from "./utils";
import WebcamView from "./WebcamView";
import UpdateListener, { UpdateSSEConnection } from "./UpdateListener";
import TickerView from "./TickerView";
import JoinFromQueryParams from "./JoinFromQueryParams";
import WhatIsThis from "./WhatIsThis";

import styles from "./UserMode.module.css";
import OnboardingView from "./OnboardingView";
import FullscreenButton from "./FullscreenButton";
import { MapViewSelf } from "./MapView";
import NextEventStrip from "./NextEventStrip";
import { RadarStrip } from "./RadarLayer";
import prose from "./prose";

import {
  isLocationPermissionGranted,
  isCameraPermissionGranted,
  isLocationBypassActive,
} from "./utils";
import { ButtonAndScoreboard } from "./Scoreboard";
import { ShotHistoryButton, ShotHistoryController } from "./ShotHistory";
import { TeamLeaderButton } from "./TeamLeaderPanel";
import ShotReceivedOverlay from "./ShotReceivedOverlay";
import RefusedNotice from "./RefusedNotice";
import useWakeLock from "./useWakeLock";
import useAudioUnlock from "./useAudioUnlock";
import useKnockedOutSound from "./useKnockedOutSound";

const isGameRunning = (user) => Boolean(user && user.active);

// Somebody who has never joined anything: no name, no game and no team. Every
// visitor gets a User row the first time they load the site (get_user_id ->
// _make_user), so a stranger who pointed their camera at a card taped to a
// lamppost is indistinguishable from a player except by this - they have
// nothing. They get the explanation (WhatIsThis.js) rather than the join
// steps, which for them lead nowhere anyway.
//
// A real player only ever looks like this before their very first join, and
// they arrive holding a join code - see useIsStranger below.
const isStranger = (user) =>
  Boolean(user) && !user.name && !user.game_id && !user.team_id;

// Whether to show a visitor the explanation instead of the join steps.
//
// The check is not just isStranger(), because a player signing up is briefly
// indistinguishable from a stranger: they land on "/?j=<code>" and stay a
// nobody until JoinFromQueryParams' POST comes back. Worse, a join that
// *fails* - a code for a game that has since been reset, say - navigates back
// to "/" with the query stripped and a popup saying why, and that player must
// read the explanation rather than be told they are not part of this. So a
// tab that has been handed a join code never shows the landing page again,
// whatever came of it.
function useIsStranger(user) {
  const [searchParams] = useSearchParams();
  const joinCode = searchParams.get("j");

  const [sawJoinCode, setSawJoinCode] = useState(joinCode !== null);

  useEffect(() => {
    if (joinCode !== null) setSawJoinCode(true);
  }, [joinCode]);

  return isStranger(user) && joinCode === null && !sawJoinCode;
}

function GetView({ user }) {
  useWakeLock();
  // Both before the early returns below, and so alive on the onboarding
  // screen: the unlock has to be armed by the taps a player spends there
  // (see useAudioUnlock), and a knockout is seeded from the first state this
  // component ever sees, whichever screen is showing at the time.
  useAudioUnlock();
  useKnockedOutSound(user);

  const [triggerShot, setTriggerShot] = useState(0);
  const [triggerPermissionsRecheck, setTriggerPermissionsRecheck] = useState(0);

  const [permissionsGranted, setPermissionsGranted] = useState(false);

  // Check if all the required permissions are granted
  useEffect(() => {
    Promise.all([
      isLocationPermissionGranted(),
      isCameraPermissionGranted(),
    ]).then(([locationGranted, cameraGranted]) => {
      const locationOk = locationGranted || isLocationBypassActive();
      setPermissionsGranted(locationOk && cameraGranted);
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
    return <p>{prose.userMode.loading}</p>;
  }

  const isAlive = user ? user.state === "alive" : false;

  // Show the user the onboarding view if they haven't set their name, the game
  // isn't running, or if permissions aren't granted properly
  if (user.name === null || !isGameRunning(user) || !permissionsGranted) {
    // The strip goes above the waiting page too: somebody standing at the
    // door with the game still paused is exactly who wants to know a drop is
    // ten minutes out. It renders nothing when nothing is cued.
    return (
      <>
        <NextEventStrip user={user} />
        <OnboardingView user={user} />
      </>
    );
  }

  return (
    <>
      <NextEventStrip user={user} />
      <RadarStrip user={user} />
      <div className={styles.monitorsContainer}>
        {isAlive ? (
          <BulletCount user={user} />
        ) : (
          <div>
            <ButtonAndScoreboard standalone />
            <ShotHistoryButton standalone />
            <TeamLeaderButton user={user} standalone />
          </div>
        )}
        <div className={styles.mapAndTickerContainer}>
          <MapViewSelf />
          <TickerView />
        </div>
      </div>

      <WebcamView trigger={triggerShot} isDead={!isAlive} />

      <ShotHistoryController />
      <ShotReceivedOverlay user={user} />
      <RefusedNotice />

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

  const showLandingPage = useIsStranger(user);

  // Above the SSE connection and the full-screen frame rather than inside
  // GetView, so a passer-by reading this costs the server nothing: no stream
  // to keep open (and to clean up - see the SSE note in CLAUDE.md), and none
  // of the chrome that is addressed to a player, like the "better in
  // full-screen" scrawl.
  if (showLandingPage) return <WhatIsThis />;

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
      {/* Top level, not in the alive-only path: joining happens during
          onboarding, before the player has a team */}
      <JoinFromQueryParams />
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
