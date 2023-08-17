import React from 'react';

import './App.css';

import CrossHair from './Crosshair';
import { FullScreen, useFullScreenHandle } from "react-full-screen";

export default function App() {

  const handle = useFullScreenHandle();

  return (
    <div>
      <button onClick={handle.enter}>
        Enter fullscreen
      </button>

      <FullScreen handle={handle}>
        <p>Any fullscreen content here</p>
        {/* <CrossHair /> */}
      </FullScreen>
    </div>
  );



  
}
