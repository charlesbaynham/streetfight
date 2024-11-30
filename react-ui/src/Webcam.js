// Make my own replacement for react-webcam because it's broken on iOS. Argh!!

import { useEffect, useRef, useCallback, useState } from "react";
import useScreenOrientation from "./useScreenOrientation";


const videoConstraints = {
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

        console.log(canvas.toDataURL("image/jpeg"));


        // const query = JSON.stringify({
        //     photo: imageSrc,
        // });

        // const requestOptions = {
        //     method: "POST",
        //     headers: { "Content-Type": "application/json" },
        //     body: query,
        // };
        // fetch("/api/submit_shot", requestOptions)
        //     .then((response) => response.json())
        //     .then((data) => console.log(`Response: ${data}`));
    }, []);


    useEffect(() => {
        if (videoRef.current === null || canvasRef.current === null || captureButtonRef.current === null) {
            return;
        }

        const video = videoRef.current;
        const canvas = canvasRef.current;

        const constraints = {
            audio: false,
            video: true
        };

        async function init() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia(constraints);
                handleSuccess(stream);
            } catch (e) {
                console.error('navigator.getUserMedia error:', e);
            }
        }


        function handleSuccess(stream) {
            const videoTracks = stream.getVideoTracks();
            console.log('Got stream with constraints:', constraints);
            console.log(`Using video device: ${videoTracks[0].label}`);
            window.stream = stream; // make variable available to browser console
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


            <label>Screenshot (base 64 dataURL)</label>
            <canvas id="canvas" width="640" height="480" ref={canvasRef}></canvas>

            <button ref={captureButtonRef}>Capture!</button>
        </>
    );
}
