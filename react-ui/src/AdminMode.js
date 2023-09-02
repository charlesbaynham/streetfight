import React, { useCallback, useEffect, useRef, useState } from 'react';
import { sendAPIRequest } from './utils';


function GamesView({ games }) {
    const [allUsers, setAllUsers] = useState([]);
    useEffect(() => {
        sendAPIRequest("get_users", {}, "GET", (users) => { setAllUsers(users) })
    }, [])

    const newTeamInput = useRef(null);

    const addNewTeam = useCallback((game_id, team_name) => {
        sendAPIRequest("admin_create_team", {
            game_id: game_id,
            team_name: team_name,
        }, "POST")
    }, [])

    const addUserToTeam = useCallback((user_id, team_id) => {
        sendAPIRequest("admin_add_user_to_team", {
            user_id: user_id,
            team_id: team_id,
        }, "POST")
    }, [])

    const ref_add_user_to_team_team = useRef(null);
    const ref_add_user_to_team_user = useRef(null);


    return games.map((game, idx_game) => (
        <div key={idx_game}>
            <h2>Game {game.id}</h2>

            {
                game.teams.map((team, idx_team) => {

                    const list_of_users = team.users.map(
                        (user, idx_user) => (
                            <li key={idx_user}>{user.name}</li>
                        ));

                    return <div key={idx_team}>
                        <h3>Team: <em>{team.name}</em></h3>

                        <ul>
                            {list_of_users}
                        </ul>
                    </div>
                }
                )
            }

            {
                <>
                    <input ref={newTeamInput}></input>
                    <button onClick={() => { addNewTeam(game.id, newTeamInput.current.value) }}>Add new team</button>
                </>
            }

            <h3>Controls</h3>
            <label for="user">Add user</label>
            <select name="user" id="user_dropdown" ref={ref_add_user_to_team_user}>
                {

                    allUsers.map((user, idx_user) => (
                        <option key={idx_user} value={user.id}>{
                            user.name ? user.name : user.id
                        }</option>
                    ))
                }
            </select>
            <label for="team">to team</label>
            <select name="team" id="team_dropdown" ref={ref_add_user_to_team_team}>
                {

                    game.teams.map((team, idx_team) => (
                        <option key={idx_team} value={team.id}>{team.name}</option>
                    ))
                }
            </select>
            <button onClick={() => {
                addUserToTeam(
                    ref_add_user_to_team_user.current.value,
                    ref_add_user_to_team_team.current.value
                );
            }}>Submit</button>
        </div >
    ))
}


export default function AdminMode() {

    const [games, setGames] = useState([]);

    const updatePanel = useCallback(
        () => {
            return sendAPIRequest("admin_list_games", null, "GET", (data) => { setGames(data) })
        }, []
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
