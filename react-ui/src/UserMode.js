import React, { useCallback, useEffect, useState } from 'react';

import { FullScreen, useFullScreenHandle } from "react-full-screen";

import { CrosshairImage, DeadImage, KnockedOutView } from './GuideImages';
import FireButton from './FireButton';
import BulletCount from './BulletCount';
import { sendAPIRequest } from './utils';
import WebcamView from './WebcamView';
import UpdateListener, { UpdateSSEConnection } from './UpdateListener';
import TickerView from './TickerView';

import styles from './UserMode.module.css'
import OnboardingView from './OnboardingView';
import FullscreenButton from './FullscreenButton';

const isGameRunning = (user) =>
  Boolean(user && user.active)

function GetView({ user }) {
  const [triggerShot, setTriggerShot] = useState(0);

  if (user === null) {
    return <p>Loading...</p>;
  }

  const isAlive = user ? user.state === "alive" : false;

  if (user.name === null || !isGameRunning(user)) {
    return <OnboardingView user={user} />;
  }

  return <>

    <div className={styles.monitorsContainer}>
      {isAlive ?
        <BulletCount user={user} />
        : <div></div>}
      <TickerView />
    </div>

    <WebcamView trigger={triggerShot} isDead={!isAlive} />

    {isAlive ?
      <CrosshairImage />
      :
      (
        user.state === "knocked out" ?
          < KnockedOutView user={user} /> :
          < DeadImage />
      )
    }

    {isAlive ?
      <FireButton user={user} onClick={
        () => {
          setTriggerShot(triggerShot + 1)
        }
      } />
      : null}

  </ >;
}


export default function UserMode() {
  const [userHash, setuserHash] = useState(0);

  const handle = useFullScreenHandle();

  const [isFullscreen, setIsFullscreen] = useState(false);

  const [user, setuser] = useState(null);

  const updateuser = useCallback(() => {
    sendAPIRequest("user_info", null, "GET", data => {
      setuser(data)
    })
  }, [setuser]);

  useEffect(updateuser, [updateuser, userHash]);

  const reportFullscreenChange = useCallback((state, _) => {
    setIsFullscreen(state);
  }, []);


  return <>
    <UpdateSSEConnection />
    <UpdateListener
      update_type="user"
      callback={() => {
        setuserHash(userHash + 1)
      }}
    />

    <FullScreen handle={handle} onChange={reportFullscreenChange}>
      <GetView user={user} isFullscreen={isFullscreen} />
    </FullScreen>
    <FullscreenButton handle={handle} keepHintVisible={!isGameRunning(user)} />
  </>
}
