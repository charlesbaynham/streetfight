import React, { useCallback, useState } from 'react';

import './App.css';

import { FullScreen, useFullScreenHandle } from "react-full-screen";

import CrossHair from './Crosshair';
import FireButton from './FireButton';
import ScanButton from './ScanButton';

const override = false;

export default function App() {

  const handle = useFullScreenHandle();
  const [isFullscreen, setIsFullscreen] = useState(false);

  const [scanMode, setScanMode] = useState(false);

  const reportChange = useCallback((state, _) => {
    setIsFullscreen(state);
  }, []);

  return (
    <div>
      <button onClick={handle.enter}>
        Click here to start
      </button>

      <FullScreen handle={handle} onChange={reportChange}>
        {isFullscreen | override ? ( <>
          <CrossHair scanMode={scanMode} />
          <FireButton onClick={
            () => { setScanMode(false) }
          } />
          <ScanButton onClick={
            () => { setScanMode(true) }
          } />
       </>
        ) : null}
      </FullScreen>


    </div>
  );




}
