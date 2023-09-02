import React, { useCallback, useEffect, useRef, useState } from 'react';

import { FullScreen, useFullScreenHandle } from "react-full-screen";

import { CrosshairImage, QRImage, DeadImage } from './GuideImages';
import FireButton from './FireButton';
import ScanButton from './ScanButton';
import BulletCount from './BulletCount';
import { sendAPIRequest } from './utils';
import WebcamView from './WebcamView';
import UserStateUpdater from './UserUpdater';


export default function UserMode() {
  const [userStateHash, setUserStateHash] = useState(0);

  const handle = useFullScreenHandle();
  const [isFullscreen, setIsFullscreen] = useState(false);

  const [scanMode, setScanMode] = useState(false);

  const [userState, setUserState] = useState(null);

  const updateUserState = useCallback(() => {
    sendAPIRequest("user_info", null, "GET", data => {
      setUserState(data)
    })
  }, [setUserState]);

  useEffect(updateUserState, [updateUserState, userStateHash]);

  const reportChange = useCallback((state, _) => {
    setIsFullscreen(state);
  }, []);

  const [triggerShot, setTriggerShot] = useState(0);

  const loadingView = <p>Loading...</p>;

  const setUserName = useCallback((username) => {
    sendAPIRequest("set_name", { name: username }, 'POST', updateUserState);
  });

  const setNameInput = useRef();
  const noNameView = <>
    <span>Enter your name:</span>
    <input ref={setNameInput} />
    <button onClick={() => { setUserName(setNameInput.current.value) }}>Submit</button>
  </>;

  const isAlive = userState ? (userState.hit_points > 0) : false;
  const isInTeam = userState ? ("team_id" in userState) : false;
  const hasBullets = userState ? (userState.num_bullets > 0) : false;

  const playingView = userState ? (
    <>
      <UserStateUpdater known_hash={userStateHash} callback={(d) => { setUserStateHash(d) }} />

      <button onClick={handle.enter}>
        Fullscreen
      </button>

      <FullScreen handle={handle} onChange={reportChange}>
        <BulletCount user={userState} />

        <WebcamView trigger={triggerShot} />

        {isAlive ?
          (scanMode ? <QRImage /> : <CrosshairImage />)
          :
          <DeadImage />
        }

        <FireButton buttonActive={isInTeam && isAlive && hasBullets} onClick={
          () => {
            setTriggerShot(triggerShot + 1)
          }
        } />
        <ScanButton onClick={
          () => { setScanMode(!scanMode) }
        } />

      </FullScreen>
    </ >
  ) : null;

  if (userState === null) {
    return loadingView;
  }

  if (userState.name === null) {
    return noNameView;
  }

  return playingView;
}
