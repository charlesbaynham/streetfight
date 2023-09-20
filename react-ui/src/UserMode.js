import React, { useCallback, useEffect, useState } from 'react';



import { FullScreen, useFullScreenHandle } from "react-full-screen";

import { CrosshairImage, DeadImage } from './GuideImages';
import FireButton from './FireButton';
import BulletCount from './BulletCount';
import { sendAPIRequest } from './utils';
import WebcamView from './WebcamView';
import UpdateListener, { UpdateSSEConnection } from './UpdateListener';
import TickerView from './TickerView';

import styles from './UserMode.module.css'
import OnboardingView from './OnboardingView';
import FullscreenButton from './FullscreenButton';

const isGameRunning = (userState) =>
  Boolean(userState && userState.active)

function GetView({ userState }) {
  const [triggerShot, setTriggerShot] = useState(0);


  if (userState === null) {
    return <p>Loading...</p>;
    ;
  }

  const isAlive = userState ? (userState.hit_points > 0) : false;
  const isInTeam = userState ? userState.team_id !== null : false;
  const hasBullets = userState ? (userState.num_bullets > 0) : false;

  if (userState.name === null || !isGameRunning(userState)) {
    return <OnboardingView userState={userState} />;
  }

  return <>

    <div className={styles.monitorsContainer}>
      {isAlive ?
        <BulletCount user={userState} />
        : <div></div>}
      <TickerView />
    </div>

    <WebcamView trigger={triggerShot} isDead={!isAlive} />

    {isAlive ?
      <CrosshairImage />
      :
      <DeadImage />
    }

    {isAlive ?
      <FireButton userHasAmmo={isInTeam && hasBullets} onClick={
        () => {
          setTriggerShot(triggerShot + 1)
        }
      } />
      : null}

  </ >;
}


export default function UserMode() {
  const [userStateHash, setUserStateHash] = useState(0);

  const handle = useFullScreenHandle();

  const [isFullscreen, setIsFullscreen] = useState(false);

  const [userState, setUserState] = useState(null);

  const updateUserState = useCallback(() => {
    sendAPIRequest("user_info", null, "GET", data => {
      setUserState(data)
    })
  }, [setUserState]);

  useEffect(updateUserState, [updateUserState, userStateHash]);

  const reportFullscreenChange = useCallback((state, _) => {
    setIsFullscreen(state);
  }, []);


  return <>
    <UpdateSSEConnection />
    <UpdateListener
      update_type="user"
      callback={() => {
        setUserStateHash(userStateHash + 1)
      }}
    />

    <FullScreen handle={handle} onChange={reportFullscreenChange}>
      <GetView userState={userState} isFullscreen={isFullscreen} />
    </FullScreen>
    {isFullscreen ? null :
      <FullscreenButton handle={handle} keepHintVisible={!isGameRunning(userState)} />
    }
  </>
}
