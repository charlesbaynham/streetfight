import React, { useCallback, useEffect, useRef, useState } from 'react';
import { sendAPIRequest } from './utils';


function GamesView({ games }) {
    const [allUsers, setAllUsers] = useState([]);
    useEffect(() => {
        sendAPIRequest("get_users", null, "GET", (users) => { setAllUsers(users) })
    }, [])

    const newTeamInput = useRef(null);

    const addNewTeam = useCallback((game_id, team_name) => {
        const url = '/api/admin_create_team?' + new URLSearchParams({
            game_id: game_id,
            team_name: team_name,
        })
        const requestOptions = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        };
        fetch(url, requestOptions)
            .then(response => response.json())
            .then(data => {
                console.log(data)
            });
    }, [])

    const addUserToTeam = useCallback((user_id, team_id) => {
        sendAPIRequest("admin_add_user_to_team", {
            user_id: user_id,
            team_id: team_id,
        }, "POST")
    }, [])


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
            <ul>
                {

                    game.teams.map((team, idx_team) => (
                        <li key={idx_team}><em>{team.name}</em></li>
                    ))
                }
            </ul>

            {
                <>
                    <input ref={newTeamInput}></input>
                    <button onClick={() => { addNewTeam(game.id, newTeamInput.current.value) }}>Add new team</button>
                </>
            }

            <h3>Controls</h3>
            <label for="user">Add user</label>
            <select name="user" id="user_dropdown">
                {

                    allUsers.map((user, idx_user) => (
                        <option key={idx_user} value={user.id}>{
                            user.name ? user.name : user.id
                        }</option>
                    ))
                }
            </select>
            <label for="team">to team</label>
            <select name="team" id="team_dropdown">
                {

                    game.teams.map((team, idx_team) => (
                        <option key={idx_team} value={team.id}>{team.name}</option>
                    ))
                }
            </select>
            <button onClick={() => {
                addUserToTeam();
            }}>Submit</button>
        </div >
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
