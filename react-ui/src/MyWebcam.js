// Make my own replacement for react-webcam because it's broken on iOS. Argh!!

import { useEffect, useRef, useCallback } from "react";


const constraints = {
    audio: false,
    video: {
        facingMode: 'environment',
        width: { ideal: 2048 },
        height: { ideal: 1080 },
    }
};

export function MyWebcam({ trigger }) {
    const canvasRef = useRef(null);
    const videoRef = useRef(null);

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


    useEffect(() => {
        if (videoRef.current === null) {
            return;
        }

        const video = videoRef.current;

        async function init() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia(constraints);
                handleSuccess(stream);
            } catch (e) {
                console.error('navigator.getUserMedia error:', e);
            }
        }

        function handleSuccess(stream) {
            video.srcObject = stream;
        }

        init();
    }, [canvasRef, videoRef, capture]);

    return (
        <>
            <video
                autoplay="autoplay"
                playsinline
                muted  // Needed for autoplay
                width="640"
                height="480"
                ref={videoRef}
            ></video>

            <canvas
                ref={canvasRef}
                style={{ display: "none" }}
            ></canvas>
        </>
    );
}
