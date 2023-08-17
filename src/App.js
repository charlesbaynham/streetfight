import React, { useCallback, useState } from 'react';

import './App.css';

import CrossHair from './Crosshair';
import { FullScreen, useFullScreenHandle } from "react-full-screen";

export default function App() {

  const handle = useFullScreenHandle();
  const [isFullscreen, setIsFullscreen] = useState(false);

  const reportChange = useCallback((state, _) => {
    setIsFullscreen(state);
  }, [handle]);

  return (
    <div>
      <button onClick={handle.enter}>
        Click here to start
      </button>

      <FullScreen handle={handle} onChange={reportChange}>
        {isFullscreen ? <CrossHair /> : null}
      </FullScreen>
    </div>
  );



  
}
