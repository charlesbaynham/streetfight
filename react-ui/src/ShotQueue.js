
import React, { useCallback, useEffect, useState } from 'react';

export default function ShotQueue() {

    const [shots, setShots] = useState([]);
    const [numShots, setNumShots] = useState(0);

    const update = useCallback(
        () => {
            const requestOptions = {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            };
            fetch('/api/admin_get_shots', requestOptions)
                .then(response => response.json())
                .then(data => {
                    setNumShots(data.numInQueue);
                    setShots(data.shots);
                });
        },
        []
    );

    useEffect(update, [])

    return (
        <>
            <h1>Unchecked shots ({numShots} in queue):</h1>

            {shots.map((shot, idx) => (
                <>
                    <em>By {shot.user.id}</em>
                    <img src={shot.image_base64} key={idx} />
                </>
            ))}
        </>
    );
}
