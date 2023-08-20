import React, { useCallback, useEffect, useState } from 'react';



export default function AdminMode() {

    const updatePanel = useCallback(
        () => {
            const requestOptions = {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            };
            fetch('/api/admin_list_games', requestOptions)
                .then(response => response.json())
                .then(data => {
                    console.log("Response");
                    console.dir(data);
                });
        },
        []
    );

    useEffect(updatePanel, [])

    return (
        <>
            <h1>Admin mode</h1>

            <p>Welcome to admin mode. I hope you're not a cheater...</p>


        </>
    );
}
