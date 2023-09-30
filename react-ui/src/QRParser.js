
import { useCallback, useEffect, useState } from 'react';
import useSound from 'use-sound';

import QrScanner from 'qr-scanner';

import { sendAPIRequest } from './utils';

import error from './error.mp3';


const timeout = 750;


const QRParser = ({ webcamRef }) => {
    const [qrEngine, setQrEngine] = useState(null);
    const [canvas, setCanvas] = useState(null);

    const [lastScanData, setLastScanData] = useState(null);
    const [lastScanTime, setLastScanTime] = useState(null);

    const [playError] = useSound(error);


    const scannedCallback = useCallback((data) => {
        // Check that we haven't submitted this scan recently
        if (lastScanData && lastScanTime && data === lastScanData && (Date.now() - lastScanTime) < 5000)
            return

        // Store the time and data of this scan so that we can avoid resubmitting it
        setLastScanData(data)
        setLastScanTime(Date.now())

        // Submit the QR code to the API
        sendAPIRequest("collect_item", {}, "POST", null, {
            data: data
        }).then(async response => {
            // Play an error sound if the API rejects us
            // Success sounds will be handled by the state updating
            if (!response.ok) {
                playError()
            }
        })
    }, [playError, lastScanData, lastScanTime]);

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
