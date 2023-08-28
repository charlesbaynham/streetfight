import React, { useCallback, useEffect, useState } from 'react';

import { FullScreen, useFullScreenHandle } from "react-full-screen";

import CrossHair from './Crosshair';
import FireButton from './FireButton';
import ScanButton from './ScanButton';
import BulletCount from './BulletCount';


export default function UserMode() {

  const handle = useFullScreenHandle();
  const [isFullscreen, setIsFullscreen] = useState(false);

  const [scanMode, setScanMode] = useState(false);

  const [userState, setUserState] = useState(null);

  const updateUserState = useCallback(() => {
    const url = '/api/user_info';
    const requestOptions = {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    };
    fetch(url, requestOptions)
      .then(response => response.json())
      .then(data => {
        setUserState(data)
      });
  }, [setUserState]);

  useEffect(updateUserState, []);

  const reportChange = useCallback((state, _) => {
    setIsFullscreen(state);
  }, []);

  const [triggerShot, setTriggerShot] = useState(0);


  return (
    <div>
      <button onClick={handle.enter}>
        Fullscreen
      </button>

      <FullScreen handle={handle} onChange={reportChange}>
        <BulletCount />

        <CrossHair trigger={triggerShot} scanMode={scanMode} />
        <FireButton onClick={
          () => {
            setTriggerShot(triggerShot + 1)
          }
        } />
        <ScanButton onClick={
          () => { setScanMode(!scanMode) }
        } />

      </FullScreen>

    </div >
  );
}
