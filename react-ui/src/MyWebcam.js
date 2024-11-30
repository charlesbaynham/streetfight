// Make my own replacement for react-webcam because it's broken on iOS. Argh!!

import { useEffect, useRef, useCallback, useState } from "react";
import { requestWebcamAccess } from "./utils";


const constraints = {
    audio: false,
    video: {
        facingMode: 'environment',
        width: { ideal: 2048 },
        height: { ideal: 1080 },
    }
};

export function MyWebcam({ trigger, className = "" }) {
    const canvasRef = useRef(null);
    const videoRef = useRef(null);
    const emergencyRef = useRef(null);  // FIXME

    const [mediaStream, setMediaStream] = useState(null);

    // Define a function that will take a shot and upload it to the server
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

        let ctx = canvas.getContext('2d');

        ctx.drawImage(video, 0, 0, w, h);

        const imageSrc = canvas.toDataURL("image/jpeg");

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
    }, []);

    // Trigger the capture function when `trigger` changes
    useEffect(() => {
        if (trigger)
            capture();
    }, [trigger, capture]);

    // Start the camera and bind it to the <video> element
    const startCamera = useCallback(async () => {
        const video = videoRef.current;

        try {
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            video.srcObject = stream;
            video.play();  // This line is critical for making the camera resume from standby in Safari, and wasting an entire Saturday
            setMediaStream(stream);

        } catch (e) {
            console.error('navigator.getUserMedia error:', e);
        }
    }, []);

    // Stop the camera
    const stopCamera = useCallback(() => {
        if (mediaStream) {
            mediaStream.getTracks().forEach(track => track.stop());
            setMediaStream(null);
        }
    }, [mediaStream, setMediaStream]);

    // Connect the webcam to the <video> element on startup
    useEffect(() => {
        if (videoRef.current === null) {
            return;
        }

        startCamera();

        const video = videoRef.current;

        return () => {
            // Close down the camera streams when the component is unmounted
            stopCamera();
        }
    }, [canvasRef, videoRef, capture, startCamera]);

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            if (!mediaStream || mediaStream.getVideoTracks().length === 0 || videoRef.current.readyState === 0) {
                console.log("Reinitializing camera...");
                stopCamera();
                startCamera();
            }
        }
    });



    return (
        <div className={className}>
            <video
                playsinline
                muted  // Needed for autoplay
                style={{ width: "100%", height: "100%", objectFit: "cover" }}

                ref={videoRef}
            ></video>

            <canvas
                ref={canvasRef}
                style={{ display: "none" }}
            ></canvas>

            <button
                ref={emergencyRef}
                style={{ position: "absolute", top: "50%", right: 0, zIndex: 100000 }}
                onClick={() => {
                    videoRef.current?.srcObject?.getTracks().forEach(track => track.stop());
                    videoRef.current.srcObject = null;

                    requestWebcamAccess();

                    setTimeout(startCamera, 1000);
                    // Please, for the love of god, FIXME
                }}
            >ARRRRRRGGGHHH</button>  {/* FIXME */}

            <p
                style={{ position: "absolute", top: "50%", right: 0, zIndex: 100000 }}
            >
                videoRef: {String(videoRef.current)}
                <br />
                srcObject: {String(videoRef.current?.srcObject)}
            </p>
        </div >
    );
}
