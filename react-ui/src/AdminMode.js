import React, { useCallback, useEffect, useState } from 'react';



function GamesView({ games }) {
    return games.map((game, idx_game) => (
        <>
            <h2 key={idx_game}>Game {game.id}</h2>
            {
                game.users.map((user, idx_user) => (
                    <p key={idx_user}>User: {user.id} "{user.name}"</p>
                ))
            }
            {
                game.teams.map((team, idx_team) => (
                    <p key={idx_team}>Team: {team.id}</p>
                ))
            }
        </>
    ))
}





function ShotQueue() {

    const [shots, setShots] = useState([]);

    const update = useCallback(
        () => {
            const requestOptions = {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            };
            fetch('/api/admin_get_shots', requestOptions)
                .then(response => response.json())
                .then(data => {
                    console.log("Response");
                    console.dir(data);
                    setShots(data);
                });
        },
        []
    );

    useEffect(update, [])

    return (
        <>
            <h1>Unchecked shots:</h1>

            {shots.map((shot, idx) => (
                <>
                    <em>By {shot.user.id}</em>
                    <img src={shot.image_base64} key={idx} />
                </>
            ))}
        </>
    );
}



export default function AdminMode() {

    const [games, setGames] = useState([]);

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
                    setGames(data);
                });
        },
        []
    );

    useEffect(updatePanel, [])

    return (
        <>
            <h1>Admin mode</h1>

            <p>Welcome to admin mode. I hope you're not a cheater...</p>

            <GamesView games={games} />

            <ShotQueue />
        </>
    );
}
