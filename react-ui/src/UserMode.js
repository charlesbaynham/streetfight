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
import NoNameView from './NoNameView';



function GetView({ userState }) {
  const [triggerShot, setTriggerShot] = useState(0);

  if (userState === null) {
    return <p>Loading...</p>;
    ;
  }

  if (userState.name === null) {
    return <NoNameView />;
  }

  // if (userState.team === null) {
  //   return <NoTeamView />;
  // }

  const isAlive = userState ? (userState.hit_points > 0) : false;
  const isInTeam = userState ? ("team_id" in userState) : false;
  const hasBullets = userState ? (userState.num_bullets > 0) : false;

  return <>

    <div className={styles.monitorsContainer}>
      <BulletCount user={userState} />
      <TickerView />
    </div>



    <WebcamView trigger={triggerShot} />

    {isAlive ?
      <CrosshairImage />
      :
      <DeadImage />
    }

    <FireButton buttonActive={isInTeam && isAlive && hasBullets} onClick={
      () => {
        setTriggerShot(triggerShot + 1)
      }
    } />

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
        console.log(`Updating userStateHash to ${userStateHash + 1}`)
        setUserStateHash(userStateHash + 1)
      }}
    />

    {isFullscreen ? null :
      <button onClick={handle.enter}>
        Fullscreen
      </button>
    }
    <FullScreen handle={handle} onChange={reportFullscreenChange}>
      <GetView userState={userState} isFullscreen={isFullscreen} />
    </FullScreen>
  </>
}
