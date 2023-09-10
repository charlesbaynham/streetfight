

import Webcam from 'react-webcam';

import { useRef } from 'react';

import QRParser from './QRParser';


const videoConstraints = {
    width: 1280,
    height: 720,
    facingMode: "environment"
};



const TestWebcamQR = () => {

    const webcamRef = useRef(null);

    return <>
        <Webcam
            ref={webcamRef}
            audio={false}
            screenshotFormat="image/png"
            videoConstraints={videoConstraints}
        />
        <QRParser webcamRef={webcamRef} />
    </>
        ;
};


export default TestWebcamQR;