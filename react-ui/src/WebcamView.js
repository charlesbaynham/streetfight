import { useRef } from "react";

import QRParser from "./QRParser";

import screenfillStyles from "./ScreenFillStyles.module.css";
import styles from "./WebcamView.module.css";

import { MyWebcam } from "./MyWebcam";

export default function WebcamView({ trigger, isDead }) {
  // Get a reference to the webcam element
  const webcamRef = useRef(null);

  return (
    <>
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
      <QRParser webcamRef={webcamRef} />
    </>
  );
}
