import { useEffect, useRef, useCallback } from 'react';

import Webcam from "react-webcam";

import QRParser from './QRParser';

import screenfillStyles from './ScreenFillStyles.module.css';
import styles from './WebcamView.module.css';

const videoConstraints = {
    width: 1280,
    height: 720,
    facingMode: "environment"
};


function WebcamCapture({ trigger, isDead }) {

    // Get a reference to the webcam element
    const webcamRef = useRef(null);

    // Define a function that will take a shot (useCallback just avoids
    // redefining the function when renders happen)
    const capture = useCallback(
        () => {
            const imageSrc = webcamRef.current.getScreenshot();

            const query = JSON.stringify({
                photo: imageSrc
            });

            const requestOptions = {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: query
            };
            fetch('/api/submit_shot', requestOptions)
                .then(response => response.json())
                .then(data => console.log(`Response: ${data}`));


        },
        [webcamRef]
    );

    // Call the capture callback when the 'trigger' prop changes
    useEffect(() => {
        if (trigger)
            capture()
    }, [trigger, capture])

    return (
        <>
            <Webcam
                ref={webcamRef}
                audio={false}
                screenshotFormat="image/png"
                videoConstraints={videoConstraints}
                className={
                    screenfillStyles.screenFill
                    + " " + styles.webcamVideo
                    + (isDead ? " " + styles.dead : "")
                }
            />
            <QRParser
                webcamRef={webcamRef}
            />
        </>
    );
}


export default function WebcamView({
    trigger,
    isDead
}) {

    return <>
        <WebcamCapture trigger={trigger} isDead={isDead} />
    </>;
}
