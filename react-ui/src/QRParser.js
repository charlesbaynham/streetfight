
import { useCallback, useEffect, useState } from 'react';
import useSound from 'use-sound';

import QrScanner from 'qr-scanner';

import { sendAPIRequest } from './utils';

import error from './error.mp3';
import BlankScreen from './BlankScreen';


const timeout = 750;

var qrEngine = null;
var canvas = null;


async function capture(webcamRef, scannedCallback) {
    console.log("scanning")
    // Create persistent service worker and canvas for performance
    if (qrEngine === null) {
        QrScanner.createQrEngine(QrScanner.WORKER_PATH)
            .then((e) => {
                qrEngine = e;
                canvas = document.createElement('canvas');
            })
        return
    }

    if (!webcamRef.current)
        return

    // Get an image from the webcam ref
    const imageSrc = webcamRef.current.getScreenshot();

    if (imageSrc === null)
        return

    // Scan it for QR codes
    return QrScanner.scanImage(imageSrc,
        {
            qrEngine: qrEngine,
            canvas: canvas,
            returnDetailedScanResult: true
        }
    )
        .then(result => {
            scannedCallback(result.data)
        })
        .catch(_ => null)
}


const QRParser = ({ webcamRef }) => {
    const [lastScanData, setLastScanData] = useState(null);
    const [lastScanTime, setLastScanTime] = useState(null);

    const [playError] = useSound(error);
    const [showBlankScreen, setShowBlankScreen] = useState(false);

    const scannedCallback = useCallback((data) => {
        // Check that we haven't submitted this scan recently
        if (lastScanData && lastScanTime && data === lastScanData && (Date.now() - lastScanTime) < 5000)
            return

        // Store the time and data of this scan so that we can avoid resubmitting it
        setLastScanData(data)
        setLastScanTime(Date.now())

        // Flash the screen
        setShowBlankScreen(true)
        const timer_id = setTimeout(() => { setShowBlankScreen(false) }, 100)

        // Submit the QR code to the API
        sendAPIRequest("collect_item", {}, "POST", null, {
            data: data
        }).then(async response => {
            // Play an error sound if the API rejects us with a forbidden error
            // We might also get 404 errors for invalid QR codes - ignore these because the QR scanner occasionally misfires
            // Success sounds will be handled by the state updating
            if (response.status === 403) {
                playError()
            }
        })

        return () => { clearTimeout(timer_id) }
    }, [playError, lastScanData, lastScanTime]);

    // Trigger a scan when triggerScan changes. After the scan completes, queue another one
    const [triggerScan, setTriggerScan] = useState(0);
    useEffect(() => {
        if (triggerScan === 0)
            return

        console.log("Setting next")

        capture(webcamRef, scannedCallback).then(() => {
            setTimeout(() => {
                setTriggerScan(triggerScan + 1)
            }, timeout)
        })

    }, [triggerScan, setTriggerScan]);

    //  Schedule the first scan once we have a webcamRef
    useEffect(() => {
        if (webcamRef === null)
            return

        const timerID = setTimeout(() => { setTriggerScan(triggerScan + 1) }, timeout);

        return () => { clearInterval(timerID) }
    }, [webcamRef])


    return <BlankScreen
        appear={showBlankScreen}
        time_to_appear={0.1}
        time_to_show={0.2}
        time_to_disappear={1.0}
    />;
};


export default QRParser;
