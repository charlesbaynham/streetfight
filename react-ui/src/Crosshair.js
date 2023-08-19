import { useEffect, useRef, useCallback } from 'react';
import crosshair from './crosshair.png';
import qr_guide from './qr_guide.png';

import Webcam from "react-webcam";


const SCREEN_FILL_STYLES = {
  position: "absolute",
  height: "100vh",
  width: "100vw",
  left: "0",
  top: "0"
};

const videoConstraints = {
  width: 1280,
  height: 720,
  facingMode: "environment"
};

function WebcamCapture({trigger}) {

  // Get a reference to the webcam element
  const webcamRef = useRef(null);
  
  // Define a function that will take a shot (useCallback just avoids
  // redefining the function when renders happen)
  const capture = useCallback(
    () => {
      const imageSrc = webcamRef.current.getScreenshot();
      console.log(imageSrc)
      // POST request using fetch inside useEffect React hook
      const requestOptions = {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: imageSrc
      };
      fetch('http://localhost:8000/api/submit_shot', requestOptions)
          .then(response => response.json())
          .then(data => console.log(data));
    },
    [webcamRef]
  );

  // Call the capture callback when the 'trigger' prop changes
  useEffect(() => {
    if (trigger) 
      capture()
  }, [trigger])

  return (
    <Webcam
      ref={webcamRef}
      audio={false}
      screenshotFormat="image/jpeg"
      videoConstraints={videoConstraints}
      style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "cover" })}
    />
  );
}

const CrosshairImage = () => (
  <img
    src={crosshair}
    style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "contain" })}
  />
);

const QRImage = () => (
  <img
    src={qr_guide}
    style={
      {
        position: "absolute",
        height: "50vh",
        width: "50vw",
        left: "25vw",
        top: "25vh"
      }
    }
  />
);

export default function CrossHair({
  scanMode, trigger
}) {

  return <>

    <WebcamCapture trigger={trigger} />
    {scanMode ?
      <QRImage />
      :
      <CrosshairImage />
    }


  </>;
}
