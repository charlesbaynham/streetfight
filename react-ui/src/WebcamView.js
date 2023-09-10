import { useEffect, useRef, useCallback } from 'react';

import useSound from 'use-sound';
import Webcam from "react-webcam";

import QRParser from './QRParser';

import { SCREEN_FILL_STYLES } from './utils';
import bang from './bang.mp3';


const videoConstraints = {
    width: 1280,
    height: 720,
    facingMode: "environment"
};


function WebcamCapture({ trigger }) {

    // Get a reference to the webcam element
    const webcamRef = useRef(null);

    const [playBang] = useSound(bang);

    // Define a function that will take a shot (useCallback just avoids
    // redefining the function when renders happen)
    const capture = useCallback(
        () => {
            playBang();
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
        [webcamRef, playBang]
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
                style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "cover" })}
            />
            <QRParser
                webcamRef={webcamRef}
            />
        </>
    );
}


export default function WebcamView({
    trigger
}) {

    return <>
        <WebcamCapture trigger={trigger} />
    </>;
}
