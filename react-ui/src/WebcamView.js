import { useEffect, useRef, useCallback, useState } from "react";

import Webcam from "react-webcam";

import QRParser from "./QRParser";

import screenfillStyles from "./ScreenFillStyles.module.css";
import styles from "./WebcamView.module.css";
import useScreenOrientation from "./useScreenOrientation";

const videoConstraints = {
  width: { ideal: 2048 },
  height: { ideal: 1080 },
  facingMode: "environment",
};

function WebcamCapture({ trigger, isDead }) {
  // Get a reference to the webcam element
  const webcamRef = useRef(null);

  const [hackyHideWebcam, setHackyHideWebcam] = useState(false);

  // Define a function that will take a shot (useCallback just avoids
  // redefining the function when renders happen)
  const capture = useCallback(() => {
    if (!webcamRef) return;

    const imageSrc = webcamRef.current.getScreenshot();

    const query = JSON.stringify({
      photo: imageSrc,
    });

    const requestOptions = {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: query,
    };
    fetch("/api/submit_shot", requestOptions)
      .then((response) => response.json())
      .then((data) => console.log(`Response: ${data}`));
  }, [webcamRef]);

  const orientation = useScreenOrientation();


  useEffect(() => {
    // Toggle the webcam on screen rotation to force a reload
    setHackyHideWebcam(true);
    const id = setTimeout(() => {
      setHackyHideWebcam(false);
    }, 500);

    return () => { clearTimeout(id); }
  }, [setHackyHideWebcam, orientation]);

  // Call the capture callback when the 'trigger' prop changes
  useEffect(() => {
    if (trigger) capture();
  }, [trigger, capture]);

  return (
    <>
      {!hackyHideWebcam ? (
        <Webcam
          ref={webcamRef}
          audio={false}
          screenshotFormat="image/jpg"
          videoConstraints={videoConstraints}
          forceScreenshotSourceSize
          height="360"
          width="640"
          className={
            screenfillStyles.screenFill +
            " " +
            styles.webcamVideo +
            (isDead ? " " + styles.dead : "")
          }
        />
      ) : null}
      <QRParser webcamRef={webcamRef} />
    </>
  );
}

export default function WebcamView({ trigger, isDead }) {
  return (
    <>
      <WebcamCapture trigger={trigger} isDead={isDead} />
    </>
  );
}
