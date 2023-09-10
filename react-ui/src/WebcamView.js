import { useEffect, useRef, useCallback } from 'react';

import Webcam from "react-webcam";
import { SCREEN_FILL_STYLES } from './utils';


const videoConstraints = {
    width: 1280,
    height: 720,
    facingMode: "environment"
};

function WebcamCapture({ trigger }) {

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
            console.log(`query = ${query}`)

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

    const check_for_qr = useCallback(
        () => {
            const imageSrc = webcamRef.current.getScreenshot();
            const code = jsQR(imageSrc, videoConstraints.width, videoConstraints.height);

            if (true) {
                console.log("Found QR code", code);
            }
        }
        , [webcamRef]);

    useEffect(() => {
        const id = setTimeout(() => {
            console.log("Scanning...");
            check_for_qr();
        }, 1000);
        return () => { clearTimeout(id); }
    }, []);

    // Call the capture callback when the 'trigger' prop changes
    useEffect(() => {
        if (trigger)
            capture()
    }, [trigger, capture])

    return (
        <Webcam
            ref={webcamRef}
            audio={false}
            screenshotFormat="image/png"
            videoConstraints={videoConstraints}
            style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "cover" })}
        />
    );
}


export default function WebcamView({
    trigger
}) {

    return <>

        <WebcamCapture trigger={trigger} />
    </>;
}
