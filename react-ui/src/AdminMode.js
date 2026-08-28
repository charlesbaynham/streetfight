import React, { useCallback, useEffect, useRef, useState } from "react";

import { Col, Row } from "react-bootstrap";

import { sendAPIRequest } from "./utils";
import { AdminPage, adminDownload, adminPost } from "./AdminCommon";
import NewItems from "./NewItems";
import JoinQRCodes from "./JoinQRCodes";
import UpdateListener from "./UpdateListener";
import { MapViewAdmin } from "./MapView";
import CircleControl from "./CircleControl";
import TickerView from "./TickerView";

// Mirrors WEAPON_NAME_LOOKUP in backend/item_actions.py
const WEAPONS = {
  "No weapon": [0, 6],
  Pewster: [1, 6],
  "Tracka-Tracka": [2, 6],
  OMG: [3, 6],
  "Eat-a-bullet": [1, 1],
};

export function weaponName(user) {
  for (const [name, [damage, timeout]] of Object.entries(WEAPONS)) {
    if (user.shot_damage === damage && user.shot_timeout === timeout)
      return name;
  }
  return null;
}

// One player's in-game stats and the knobs to fiddle with them. Renaming and
// team assignment live in the global Players section instead.
function UserControls({ user }) {
  return (
    <li>
      <b>{user.name || user.id}</b>
      {user.hit_points <= 0 ? " \u{1F480}" : ""} &mdash; {user.hit_points} HP,{" "}
      {user.num_bullets} ammo,{" "}
      {weaponName(user) || `${user.shot_damage} dmg / ${user.shot_timeout}s`}
      <br />
      HP:{" "}
      <button
        onClick={() => adminPost("admin_set_hp", { user_id: user.id, num: 0 })}
      >
        Kill
      </button>
      <button
        onClick={() =>
          adminPost("admin_hit_user", { user_id: user.id, num: 1 })
        }
      >
        Hit (-1)
      </button>
      {[1, 2, 3, 4].map((n) => (
        <button
          key={n}
          onClick={() =>
            adminPost("admin_set_hp", { user_id: user.id, num: n })
          }
        >
          {n}
        </button>
      ))}{" "}
      Ammo:{" "}
      <button
        onClick={() =>
          adminPost("admin_give_ammo", { user_id: user.id, num: 1 })
        }
      >
        +1
      </button>
      <button
        onClick={() =>
          adminPost("admin_give_ammo", { user_id: user.id, num: -1 })
        }
      >
        -1
      </button>{" "}
      Weapon:{" "}
      <select
        value={weaponName(user) || ""}
        onChange={(e) =>
          adminPost("admin_set_weapon", {
            user_id: user.id,
            weapon: e.target.value,
          })
        }
      >
        {weaponName(user) === null ? <option value="">custom</option> : null}
        {Object.keys(WEAPONS).map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
    </li>
  );
}

function TeamSection({ team }) {
  const [teamName, setTeamName] = useState(team.name);

  useEffect(() => {
    setTeamName(team.name);
  }, [team.name]);

  return (
    <div>
      <h4>{team.name}</h4>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          adminPost("admin_set_team_name", {
            team_id: team.id,
            name: teamName,
          });
        }}
      >
        <input
          value={teamName}
          aria-label="team name"
          onChange={(e) => setTeamName(e.target.value)}
          required
        />{" "}
        <button type="submit">Rename team</button>
      </form>
      <ul>
        {team.users.map((user) => (
          <UserControls key={user.id} user={user} />
        ))}
      </ul>
    </div>
  );
}

function GamePanel({ game }) {
  const [keepWeapons, setKeepWeapons] = useState(true);
  const newTeamInput = useRef(null);

  return (
    <>
      <h2>
        Game <code>{game.id}</code>
      </h2>

      <p>
        Status: <b>{game.active ? "running" : "paused"}</b>{" "}
        <button
          onClick={() =>
            adminPost("admin_set_game_active", {
              game_id: game.id,
              active: !game.active,
            })
          }
        >
          {game.active ? "Pause game" : "Start game"}
        </button>
      </p>

      <p>
        <label>
          <input
            type="checkbox"
            checked={game.ai_shot_review_enabled}
            onChange={(e) =>
              adminPost("admin_set_ai_shot_review", {
                game_id: game.id,
                enabled: e.target.checked,
              })
            }
          />{" "}
          AI reviews shot photos automatically (annotates the queue)
        </label>
        <br />
        <label>
          <input
            type="checkbox"
            checked={game.ai_auto_actions_enabled}
            onChange={(e) =>
              adminPost("admin_set_ai_auto_actions", {
                game_id: game.id,
                enabled: e.target.checked,
              })
            }
          />{" "}
          AI verdicts resolve shots automatically (confident calls ≥ 0.6 on the
          oldest queued shot; ambiguous ones wait for you)
        </label>
        <br />
        <label>
          <input
            type="checkbox"
            checked={game.ai_escalation_enabled}
            onChange={(e) =>
              adminPost("admin_set_ai_escalation", {
                game_id: game.id,
                enabled: e.target.checked,
              })
            }
          />{" "}
          Hard shots escalate to a stronger AI model (too few readable garments;
          its unsure cases still wait for you)
        </label>
      </p>

      <p>
        <button
          onClick={() => {
            if (
              window.confirm(
                "Reset this game? Wipes scores, shots, collected items and " +
                  "the ticker. Keeps teams and usernames.",
              )
            ) {
              adminPost("admin_reset_game", {
                game_id: game.id,
                keep_weapons: keepWeapons,
              });
            }
          }}
        >
          Reset game
        </button>{" "}
        <label>
          <input
            type="checkbox"
            checked={keepWeapons}
            onChange={(e) => setKeepWeapons(e.target.checked)}
          />{" "}
          keep weapons
        </label>
      </p>

      <Row>
        <Col md>
          <h3>Teams</h3>
          {game.teams.length === 0 ? (
            <p>No teams yet - add one below.</p>
          ) : null}
          {game.teams.map((team) => (
            <TeamSection key={team.id} team={team} />
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              adminPost("admin_create_team", {
                game_id: game.id,
                team_name: newTeamInput.current.value,
              });
              newTeamInput.current.value = "";
            }}
          >
            <input ref={newTeamInput} placeholder="New team name" required />{" "}
            <button type="submit">Add team</button>
          </form>
        </Col>

        <Col md>
          <h3>Circles</h3>
          <CircleControl game_id={game.id} />

          <h3>Ticker</h3>
          <TickerView admin game_id={game.id} num_messages={10} />
          <SendTickerMessage game_id={game.id} />
        </Col>
      </Row>

      <h3>Join QR codes</h3>
      <JoinQRCodes game_id={game.id} />
    </>
  );
}

function SendTickerMessage({ game_id }) {
  const messageInput = useRef(null);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        adminPost("admin_send_custom_ticker_message", {
          game_id: game_id,
          message: messageInput.current.value,
        });
        messageInput.current.value = "";
      }}
    >
      <input ref={messageInput} placeholder="Ticker announcement" required />{" "}
      <button type="submit">Send</button>
    </form>
  );
}

// Rename any user, put them in a team (optionally claiming an identity slot)
// or delete them outright. Covers players who have opened the app but are not
// yet in any team, so they don't appear under a game.
function PlayerRow({ user, teams, freeSlotsByGame }) {
  const nameInput = useRef(null);

  // Tracked with state (not a ref) so the slot options follow the team choice
  const [selectedTeamId, setSelectedTeamId] = useState(
    user.team_id || (teams.length > 0 ? teams[0].id : ""),
  );
  const [selectedSlot, setSelectedSlot] = useState("");

  const team = teams.find((t) => t.id === user.team_id);
  const selectedTeam = teams.find((t) => t.id === selectedTeamId);

  // Free slots of the game owning the currently-selected team, plus the
  // user's current slot (taken, so never in free_slots) if they have one.
  const slotOptions = [
    ...((selectedTeam && freeSlotsByGame[selectedTeam.game_id]) || []),
  ];
  if (user.identity_slot != null && !slotOptions.includes(user.identity_slot))
    slotOptions.push(user.identity_slot);
  slotOptions.sort((a, b) => a - b);

  return (
    <li>
      {user.name || <i>unnamed</i>} {team ? `(${team.name})` : <b>(no team)</b>}{" "}
      <small>
        <code>{user.id}</code>
      </small>
      <br />
      <input
        ref={nameInput}
        defaultValue={user.name || ""}
        placeholder="name"
      />
      <button
        onClick={() =>
          adminPost("admin_set_user_name", {
            user_id: user.id,
            name: nameInput.current.value,
          })
        }
      >
        Rename
      </button>{" "}
      <select
        aria-label="team"
        value={selectedTeamId}
        onChange={(e) => setSelectedTeamId(e.target.value)}
      >
        {teams.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
      <select
        aria-label="slot"
        value={selectedSlot}
        onChange={(e) => setSelectedSlot(e.target.value)}
      >
        <option value="">(no slot)</option>
        {slotOptions.map((slot) => (
          <option key={slot} value={slot}>
            {slot === user.identity_slot
              ? `outfit #${slot} (current)`
              : `outfit #${slot}`}
          </option>
        ))}
      </select>
      <button
        onClick={() => {
          const params = { user_id: user.id, team_id: selectedTeamId };
          if (selectedSlot !== "") params.slot = selectedSlot;
          adminPost("admin_add_user_to_team", params);
        }}
      >
        Put in team
      </button>{" "}
      <button
        onClick={() => {
          if (
            window.confirm(
              `Delete ${user.name || "this unnamed player"} entirely?`,
            )
          ) {
            adminPost("admin_delete_user", { user_id: user.id });
          }
        }}
      >
        Delete
      </button>
    </li>
  );
}

function AdminPanel() {
  const [games, setGames] = useState(null);
  const [users, setUsers] = useState([]);
  const [freeSlotsByGame, setFreeSlotsByGame] = useState({});

  // Failures show up in AdminPage's error log box
  const update = useCallback(() => {
    sendAPIRequest("admin_list_games", null, "GET", (loadedGames) => {
      setGames(loadedGames);
      // The free identity slots per game feed PlayerRow's slot picker
      loadedGames.forEach((game) => {
        sendAPIRequest(
          "admin_identity_report",
          { game_id: game.id },
          "GET",
          (report) =>
            setFreeSlotsByGame((previous) => ({
              ...previous,
              [game.id]: report.free_slots,
            })),
        );
      });
    });
    sendAPIRequest("get_users", {}, "GET", setUsers);
  }, []);

  useEffect(update, [update]);

  const createGame = useCallback(() => {
    if (
      games.length === 0 ||
      window.confirm(
        "A game already exists. Multiple simultaneous games confuse " +
          "automatic team assignment - create another anyway?",
      )
    ) {
      adminPost("admin_create_game", null, update);
    }
  }, [games, update]);

  if (games === null)
    return (
      <>
        <p>Loading...</p>
        <button onClick={update}>Retry</button>
      </>
    );

  const allTeams = games.flatMap((game) => game.teams);

  return (
    <>
      {/* Everything below refreshes whenever anything changes in any game */}
      <UpdateListener update_type="admin" callback={update} />

      <h1>Admin</h1>

      {games.length === 0 ? (
        <p>
          No games exist yet. Create one, add teams, then put players into teams
          as they appear under Players below.
        </p>
      ) : null}
      <p>
        <button onClick={createGame}>Create new game</button>
      </p>

      {games.map((game) => (
        <GamePanel key={game.id} game={game} />
      ))}

      <h2>Players</h2>
      <p>
        Everyone who has opened the app, including players not yet in a team.
      </p>
      <ul>
        {users.map((user) => (
          <PlayerRow
            key={user.id}
            user={user}
            teams={allTeams}
            freeSlotsByGame={freeSlotsByGame}
          />
        ))}
      </ul>

      <Row>
        <Col md>
          <h2>New items</h2>
          <NewItems />
        </Col>
        <Col md>
          <h2>Maintenance</h2>
          <button
            onClick={() =>
              adminDownload("admin_dump_images", null, "shot_images.zip")
            }
          >
            Download shot images (zip)
          </button>
        </Col>
      </Row>

      <h2>Map</h2>
      <Row>
        <MapViewAdmin />
      </Row>
    </>
  );
}

export default function AdminMode() {
  return (
    <AdminPage>
      <AdminPanel />
    </AdminPage>
  );
}
