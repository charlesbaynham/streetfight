

import Webcam from 'react-webcam';

import QrScanner from 'qr-scanner';
import { useCallback, useRef } from 'react';


const videoConstraints = {
    width: 1280,
    height: 720,
    facingMode: "environment"
};


const TestWebcamQR = () => {
    const webcamRef = useRef(null);

    const capture = useCallback(() => {
        const imageSrc = webcamRef.current.getScreenshot();

        QrScanner.scanImage(imageSrc)
            .then(result => console.log(result))
            .catch(error => console.log(error || 'No QR code found.'));
    }, []);


    return <>
        <Webcam
            ref={webcamRef}
            audio={false}
            screenshotFormat="image/png"
            videoConstraints={videoConstraints}
        />
        <button onClick={capture}>Capture</button>
    </>
};


export default TestWebcamQR;