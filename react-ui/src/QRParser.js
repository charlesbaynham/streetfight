



import QrScanner from 'qr-scanner';
import { useCallback, useEffect, useState } from 'react';


const timeout = 500;


const QRParser = ({ webcamRef }) => {
    const [qrEngine, setQrEngine] = useState(null);
    const [canvas, setCanvas] = useState(null);

    const capture = useCallback(() => {
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
                console.log(result)
            })
            .catch(error => console.log(error || 'No QR code found.'))

    }, [qrEngine, webcamRef, canvas]);

    useEffect(() => {
        if (webcamRef === null)
            return

        const timerID = setInterval(capture, timeout);

        return () => { clearInterval(timerID) }
    }, [webcamRef, capture])


    return null;
};


export default QRParser;