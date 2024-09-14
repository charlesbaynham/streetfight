import { useCallback, useEffect, useState } from "react";
import useSound from "use-sound";

import QrScanner from "qr-scanner";

import { sendAPIRequest } from "./utils";

import error from "./error.mp3";
import BlankScreen from "./BlankScreen";

const timeout = 1000;

var qrEngine = null;
var canvas = null;

async function capture(webcamRef, scannedCallback) {
  // Create persistent service worker and canvas for performance
  if (qrEngine === null) {
    QrScanner.createQrEngine().then((e) => {
      qrEngine = e;
      canvas = document.createElement("canvas");
    });
    return;
  }

  if (!webcamRef.current) return;

  // Get an image from the webcam ref
  const imageSrc = webcamRef.current.getScreenshot();

  if (imageSrc === null) return;

  // Scan it for QR codes
  return QrScanner.scanImage(imageSrc, {
    qrEngine: qrEngine,
    canvas: canvas,
    returnDetailedScanResult: true,
  })
    .then((result) => {
      scannedCallback(result.data);
    })
    .catch((_) => null);
}

const QRParser = ({ webcamRef }) => {
  const [lastScanData, setLastScanData] = useState(null);
  const [lastScanTime, setLastScanTime] = useState(null);

  const [playError] = useSound(error);

  const [showBlankScreen, setShowBlankScreen] = useState(false);
  const [colorBlankScreen, setColorBlankScreen] = useState("red");

  const flashTheScreen = useCallback((color) => {
    setColorBlankScreen(color);
    setShowBlankScreen(true);
    const timer_id = setTimeout(() => {
      setShowBlankScreen(false);
    }, 1000);
    return timer_id;
  }, [setShowBlankScreen, setColorBlankScreen])

  const scannedCallback = useCallback(
    (data) => {
      // Check that we haven't submitted this scan recently
      if (
        lastScanData &&
        lastScanTime &&
        data === lastScanData &&
        Date.now() - lastScanTime < 5000
      )
        return;

      // Store the time and data of this scan so that we can avoid resubmitting it
      setLastScanData(data);
      setLastScanTime(Date.now());


      // Submit the QR code to the API
      sendAPIRequest("collect_item", {}, "POST", null, {
        data: data,
      }).then(async (response) => {
        // Play an error sound if the API rejects us with a forbidden error
        // We might also get 404 errors for invalid QR codes - ignore these because the QR scanner occasionally misfires
        // Success sounds will be handled by the state updating
        if (response.status === 403) {
          flashTheScreen("red");
          playError();
        } else {
          // flashTheScreen("green");
        }
      });
    },
    [playError, lastScanData, lastScanTime, flashTheScreen],
  );

  // Trigger a scan when triggerScan changes. After the scan completes, queue another one
  const [triggerScan, setTriggerScan] = useState(0);
  useEffect(() => {
    if (triggerScan === 0) return;

    capture(webcamRef, scannedCallback).then(() => {
      setTimeout(() => {
        setTriggerScan(triggerScan + 1);
      }, timeout);
    });
  }, [triggerScan, setTriggerScan, scannedCallback, webcamRef]);

  //  Schedule the first scan once we have a webcamRef
  useEffect(() => {
    if (webcamRef === null) return;

    const timerID = setTimeout(() => {
      setTriggerScan(1);
    }, timeout);

    return () => {
      clearInterval(timerID);
    };
  }, [webcamRef]);

  return (
    <BlankScreen
      appear={showBlankScreen}
      color={colorBlankScreen}
      time_to_appear={0.3}
      time_to_show={0.7}
      time_to_disappear={3.0}
    />
  );
};

export default QRParser;
