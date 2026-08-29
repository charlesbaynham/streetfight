// The spectator screen: a laptop wired to a big TV, logged in as admin and
// left alone. Read-only - nothing here is clickable and nothing it does
// changes the game.
//
// Deliberately NOT in the admin house style (react-ui/src/ReferencePhotos.js).
// That exemplar is tuned for a phone held one-handed with a box of armbands in
// the other: big touch targets, light background, one column. This is read
// from three metres by people who will never touch it. It keeps the house
// *semantics* - state said in words, green and red for answers, amber for
// anything the machine is unsure of - and none of its shapes. See CLAUDE.md.

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { AdminPage } from "./AdminCommon";
import { MapViewAdmin } from "./MapView";
import { fallbackTeamColour } from "./teamColours";
import UpdateListener from "./UpdateListener";
import { charlesBotVerdict, verdictText } from "./ShotQueue";
import { weaponName } from "./AdminMode";
import { hexFor } from "./Swatch";
import useWakeLock from "./useWakeLock";
import { sendAPIRequest } from "./utils";

import styles from "./SpectatorView.module.css";

const RECENT_SHOT_COUNT = 6;
const TICKER_LINES = 6;
// The headline clock only has to look live, so a slow tick is plenty.
const CLOCK_TICK_MS = 1000;

// -- data -------------------------------------------------------------------

// The game this screen is about: the running one, or failing that the only one
// there is. The admin can have several games on the go; the screen shows the
// one being played.
function pickGame(games) {
  if (!games || games.length === 0) return null;
  return games.find((game) => game.active) || games[0];
}

function useSpectatorData() {
  const [games, setGames] = useState(null);
  const [scoreboard, setScoreboard] = useState([]);
  const [shots, setShots] = useState([]);
  const [ticker, setTicker] = useState([]);
  const [identity, setIdentity] = useState(null);

  const game = useMemo(() => pickGame(games), [games]);
  const gameId = game ? game.id : null;

  const refreshGames = useCallback(() => {
    sendAPIRequest("admin_list_games", {}, "GET", setGames);
  }, []);

  const refreshGameData = useCallback(() => {
    if (!gameId) return;
    sendAPIRequest("admin_get_scoreboard", { game_id: gameId }, "GET", (data) =>
      setScoreboard(data.table || []),
    );
    sendAPIRequest(
      "admin_ticker_messages",
      { game_id: gameId, num_messages: TICKER_LINES },
      "GET",
      setTicker,
    );
  }, [gameId]);

  const refreshShots = useCallback(() => {
    if (!gameId) return;
    sendAPIRequest(
      "admin_get_recent_shots",
      { game_id: gameId, limit: RECENT_SHOT_COUNT },
      "GET",
      setShots,
    );
  }, [gameId]);

  // The colour code's hexes, so a team's dot can be the colour of the hat its
  // players are actually wearing. Fetched once - the palette does not move.
  useEffect(() => {
    if (!gameId) return;
    sendAPIRequest(
      "admin_identity_report",
      { game_id: gameId },
      "GET",
      setIdentity,
    );
  }, [gameId]);

  useEffect(refreshGames, [refreshGames]);
  useEffect(refreshGameData, [refreshGameData]);
  useEffect(refreshShots, [refreshShots]);

  const refreshAll = useCallback(() => {
    refreshGames();
    refreshGameData();
  }, [refreshGames, refreshGameData]);

  return {
    game,
    games,
    scoreboard,
    shots,
    ticker,
    identity,
    refreshAll,
    refreshShots,
  };
}

// Each shot's photograph, fetched once and kept: they never change, and the
// feed itself is refetched on every bump.
function useThumbnails(shots) {
  const [thumbnails, setThumbnails] = useState({});
  const requested = useRef(new Set());

  useEffect(() => {
    shots.forEach((shot) => {
      if (requested.current.has(shot.id)) return;
      requested.current.add(shot.id);
      sendAPIRequest(
        "admin_get_shot_thumbnail",
        { shot_id: shot.id },
        "GET",
        (data) =>
          setThumbnails((previous) => ({
            ...previous,
            [shot.id]: data.image_base64,
          })),
      );
    });
  }, [shots]);

  return thumbnails;
}

// -- adjudication -----------------------------------------------------------

// Where a shot has got to, as a sentence. The tone classes carry the house
// meaning: "good" and "bad" are answers, "warn" is the machine being unsure.
export function adjudicationStatus(shot) {
  if (shot.checked) {
    const text = verdictText(shot, shot.target_name);
    if (shot.result === "hit") return [text, "good"];
    return [text, shot.result === "refunded" ? "warn" : "bad"];
  }

  if (shot.escalation_state === "pending")
    return ["Escalated to the stronger model...", "thinking"];
  if (shot.escalation_state === "error")
    return ["Escalation failed - over to the admin", "warn"];
  if (shot.state === "pending") return ["CharlesBot looking...", "thinking"];
  if (shot.state === "error")
    return ["CharlesBot errored - over to the admin", "warn"];

  const verdict = charlesBotVerdict({
    review: shot.review,
    identification: shot.identification,
    escalation: shot.escalation,
    escalationState: shot.escalation_state,
  });
  if (verdict) return [verdict, "thinking"];

  return ["Waiting for the admin", "warn"];
}

// -- roster -----------------------------------------------------------------

const STATE_ORDER = { alive: 0, "knocked out": 1, dead: 2, waiting: 3 };

const STATE_CLASS = {
  alive: "alive",
  "knocked out": "knockedOut",
  dead: "dead",
  waiting: "waiting",
};

function secondsUntil(timestamp, now) {
  return Math.max(0, Math.round(timestamp - now / 1000));
}

function countdown(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

// -- panels -----------------------------------------------------------------

// The wall clock rather than an elapsed one: a Game has neither a name nor a
// recorded start time (backend/model.py GameModel), so "2:14 into the game"
// would be invented. Adding a started_at is a schema change - see the design
// brief.
function Headline({ game, players, now }) {
  const alive = players.filter((p) => p.state === "alive").length;

  return (
    <header className={styles.headline}>
      <span className={styles.headlineTitle}>Streetfight</span>
      <span className={styles.headlineClock}>
        {new Date(now).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
      <span className={styles.headlineAlive}>
        <strong>{alive}</strong> of {players.length} alive
      </span>
      {game && !game.active ? (
        <span className={styles.headlinePaused}>Paused</span>
      ) : null}
    </header>
  );
}

function ShotFeed({ shots, thumbnails }) {
  if (shots.length === 0)
    return (
      <section className={styles.panel}>
        <h2 className={styles.panelTitle}>Recent shots</h2>
        <p className={styles.empty}>No shots fired yet.</p>
      </section>
    );

  return (
    <section className={styles.panel}>
      <h2 className={styles.panelTitle}>Recent shots</h2>
      <ul className={styles.shotList}>
        {shots.map((shot) => {
          const [status, tone] = adjudicationStatus(shot);
          return (
            <li key={shot.id} className={styles.shot}>
              {thumbnails[shot.id] ? (
                <img
                  className={styles.shotThumb}
                  src={thumbnails[shot.id]}
                  alt=""
                />
              ) : (
                <div className={styles.shotThumbPlaceholder} />
              )}
              <div className={styles.shotBody}>
                <div className={styles.shotWho}>
                  <span className={styles.shotShooter}>
                    {shot.shooter_name || "Someone"}
                  </span>
                  <span className={styles.shotArrow}>&rarr;</span>
                  <span className={styles.shotTarget}>
                    {shot.target_name || "?"}
                  </span>
                </div>
                <div className={`${styles.shotStatus} ${styles[tone]}`}>
                  {status}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function TeamTotals({ teams, players, scoreById, colourForTeam }) {
  return (
    <ul className={styles.teamTotals}>
      {teams.map((team) => {
        const members = players.filter((p) => p.team_id === team.id);
        const alive = members.filter((p) => p.state === "alive").length;
        const damage = members.reduce(
          (total, p) => total + (scoreById[p.id] || 0),
          0,
        );
        return (
          <li key={team.id} className={styles.teamTotal}>
            <span
              className={styles.teamDot}
              style={{ background: colourForTeam(team.id) }}
            />
            <span className={styles.teamName}>{team.name}</span>
            <span className={styles.teamStat}>{alive} alive</span>
            <span className={styles.teamStat}>{damage} dmg</span>
          </li>
        );
      })}
    </ul>
  );
}

function Roster({ teams, players, scoreById, colourForTeam, now }) {
  const ordered = useMemo(
    () =>
      [...players].sort((a, b) => {
        const byState =
          (STATE_ORDER[a.state] ?? 9) - (STATE_ORDER[b.state] ?? 9);
        if (byState !== 0) return byState;
        return (scoreById[b.id] || 0) - (scoreById[a.id] || 0);
      }),
    [players, scoreById],
  );

  return (
    <section className={styles.panel}>
      <h2 className={styles.panelTitle}>Players</h2>
      <TeamTotals
        teams={teams}
        players={players}
        scoreById={scoreById}
        colourForTeam={colourForTeam}
      />
      <ul className={styles.roster}>
        {ordered.map((player) => {
          // Armour is HP above 1 - there is no armour column. Same convention
          // as Scoreboard.js and backend/item_actions.py's _handle_armour.
          const armour = Math.max(player.hit_points - 1, 0);
          const knockedOut = player.state === "knocked out";
          return (
            <li
              key={player.id}
              className={`${styles.rosterRow} ${styles[STATE_CLASS[player.state] || "waiting"]}`}
            >
              <span
                className={styles.teamDot}
                style={{ background: colourForTeam(player.team_id) }}
              />
              <span className={styles.rosterName}>
                {player.name || "unnamed"}
              </span>
              {player.state === "alive" ? (
                <>
                  <span className={styles.stat} title="armour">
                    {armour} armour
                  </span>
                  <span className={styles.stat} title="ammo">
                    {player.num_bullets} ammo
                  </span>
                  <span className={styles.statWeapon}>
                    {weaponName(player) || ""}
                  </span>
                </>
              ) : (
                <span className={styles.rosterState}>
                  {knockedOut && player.time_of_death
                    ? `back in ${countdown(secondsUntil(player.time_of_death, now))}`
                    : player.state}
                </span>
              )}
              <span className={styles.score}>{scoreById[player.id] || 0}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Ticker({ lines }) {
  if (!lines || lines.length === 0) return null;
  return (
    <footer className={styles.ticker}>
      <ul>
        {lines.map((line, i) => (
          <li key={i}>{line[1]}</li>
        ))}
      </ul>
    </footer>
  );
}

// -- the screen -------------------------------------------------------------

function SpectatorScreen() {
  useWakeLock();

  const {
    game,
    games,
    scoreboard,
    shots,
    ticker,
    identity,
    refreshAll,
    refreshShots,
  } = useSpectatorData();
  const thumbnails = useThumbnails(shots);

  // Only for the elapsed clock and the knocked-out countdowns, which have to
  // move without anything arriving from the server.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const handle = setInterval(() => setNow(Date.now()), CLOCK_TICK_MS);
    return () => clearInterval(handle);
  }, []);

  // Only teams with players in them: a game is created with more teams than
  // get used, and empty rows are just noise on a screen nobody can scroll.
  const teams = useMemo(
    () =>
      game ? game.teams.filter((team) => (team.users || []).length > 0) : [],
    [game],
  );
  const players = useMemo(
    () => teams.flatMap((team) => team.users || []),
    [teams],
  );

  const scoreById = useMemo(() => {
    const out = {};
    scoreboard.forEach((row) => {
      out[row.user_id] = row.total_damage;
    });
    return out;
  }, [scoreboard]);

  // A team's colour is the hat its players wear, so the dots on the map match
  // the people in the room. Falls back to MapViewAdmin's own palette when a
  // team has no pinned colour yet.
  const colourForTeam = useCallback(
    (teamId) => {
      const team = teams.find((t) => t.id === teamId);
      if (identity && identity.channels && identity.team_channel && team) {
        const hex = hexFor(
          identity.channels,
          identity.team_channel,
          team.identity_colour,
        );
        if (hex) return hex;
      }
      // No pinned hat colour yet (a game before the join codes are minted).
      // Fall back to the map's own palette, by the same index, so a dot and
      // its roster row still match.
      return fallbackTeamColour(teams.findIndex((t) => t.id === teamId));
    },
    [identity, teams],
  );

  if (games !== null && !game)
    return <p className={styles.empty}>No games yet.</p>;

  return (
    <div className={styles.screen}>
      <UpdateListener update_type="admin" callback={refreshAll} />
      <UpdateListener update_type="shots" callback={refreshShots} />

      <Headline game={game} players={players} now={now} />

      <div className={styles.body}>
        <div className={styles.mapPanel}>
          <MapViewAdmin
            gameId={game ? game.id : null}
            colourForTeam={colourForTeam}
            circles={game || null}
            fillContainer
          />
        </div>
        <div className={styles.sidebar}>
          <ShotFeed shots={shots} thumbnails={thumbnails} />
          <Roster
            teams={teams}
            players={players}
            scoreById={scoreById}
            colourForTeam={colourForTeam}
            now={now}
          />
        </div>
      </div>

      <Ticker lines={ticker} />
    </div>
  );
}

export default function SpectatorView() {
  return (
    <AdminPage bare>
      <SpectatorScreen />
    </AdminPage>
  );
}
