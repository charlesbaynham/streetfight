// Make my own replacement for react-webcam because it's broken on iOS. Argh!!

import { useEffect, useRef, useCallback } from "react";



const videoConstraints = {
    audio: false,
    video: true,
    width: { ideal: 2048 },
    height: { ideal: 1080 },
    facingMode: "environment",
};

export function MyWebcam() {
    const canvasRef = useRef(null);
    const videoRef = useRef(null);
    const captureButtonRef = useRef(null);


    // Define a function that will take a shot (useCallback just avoids
    // redefining the function when renders happen)
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


    useEffect(() => {
        if (videoRef.current === null || captureButtonRef.current === null) {
            return;
        }

        const video = videoRef.current;



        async function init() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia(videoConstraints);
                handleSuccess(stream);
            } catch (e) {
                console.error('navigator.getUserMedia error:', e);
            }
        }

        function handleSuccess(stream) {
            video.srcObject = stream;
            captureButtonRef.current.onclick = capture;
        }

        init();
    }, [canvasRef, videoRef, captureButtonRef, capture]);

    return (
        <>
            <label>Video Stream</label>
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

            <button ref={captureButtonRef}>Capture!</button>
        </>
    );
}
