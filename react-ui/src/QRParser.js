
import { useCallback, useEffect, useState } from 'react';
import useSound from 'use-sound';

import QrScanner from 'qr-scanner';

import { sendAPIRequest } from './utils';

import error from './error.mp3';


const timeout = 750;


const QRParser = ({ webcamRef }) => {
    const [qrEngine, setQrEngine] = useState(null);
    const [canvas, setCanvas] = useState(null);

    const [playError] = useSound(error);


    const scannedCallback = useCallback((data) => {
        sendAPIRequest("collect_item", {}, "POST", null, {
            data: data
        }).then(async response => {
            if (!response.ok) {
                console.log("Error happened in item collection")
                playError()
            }
        })
    }, [playError]);

    const capture = useCallback(() => {
        // Create persistent service worker and canvas for performance
        if (qrEngine === null) {
            QrScanner.createQrEngine(QrScanner.WORKER_PATH)
                .then((e) => {
                    setQrEngine(e)
                })

            setCanvas(document.createElement('canvas'));
        }

        if (!webcamRef || !webcamRef.current)
            return

        // Get an image from the webcam ref
        const imageSrc = webcamRef.current.getScreenshot();

        if (imageSrc === null)
            return

        // Scan it for QR codes
        QrScanner.scanImage(imageSrc,
            {
                qrEngine: qrEngine,
                canvas: canvas,
                returnDetailedScanResult: true
            }
        )
            .then(result => {
                scannedCallback(result.data)
            })
            .catch(error => null)

    }, [qrEngine, webcamRef, canvas, scannedCallback]);

    useEffect(() => {
        if (webcamRef === null)
            return

        const timerID = setInterval(capture, timeout);

        return () => { clearInterval(timerID) }
    }, [webcamRef, capture])


    return null;
};


export default QRParser;
