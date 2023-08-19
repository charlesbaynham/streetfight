import { useEffect } from 'react';
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
  // A slight abuse here - if the "trigger" variable changes to anything other than zero, take a screenshot
  useEffect(() => {
    if (trigger) {
      console.log("bing")
    }
  }, [trigger]);

  return (

  <Webcam
    audio={false}
    screenshotFormat="image/jpeg"
    videoConstraints={videoConstraints}
    style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "cover" })}
  >
    {({ getScreenshot }) => (
      <button
        style={{
          position: "absolute",
          left:"0",
          top:"10vh"
        }}
        onClick={() => {
          const imageSrc = getScreenshot()

          console.log(imageSrc)
        }}
      >
        Capture photo
      </button>
    )}
  </Webcam>
  )
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
