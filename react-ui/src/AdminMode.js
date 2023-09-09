import React, { useCallback, useEffect, useRef, useState } from 'react';

import { sendAPIRequest } from './utils';
import NewItems from './NewItems';

function GameView({ game }) {
    return <>
        <h2>Game {game.id}</h2>

        <h3>Teams</h3>

        <TeamsView teams={game.teams} />

        <h3>Controls</h3>

        <CreateNewTeam game_id={game} />
        <br />
        <AddUserToTeam teams={game.teams} />
    </>
}

function UserControls({ user }) {

    const give_n_health = useCallback((n) => {
        sendAPIRequest("admin_give_hp", {
            user_id: user.id,
            num: n,
        }, "POST")
    }, [user.id])

    const give_n_ammo = useCallback((n) => {
        sendAPIRequest("admin_give_ammo", {
            user_id: user.id,
            num: n,
        }, "POST")
    }, [user.id])

    return <li>
        {user.name} ({user.hit_points}❤️  {user.num_bullets}A)

        <button onClick={() => { give_n_health(+1) }}>+❤️</button>
        <button onClick={() => { give_n_health(-1) }}>-❤️</button>

        <button onClick={() => { give_n_ammo(+1) }}>+A</button>
        <button onClick={() => { give_n_ammo(-1) }}>-A</button>
    </li>
}

function TeamsView({ teams }) {
    return teams.map((team, idx_team) => (
        <div key={idx_team}>
            <h4>{team.name}</h4>

            <ul>
                {
                    team.users.map(
                        (user, idx_user) => <UserControls key={idx_user} user={user} />
                    )
                }
            </ul>
        </div>
    ));
}

function CreateNewTeam({ game_id }) {
    const addNewTeam = useCallback((game_id, team_name) => {
        sendAPIRequest("admin_create_team", {
            game_id: game_id,
            team_name: team_name,
        }, "POST")
    }, [])

    const newTeamInput = useRef(null);

    return <>
        <input ref={newTeamInput}></input>
        <button onClick={() => { addNewTeam(game_id, newTeamInput.current.value) }}>Add new team</button>
    </>

}


function AddUserToTeam({ teams }) {
    const addUserToTeam = useCallback((user_id, team_id) => {
        sendAPIRequest("admin_add_user_to_team", {
            item_type: user_id,
            team_id: team_id,
        }, "POST")
    }, [])

    const [allUsers, setAllUsers] = useState([]);

    const ref_add_user_to_team_team = useRef(null);
    const ref_add_user_to_team_user = useRef(null);

    useEffect(() => {
        sendAPIRequest("get_users", {}, "GET", (users) => { setAllUsers(users) })
    }, [])

    return <>
        <label htmlFor="user">Add user</label>
        <select name="user" id="user_dropdown" ref={ref_add_user_to_team_user}>
            {
                allUsers.map((user, idx_user) => (
                    <option key={idx_user} value={user.id}>{
                        user.name ? user.name : user.id
                    }</option>
                ))
            }
        </select>
        <label htmlFor="team">to team</label>
        <select name="team" id="team_dropdown" ref={ref_add_user_to_team_team}>
            {
                teams.map((team, idx_team) => (
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
    </>
}

function AllGamesView({ games }) {
    return games.map((game, idx_game) => (
        <div key={idx_game}>
            <GameView game={game} />
        </div >
    ))
}


export default function AdminMode() {

    const [games, setGames] = useState([]);

    const updatePanel = useCallback(
        () => {
            sendAPIRequest("admin_list_games", null, "GET", (data) => { setGames(data) })
        }, []
    );

    useEffect(updatePanel, [])

    return (
        <>
            <h1>Admin mode</h1>

            <p>Welcome to admin mode. I hope you're not a cheater...</p>

            <AllGamesView games={games} />

            <NewItems />
        </>
    );
}
