import { useEffect, useRef, useState } from "react";



import QRParser from "./QRParser";

import screenfillStyles from "./ScreenFillStyles.module.css";
import styles from "./WebcamView.module.css";
import useScreenOrientation from "./useScreenOrientation";
import { MyWebcam } from "./MyWebcam";



function WebcamCapture({ trigger, isDead }) {
  // Get a reference to the webcam element
  const webcamRef = useRef(null);

  const [hackyHideWebcam, setHackyHideWebcam] = useState(false);

  const orientation = useScreenOrientation();


  useEffect(() => {
    // Toggle the webcam on screen rotation to force a reload
    setHackyHideWebcam(true);
    const id = setTimeout(() => {
      setHackyHideWebcam(false);
    }, 500);

    return () => { clearTimeout(id); }
  }, [setHackyHideWebcam, orientation]);

  return (
    <>
      {!hackyHideWebcam ? (
        <MyWebcam
          ref={webcamRef}
          trigger={trigger}
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
