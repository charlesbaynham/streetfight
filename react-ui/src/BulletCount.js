import React, { useCallback, useState, useEffect } from 'react';


export default function BulletCount() {

    const [numBullets, setNumBullets] = useState(0);
    const [numHP, setNumHP] = useState(0);

    const update = useCallback(
        () => {
            const requestOptions = {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            };
            fetch('/api/user_info', requestOptions)
                .then(response => response.json())
                .then(data => {
                    setNumBullets(data.num_bullets)
                    setNumHP(data.hit_points)
                });
        },
        []
    );

    useEffect(update, [])

    return (
        <>
            <p>Bullets: {numBullets}</p>
            <p>HP: {numHP}</p>
        </>
    );
}
