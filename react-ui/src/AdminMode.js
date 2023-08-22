import React, { useCallback, useEffect, useRef, useState } from 'react';


function GamesView({ games }) {
    const newTeamInput = useRef(null);

    const addNewTeam = useCallback(() => { console.log(newTeamInput.current.value) }, [])


    return games.map((game, idx_game) => (
        <div key={idx_game}>
            <h2>Game {game.id}</h2>
            <h3>Users</h3>
            {
                game.users.map((user, idx_user) => (
                    <p key={idx_user}>User: {user.id} "{user.name}"</p>
                ))
            }
            <h3>Teams</h3>
            {
                game.teams.map((team, idx_team) => (
                    <p key={idx_team}>Team: {team.id}</p>
                ))
            }
            {
                <>
                    <input ref={newTeamInput}></input>
                    <button onClick={addNewTeam}>Add new team</button>
                </>
            }
        </div>
    ))
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


        </>
    );
}
