// The camera-as-QR-scanner loop, on its own so that both things that point a
// phone at a printed code can share it: the player's screen, which collects
// what it scans (QRParser.js), and the admin's code list, which registers it
// instead (AdminCodes.js). What varies between them is only what happens to
// the decoded string, so that is the argument.
//
// The scan rate, the persistent engine and canvas, and the refusal to scan
// while the app is backgrounded all came from QRParser and are unchanged.

import { useCallback, useEffect, useRef, useState } from "react";

import QrScanner from "qr-scanner";

// How often a frame is grabbed and decoded, and how long the same code is
// ignored for after it has been handled. Rescanning the card in your hand is
// how an admin checks it is on the list, so the suppression has to expire.
const SCAN_INTERVAL_MS = 1000;
const REPEAT_SUPPRESSION_MS = 5000;

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
  const imageSrc = webcamRef.current.capture();

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

export default function useQRScanLoop(webcamRef, onScan) {
  const [lastScanData, setLastScanData] = useState(null);
  const [lastScanTime, setLastScanTime] = useState(null);

  // Held in a ref, as MyWebcam holds its onCapture: the loop below would
  // otherwise restart - losing its place - every time a caller re-rendered
  // with a freshly built callback.
  const onScanRef = useRef(onScan);
  useEffect(() => {
    onScanRef.current = onScan;
  }, [onScan]);

  const scannedCallback = useCallback(
    (data) => {
      // Check that we haven't submitted this scan recently
      if (
        lastScanData &&
        lastScanTime &&
        data === lastScanData &&
        Date.now() - lastScanTime < REPEAT_SUPPRESSION_MS
      )
        return;

      // Store the time and data of this scan so that we can avoid resubmitting it
      setLastScanData(data);
      setLastScanTime(Date.now());

      onScanRef.current(data);
    },
    [lastScanData, lastScanTime],
  );

  // Trigger a scan when triggerScan changes. After the scan completes, queue another one
  const [triggerScan, setTriggerScan] = useState(0);
  useEffect(() => {
    if (triggerScan === 0) return;

    // Don't capture/scan while the app is backgrounded: the camera is stopped
    // and scanning would waste CPU/battery. The visibility effect below
    // restarts the loop when the app becomes visible again.
    if (document.hidden) return;

    let timerId;
    capture(webcamRef, scannedCallback).then(() => {
      timerId = setTimeout(() => {
        setTriggerScan((n) => n + 1);
      }, SCAN_INTERVAL_MS);
    });

    return () => clearTimeout(timerId);
  }, [triggerScan, setTriggerScan, scannedCallback, webcamRef]);

  // Resume the scan loop when the app becomes visible again after being paused
  useEffect(() => {
    const onVisible = () => {
      if (!document.hidden) setTriggerScan((n) => (n === 0 ? 0 : n + 1));
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  //  Schedule the first scan once we have a webcamRef
  useEffect(() => {
    if (webcamRef === null) return;

    const timerID = setTimeout(() => {
      setTriggerScan(1);
    }, SCAN_INTERVAL_MS);

    return () => {
      clearTimeout(timerID);
    };
  }, [webcamRef]);
}
