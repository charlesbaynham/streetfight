import React from 'react';


export default function BulletCount({ user }) {
    return (
        <>
            <p>Bullets: {user.num_bullets}</p>
            <p>HP: {user.hit_points}</p>
        </>
    );
}
