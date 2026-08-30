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
      {user.num_bullets} ammo, {user.appeals_remaining} appeals,{" "}
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
      {/* A referee who has just talked something through with a player needs
          to be able to give them another go (roadmap R8) */}
      Appeals:{" "}
      <button
        aria-label="Appeals +1"
        onClick={() =>
          adminPost("admin_give_appeals", { user_id: user.id, num: 1 })
        }
      >
        +1
      </button>
      <button
        aria-label="Appeals -1"
        onClick={() =>
          adminPost("admin_give_appeals", { user_id: user.id, num: -1 })
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
      <button
        onClick={() => {
          if (
            window.confirm(
              `Delete team ${team.name}? This also deletes its ` +
                `${team.users.length} player(s) entirely.`,
            )
          ) {
            adminPost("admin_delete_team", { team_id: team.id });
          }
        }}
      >
        Delete team
      </button>
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

      {/* "CharlesBot" is the display name for what the API calls ai_review (#1). */}
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
          CharlesBot reviews shot photos automatically (annotates the queue)
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
          CharlesBot verdicts resolve shots automatically (confident calls ≥ 0.6
          on the oldest queued shot; ambiguous ones wait for you)
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
          Hard shots escalate to a stronger CharlesBot model (too few readable
          garments; its unsure cases still wait for you)
        </label>
        <br />
        <label>
          <input
            type="checkbox"
            checked={game.ai_resolve_everything_enabled}
            onChange={(e) =>
              adminPost("admin_set_ai_resolve_everything", {
                game_id: game.id,
                enabled: e.target.checked,
              })
            }
          />{" "}
          CharlesBot resolves every shot it can (unconfident calls too - players
          appeal the wrong ones)
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

// Fires the thirty-player sample game one shot at a time (backend/demo_game.py)
// so a dashboard - the spectator screen above all - can be watched reacting to
// shots landing, rather than found already full the way `npm run demoshots`
// leaves it. Safe to leave on the page during a real game: the backend refuses
// outright if anybody in a team is not one of the simulated players.
const DEMO_GAME_POLL_MS = 2000;

function demoGameSummary(status) {
  if (!status) return "checking...";
  switch (status.state) {
    case "idle":
      return "not started";
    case "provisioning":
      return "creating the thirty players (this takes a few seconds)";
    case "firing":
      return (
        `firing: ${status.fired} of ${status.total} shots` +
        (status.next_in_s === null ? "" : `, next in ${status.next_in_s}s`)
      );
    case "cancelling":
      return "stopping after the shot in flight";
    case "cancelled":
      return (
        `stopped after ${status.fired} of ${status.total} shots - ` +
        "starting again picks up where it left off"
      );
    case "done":
      return `all ${status.fired} shots fired`;
    case "error":
      return `failed: ${status.error}`;
    default:
      return status.state;
  }
}

function DemoGamePanel() {
  const [status, setStatus] = useState(null);
  // The refusal is the message worth reading twice: it is the answer to "why
  // did nothing happen?", so it goes beside the button as well as into the
  // error log at the top of the page.
  const [refusal, setRefusal] = useState(null);
  const running = status ? status.running : false;

  const update = useCallback(() => {
    sendAPIRequest("admin_demo_game_status", {}, "GET", setStatus);
  }, []);

  useEffect(update, [update]);

  // Only while something is happening - a finished run has nothing more to
  // say. Keyed on `running` rather than on the whole status, so a poll that
  // changes nothing but the countdown doesn't restart the timer.
  useEffect(() => {
    if (!running) return undefined;
    const interval = setInterval(update, DEMO_GAME_POLL_MS);
    return () => clearInterval(interval);
  }, [running, update]);

  const send = useCallback((endpoint) => {
    setRefusal(null);
    adminPost(endpoint, null, setStatus).then(async (response) => {
      if (response.ok) return;
      const body = await response.json().catch(() => null);
      setRefusal(
        (body && body.detail) || `Request failed (${response.status})`,
      );
    });
  }, []);

  return (
    <>
      <button onClick={() => send("admin_start_demo_game")}>
        Fire demo game
      </button>{" "}
      <button
        onClick={() => send("admin_cancel_demo_game")}
        disabled={!running}
      >
        Cancel demo game
      </button>
      <p>
        Thirty simulated players and their ten shots, dripped in one at a time
        over about five minutes so the spectator screen has something to react
        to. Pressing it again while it runs changes nothing; after a cancel it
        carries on from where it stopped.
        <br />
        Demo game: <b>{demoGameSummary(status)}</b>
      </p>
      {refusal ? <p style={{ color: "red" }}>{refusal}</p> : null}
    </>
  );
}

function AdminPanel() {
  const [games, setGames] = useState(null);
  const [users, setUsers] = useState([]);
  const [freeSlotsByGame, setFreeSlotsByGame] = useState({});
  const [showUnnamed, setShowUnnamed] = useState(false);

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
        Unnamed players are hidden by default.
      </p>
      <p>
        <label>
          <input
            type="checkbox"
            checked={showUnnamed}
            onChange={(e) => setShowUnnamed(e.target.checked)}
          />{" "}
          {`Show unnamed players (${
            users.filter((user) => !user.name).length
          })`}
        </label>
      </p>
      <ul>
        {users
          .filter((user) => showUnnamed || user.name)
          .map((user) => (
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
          <h3>Demo game</h3>
          <DemoGamePanel />
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
