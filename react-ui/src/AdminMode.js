import React, { useCallback, useEffect, useRef, useState } from "react";

import { sendAPIRequest } from "./utils";
import NewItems from "./NewItems";
import UpdateListener, { UpdateSSEConnection } from "./UpdateListener";
import { MapViewAdmin } from "./MapView";
import CircleControl from "./CircleControl";

function GameView({ game }) {
  const setGameActive = useCallback(
    (state) => {
      sendAPIRequest(
        "admin_set_game_active",
        {
          game_id: game.id,
          active: state,
        },
        "POST"
      );
    },
    [game]
  );

  return (
    <>
      <h2>Game {game.id}</h2>

      <label>
        Game active: {game.active ? "true" : "false"}
        <br />
        <button
          onClick={() => {
            setGameActive(true);
          }}
        >
          Start
        </button>
        <button
          onClick={() => {
            setGameActive(false);
          }}
        >
          Pause
        </button>
      </label>

      <h3>Teams</h3>

      <TeamsView teams={game.teams} />

      <h3>Controls</h3>

      <CreateNewTeam game_id={game.id} />
      <br />
      <AddUserToTeam teams={game.teams} />
    </>
  );
}

function UserControls({ user }) {
  const set_health = useCallback(
    (n) => {
      sendAPIRequest(
        "admin_set_hp",
        {
          user_id: user.id,
          num: n,
        },
        "POST"
      );
    },
    [user.id]
  );

  const hit_user = useCallback(
    (n) => {
      sendAPIRequest(
        "admin_hit_user",
        {
          user_id: user.id,
          num: n,
        },
        "POST"
      );
    },
    [user.id]
  );

  const give_n_ammo = useCallback(
    (n) => {
      sendAPIRequest(
        "admin_give_ammo",
        {
          user_id: user.id,
          num: n,
        },
        "POST"
      );
    },
    [user.id]
  );

  return (
    <li>
      {user.name} {user.hit_points <= 0 ? <span>&#x1F480;</span> : null} (
      {user.hit_points}❤️ {user.num_bullets}A) Health:
      <button
        onClick={() => {
          set_health(0);
        }}
      >
        <span>&#x1F480; Kill &#x1F480;</span>
      </button>
      <button
        onClick={() => {
          hit_user(1);
        }}
      >
        <span>&#x1F480; Shoot &#x1F480;</span>
      </button>
      <button
        onClick={() => {
          set_health(1);
        }}
      >
        Revive
      </button>
      <button
        onClick={() => {
          set_health(1);
        }}
      >
        Lv. 0
      </button>
      <button
        onClick={() => {
          set_health(2);
        }}
      >
        Lv. 1
      </button>
      <button
        onClick={() => {
          set_health(3);
        }}
      >
        Lv. 2
      </button>
      <button
        onClick={() => {
          set_health(4);
        }}
      >
        Lv. 3
      </button>
      Ammo:
      <button
        onClick={() => {
          give_n_ammo(+1);
        }}
      >
        +A
      </button>
      <button
        onClick={() => {
          give_n_ammo(-1);
        }}
      >
        -A
      </button>
    </li>
  );
}

function TeamsView({ teams }) {
  return teams.map((team, idx_team) => (
    <div key={idx_team}>
      <h4>{team.name}</h4>

      <ul>
        {team.users.map((user, idx_user) => (
          <UserControls key={idx_user} user={user} />
        ))}
      </ul>
    </div>
  ));
}

function CreateNewTeam({ game_id }) {
  const addNewTeam = useCallback((game_id, team_name) => {
    sendAPIRequest(
      "admin_create_team",
      {
        game_id: game_id,
        team_name: team_name,
      },
      "POST"
    );
  }, []);

  const newTeamInput = useRef(null);

  return (
    <>
      <input ref={newTeamInput}></input>
      <button
        onClick={() => {
          addNewTeam(game_id, newTeamInput.current.value);
        }}
      >
        Add new team
      </button>
    </>
  );
}

function AddUserToTeam({ teams }) {
  const addUserToTeam = useCallback((user_id, team_id) => {
    sendAPIRequest(
      "admin_add_user_to_team",
      {
        user_id: user_id,
        team_id: team_id,
      },
      "POST"
    );
  }, []);

  const [allUsers, setAllUsers] = useState([]);

  const ref_add_user_to_team_team = useRef(null);
  const ref_add_user_to_team_user = useRef(null);

  useEffect(() => {
    sendAPIRequest("get_users", {}, "GET", (users) => {
      setAllUsers(users);
    });
  }, []);

  return (
    <>
      <label htmlFor="user">Add user</label>
      <select name="user" id="user_dropdown" ref={ref_add_user_to_team_user}>
        {allUsers.map((user, idx_user) => (
          <option key={idx_user} value={user.id}>
            {user.name ? user.name : user.id}
          </option>
        ))}
      </select>
      <label htmlFor="team">to team</label>
      <select name="team" id="team_dropdown" ref={ref_add_user_to_team_team}>
        {teams.map((team, idx_team) => (
          <option key={idx_team} value={team.id}>
            {team.name}
          </option>
        ))}
      </select>
      <button
        onClick={() => {
          addUserToTeam(
            ref_add_user_to_team_user.current.value,
            ref_add_user_to_team_team.current.value
          );
        }}
      >
        Submit
      </button>
    </>
  );
}

function AllGamesView({ games }) {
  return games.map((game, idx_game) => (
    <div key={idx_game}>
      <GameView game={game} />
    </div>
  ));
}

function UserRenaming() {
  const renameUser = useCallback((user_id, new_name) => {
    sendAPIRequest(
      "admin_set_user_name",
      {
        user_id: user_id,
        name: new_name,
      },
      "POST"
    );
  }, []);

  const [users, setUsers] = useState([]);

  const ref_user = useRef(null);
  const ref_new_name = useRef(null);

  useEffect(() => {
    sendAPIRequest("get_users", {}, "GET", (users) => {
      setUsers(users);
    });
  }, []);

  return (
    <>
      <label htmlFor="user">Rename user</label>
      <select name="user" ref={ref_user}>
        {users.map((user, idx_user) => (
          <option key={idx_user} value={user.id}>
            {user.name ? user.name : user.id}
          </option>
        ))}
      </select>
      <label htmlFor="newName">Name:</label>
      <input name="newName" ref={ref_new_name} />

      <button
        onClick={() => {
          renameUser(ref_user.current.value, ref_new_name.current.value);
        }}
      >
        Submit
      </button>
    </>
  );
}

export default function AdminMode() {
  const [games, setGames] = useState([]);
  const [knownTickerHash, setKnownTickerHash] = useState(0);

  const updatePanel = useCallback(() => {
    sendAPIRequest("admin_list_games", null, "GET", (data) => {
      setGames(data);
    });
  }, []);

  useEffect(updatePanel, [updatePanel, knownTickerHash]);

  return (
    <>
      <UpdateSSEConnection endpoint="sse_admin_updates" />
      <UpdateListener
        update_type="admin"
        callback={() => {
          console.log(`Updating knownTickerHash to ${knownTickerHash + 1}`);
          setKnownTickerHash(knownTickerHash + 1);
        }}
      />

      <h1>Admin mode</h1>

      <p>Welcome to admin mode. I hope you're not a cheater...</p>

      <AllGamesView games={games} />

      <NewItems />

      <UserRenaming />

      <MapViewAdmin />

      <h2>Circle Control</h2>
      {games.length > 0 ? (
        <CircleControl game_id={games[0].id} />
      ) : (
        "Loading..."
      )}
    </>
  );
}
