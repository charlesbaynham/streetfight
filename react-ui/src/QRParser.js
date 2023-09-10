



import QrScanner from 'qr-scanner';
import { useCallback, useEffect, useState } from 'react';


const timeout = 2000;


const QRParser = ({ webcamRef }) => {
    const [qrEngine, setQrEngine] = useState(null);
    const [canvas, setCanvas] = useState(null);
    const [timerID, setTimerID] = useState(null);

    const capture = useCallback(() => {
        if (webcamRef === null)
            return

        // Create persistent service worker and canvas for performance
        if (qrEngine === null) {
            QrScanner.createQrEngine(QrScanner.WORKER_PATH)
                .then((e) => {
                    setQrEngine(e)
                })

            setCanvas(document.createElement('canvas'));
        }

        // Get an image from the webcam ref
        const imageSrc = webcamRef.current.getScreenshot();

        // Scan it for QR codes
        QrScanner.scanImage(imageSrc,
            {
                qrEngine: qrEngine,
                canvas: canvas,
                returnDetailedScanResult: true
            }
        )
            .then(result => {
                console.log(result)
            })
            .catch(error => console.log(error || 'No QR code found.'))
            .finally(() => {
                // Queue the next run
                setTimerID(setTimeout(capture, timeout));
            });

        // Return a cleanup function for dismount
        return (timerID) => {
            if (timerID !== null) {
                clearTimeout(timerID);
            }
        }
    }, [qrEngine, setQrEngine, webcamRef, canvas, timerID, setTimerID]);

    useEffect(capture, [webcamRef])


    return null;
};


export default QRParser;