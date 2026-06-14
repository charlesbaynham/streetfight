// Make my own replacement for react-webcam because it's broken on iOS. Argh!!

import {
  useEffect,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react";
import useScreenOrientation from "./useScreenOrientation";

const constraints = {
  audio: false,
  video: {
    facingMode: "environment",
    width: { ideal: 2048 },
    height: { ideal: 1080 },
  },
};

export const MyWebcam = forwardRef(
  ({ trigger, className = "" }, refFromParent) => {
    const canvasRef = useRef(null);
    const videoRef = useRef(null);

    const mediaStream = useRef(null);

    // Return the current frame as a base64-encoded image
    const capture = useCallback(() => {
      if (videoRef.current === null || canvasRef.current === null) {
        return;
      }
      const video = videoRef.current;
      const canvas = canvasRef.current;

      let w = video.videoWidth;
      let h = video.videoHeight;
      canvas.width = w;
      canvas.height = h;

      let ctx = canvas.getContext("2d");

      ctx.drawImage(video, 0, 0, w, h);

      const imageSrc = canvas.toDataURL("image/jpeg");

      return imageSrc;
    }, [videoRef, canvasRef]);

    // Take a shot and upload it when trigger changes
    const captureAndUpload = useCallback(() => {
      const imageSrc = capture();
      const query = JSON.stringify({
        photo: imageSrc,
      });

      const requestOptions = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: query,
      };
      fetch("/api/submit_shot", requestOptions)
        .then((response) => response.json())
        .then((data) => console.log(`Response: ${data}`));
    }, [capture]);

    // Expose the capture function to the parent component
    useImperativeHandle(refFromParent, () => ({
      capture: capture,
    }));

    // Trigger the captureAndUpload function when `trigger` changes
    useEffect(() => {
      if (trigger) captureAndUpload();
    }, [trigger, captureAndUpload]);

    // Guard against overlapping startCamera calls (e.g. rapid hidden<->visible
    // bursts during mobile app-switching) which would acquire duplicate streams
    const isStarting = useRef(false);

    // Start the camera and bind it to the <video> element
    const startCamera = useCallback(async () => {
      const video = videoRef.current;

      if (isStarting.current || mediaStream.current) return;
      isStarting.current = true;

      try {
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = stream;
        await video.play(); // This line is critical for making the camera resume from standby in Safari, and wasting an entire Saturday
        mediaStream.current = stream;
      } catch (e) {
        console.error("navigator.getUserMedia error:", e);
      } finally {
        isStarting.current = false;
      }
    }, []);

    // Stop the camera
    const stopCamera = useCallback(() => {
      if (mediaStream.current) {
        mediaStream.current.getTracks().forEach((track) => track.stop());
        mediaStream.current = null;
      }
    }, [mediaStream]);

    // Connect the webcam to the <video> element on startup
    useEffect(() => {
      if (videoRef.current === null) {
        return;
      }

      startCamera();

      return () => {
        // Close down the camera streams when the component is unmounted
        stopCamera();
      };
    }, [canvasRef, videoRef, capture, startCamera, stopCamera]);

    // Stop the camera while the app is backgrounded (saves battery on all
    // platforms), and resume it when the app becomes visible again. The
    // stop-then-start on resume also preserves the documented Safari fix where
    // the camera needs reinitialising to come back from standby.
    useEffect(() => {
      const handleVisibilityChange = () => {
        if (document.visibilityState === "hidden") {
          stopCamera();
        } else {
          stopCamera();
          startCamera();
        }
      };
      document.addEventListener("visibilitychange", handleVisibilityChange);
      return () =>
        document.removeEventListener(
          "visibilitychange",
          handleVisibilityChange,
        );
    }, [startCamera, stopCamera]);

    // Bugfix for Firefox: Reinitialize the camera when the screen orientation changes
    // TODO: this isn't enough - I need to also rotate the camera apparently. See src for react-webcam I guess, or just don't bother
    // const orientation = useScreenOrientation();
    // useEffect(() => {
    //     if (!firefox) return;
    //     if (mediaStream.current) {
    //         stopCamera();
    //         startCamera();
    //     }
    // }, [orientation, mediaStream, startCamera, stopCamera]);

    return (
      <div className={className}>
        <video
          playsInline
          muted // Needed for autoplay
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          ref={videoRef}
        ></video>

        <canvas ref={canvasRef} style={{ display: "none" }}></canvas>
      </div>
    );
  },
);
