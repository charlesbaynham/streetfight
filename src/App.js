import React, { useCallback, useState } from 'react';

import './App.css';

import { FullScreen, useFullScreenHandle } from "react-full-screen";

import CrossHair from './Crosshair';
import FireButton from './FireButton';
import ScanButton from './ScanButton';

const override = true;

export default function App() {

  const handle = useFullScreenHandle();
  const [isFullscreen, setIsFullscreen] = useState(false);

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
          <CrossHair />
          <FireButton />
          <ScanButton test="hrllo"/>
       </>
        ) : null}
      </FullScreen>

      
    </div>
  );



  
}
