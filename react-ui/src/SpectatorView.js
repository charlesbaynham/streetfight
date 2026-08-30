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

import { FullScreen, useFullScreenHandle } from "react-full-screen";

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
const GALLERY_SHOT_COUNT = 4;
const TICKER_LINES = 6;
// The headline clock only has to look live, so a slow tick is plenty.
const CLOCK_TICK_MS = 1000;

// How long each face holds before the screen swaps. The gallery's 10s is not
// arbitrary: .screenProgress's countdown animation runs for exactly that, so
// the hairline finishes as the face changes. The map gets four times the
// airtime because it is the main event and the gallery is the interstitial.
const DASHBOARD_MS = 40 * 1000;
const GALLERY_MS = 10 * 1000;

// The takeover: a new shot's photograph gets the room, holds while CharlesBot
// works, and leaves a few seconds after the first conclusion - "escalating"
// counts as a conclusion.
//
// TAKEOVER_MAX_WAIT_MS is the part the design could not know about. CharlesBot
// is off unless a per-game toggle is on, and the roadmap's safety valve is
// that the game runs with the admin adjudicating by hand. With it off no
// conclusion ever arrives, so without a cap the first shot of the night would
// park on screen for the rest of the evening.
const TAKEOVER_MAX_WAIT_MS = 15 * 1000;
// Must stay in step with the takeoverCountdown animation in the stylesheet,
// which drains the bar over exactly this long. Change one and change the other,
// or the bar empties early and then sits there.
const TAKEOVER_RESOLVED_MS = 3 * 1000;
const TAKEOVER_LEAVING_MS = 300; // matches takeoverOut
// A busy minute must not hide the map. Older ones are dropped rather than
// queued forever; they still reach the feed and the gallery seconds later.
const TAKEOVER_QUEUE_MAX = 3;

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
  // null until the first response: an empty feed and an unloaded one are
  // different things to the takeover, which must not fire for shots that
  // happened before anybody was watching.
  const [shots, setShots] = useState(null);
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
    shots: shots || [],
    shotsLoaded: shots !== null,
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

// -- the takeover -----------------------------------------------------------

// Which shots have just landed, and where the one on screen has got to.
//
// Returns the id of the shot to show (or null), its stage, and how many are
// queued behind it. The *content* is deliberately not returned: the caller
// looks the id up in the live feed each render, so the status updates in place
// as the pipeline advances. Watching a verdict land is the whole point of the
// panel, and a snapshot taken at pop time would freeze it.
export function useShotTakeover(shots, loaded) {
  const [queue, setQueue] = useState([]);
  const [stage, setStage] = useState("waiting");
  const seen = useRef(null);

  // New arrivals join the queue. The first response only seeds the set:
  // opening the page mid-game would otherwise take over for six shots that
  // happened before anybody was watching.
  useEffect(() => {
    if (!loaded) return;

    const ids = shots.map((shot) => shot.id);

    if (seen.current === null) {
      seen.current = new Set(ids);
      return;
    }

    const arrived = ids.filter((id) => !seen.current.has(id));
    if (arrived.length === 0) return;

    arrived.forEach((id) => seen.current.add(id));
    setQueue((previous) =>
      [...previous, ...arrived.reverse()].slice(-TAKEOVER_QUEUE_MAX),
    );
  }, [shots, loaded]);

  const current = queue[0] || null;
  const shot = current ? shots.find((s) => s.id === current) : null;
  const concluded = hasConcluded(shot);

  // waiting -> resolving, on a conclusion or the cap, whichever comes first
  useEffect(() => {
    if (!current || stage !== "waiting") return undefined;
    if (concluded) {
      setStage("resolving");
      return undefined;
    }
    const handle = setTimeout(
      () => setStage("resolving"),
      TAKEOVER_MAX_WAIT_MS,
    );
    return () => clearTimeout(handle);
  }, [current, stage, concluded]);

  // resolving -> leaving -> gone, and on to whatever queued behind it
  useEffect(() => {
    if (!current || stage !== "resolving") return undefined;
    const handle = setTimeout(() => setStage("leaving"), TAKEOVER_RESOLVED_MS);
    return () => clearTimeout(handle);
  }, [current, stage]);

  useEffect(() => {
    if (!current || stage !== "leaving") return undefined;
    const handle = setTimeout(() => {
      setQueue((previous) => previous.slice(1));
      setStage("waiting");
    }, TAKEOVER_LEAVING_MS);
    return () => clearTimeout(handle);
  }, [current, stage]);

  return { shotId: current, stage, waiting: Math.max(0, queue.length - 1) };
}

// -- team letters -----------------------------------------------------------

// A letter per team, dropped into each .teamDot via data-letter.
//
// This is the fix for the one hazard the palette cannot solve on its own: team
// colours are the hat each team wears, and the hat palette is measured off real
// kit rather than designed for contrast - burgundy and rust are 14.2 dE2000
// apart and read alike across a room. So the letters must be *distinct*, which
// is why this is not simply name[0]: with a Blue team already holding "B",
// Burgundy has to take something else or the dot stops disambiguating in
// exactly the case it exists for.
export function teamLetters(teams) {
  const taken = new Set();
  const out = {};

  teams.forEach((team) => {
    const candidates = [
      ...(team.name || "").toUpperCase().replace(/[^A-Z]/g, ""),
      ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ];
    const letter = candidates.find((c) => !taken.has(c)) || "?";
    taken.add(letter);
    out[team.id] = letter;
  });

  return out;
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

// Has anything at all been concluded about this shot? The takeover holds until
// this is true (or it times out). The design is explicit that "escalating"
// counts: it is news, so it is a conclusion.
export function hasConcluded(shot) {
  if (!shot) return false;
  return Boolean(
    shot.checked ||
    shot.state === "done" ||
    shot.state === "error" ||
    shot.escalation_state,
  );
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
function Headline({
  game,
  players,
  now,
  fullscreenActive,
  onToggleFullscreen,
}) {
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
      {game && !game.active ? (
        <span className={styles.headlinePaused}>Paused</span>
      ) : null}
      {/* One string, and the number is not picked out in green: on this page
          colour means certainty, and a count is not a verdict. */}
      <span className={styles.headlineAlive}>
        {alive} of {players.length} alive
      </span>
      {/* The one clickable thing on an otherwise hands-off screen: set once
          when the laptop is wired to the TV, then left alone. */}
      <button
        type="button"
        className={styles.fullscreenToggle}
        onClick={onToggleFullscreen}
      >
        {fullscreenActive ? "Exit full screen" : "Full screen"}
      </button>
    </header>
  );
}

// The letter is what separates two teams whose hat colours are nearly the
// same; the fill is the hat colour itself.
function TeamDot({ colour, letter }) {
  return (
    <span
      className={styles.teamDot}
      style={colour ? { background: colour } : undefined}
      data-letter={letter}
    />
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

function TeamTotals({ teams, players, scoreById, colourForTeam, letters }) {
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
            <TeamDot
              colour={colourForTeam(team.id)}
              letter={letters[team.id]}
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

function Roster({ teams, players, scoreById, colourForTeam, letters, now }) {
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
        letters={letters}
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
              <TeamDot
                colour={colourForTeam(player.team_id)}
                letter={letters[player.team_id]}
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

// -- the gallery face -------------------------------------------------------

// One row of tall frames, the photographs big. Portrait phone shots fill a
// 9:16 cell almost exactly, which is why this is four across rather than a
// grid of wide ones.
function Gallery({ shots, thumbnails }) {
  return (
    <ul className={styles.gallery}>
      {shots.slice(0, GALLERY_SHOT_COUNT).map((shot) => {
        const [status, tone] = adjudicationStatus(shot);
        return (
          <li key={shot.id} className={styles.galleryItem}>
            {thumbnails[shot.id] ? (
              <img
                className={styles.galleryPhoto}
                src={thumbnails[shot.id]}
                alt=""
              />
            ) : (
              <div className={styles.galleryPhotoPlaceholder} />
            )}
            <div className={styles.galleryCaption}>
              <div className={styles.galleryWho}>
                <span className={styles.shotShooter}>
                  {shot.shooter_name || "Someone"}
                </span>
                <span className={styles.shotArrow}>&rarr;</span>
                <span className={styles.shotTarget}>
                  {shot.target_name || "?"}
                </span>
              </div>
              <div className={`${styles.galleryStatus} ${styles[tone]}`}>
                {status}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// -- the takeover -----------------------------------------------------------

// Sits over whichever face is showing - the dashboard is scrimmed rather than
// replaced, so the map never disappears and nobody loses their place.
function ShotTakeover({ shot, stage, waiting, thumbnail }) {
  const [status, tone] = adjudicationStatus(shot);

  return (
    <div
      className={`${styles.shotTakeover} ${
        stage === "leaving" ? styles.leaving : ""
      }`}
    >
      <div className={styles.takeoverScrim} />
      <div className={styles.takeoverCard}>
        {waiting > 0 ? (
          <div className={styles.takeoverQueue}>{waiting} more waiting</div>
        ) : null}
        {thumbnail ? (
          <img className={styles.takeoverPhoto} src={thumbnail} alt="" />
        ) : (
          <div className={styles.takeoverPhotoPlaceholder} />
        )}
        <div className={styles.takeoverWho}>
          <span className={styles.takeoverShooter}>
            {shot.shooter_name || "Someone"}
          </span>
          <span className={styles.takeoverArrow}>&rarr;</span>
          <span className={styles.takeoverTarget}>
            {shot.target_name || "?"}
          </span>
        </div>
        <div className={`${styles.takeoverStatus} ${styles[tone]}`}>
          {status}
        </div>
        <div
          className={`${styles.takeoverTimer} ${
            stage === "waiting" ? "" : styles.resolving
          }`}
        />
      </div>
    </div>
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

// -- the face cycle ---------------------------------------------------------

// The screen alternates between the map and the photo wall. `hasGallery` is
// false for the first hour of every game - a photo wall with nothing on it
// reads as broken, so the map simply stays up until there is a shot to show.
function useFaceCycle(hasGallery) {
  const [face, setFace] = useState("dashboard");

  useEffect(() => {
    if (!hasGallery) {
      setFace("dashboard");
      return undefined;
    }
    const handle = setTimeout(
      () => setFace((f) => (f === "dashboard" ? "gallery" : "dashboard")),
      face === "dashboard" ? DASHBOARD_MS : GALLERY_MS,
    );
    return () => clearTimeout(handle);
  }, [face, hasGallery]);

  return hasGallery ? face : "dashboard";
}

function SpectatorScreen() {
  useWakeLock();

  const fullscreenHandle = useFullScreenHandle();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const reportFullscreenChange = useCallback((state) => {
    setIsFullscreen(state);
  }, []);
  const toggleFullscreen = useCallback(() => {
    if (isFullscreen) fullscreenHandle.exit();
    else fullscreenHandle.enter();
  }, [fullscreenHandle, isFullscreen]);

  const {
    game,
    games,
    scoreboard,
    shots,
    ticker,
    identity,
    shotsLoaded,
    refreshAll,
    refreshShots,
  } = useSpectatorData();
  const thumbnails = useThumbnails(shots);
  const face = useFaceCycle(shots.length > 0);
  const takeover = useShotTakeover(shots, shotsLoaded);
  const takeoverShot = takeover.shotId
    ? shots.find((shot) => shot.id === takeover.shotId)
    : null;

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

  const letters = useMemo(() => teamLetters(teams), [teams]);

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
    <FullScreen
      handle={fullscreenHandle}
      onChange={reportFullscreenChange}
      className={styles.screen}
    >
      <UpdateListener update_type="admin" callback={refreshAll} />
      <UpdateListener update_type="shots" callback={refreshShots} />

      <Headline
        game={game}
        players={players}
        now={now}
        fullscreenActive={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
      />

      {face === "gallery" ? (
        <>
          {/* The swap timer. Its countdown runs for GALLERY_MS, so the
              hairline finishes as the face changes. */}
          <div className={styles.screenProgress} />
          <Gallery shots={shots} thumbnails={thumbnails} />
        </>
      ) : (
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
              letters={letters}
              now={now}
            />
          </div>
        </div>
      )}

      <Ticker lines={ticker} />

      {/* Over whichever face is showing. Reads its shot out of the live feed,
          so the verdict lands on screen as it lands in the database. */}
      {takeoverShot ? (
        <ShotTakeover
          shot={takeoverShot}
          stage={takeover.stage}
          waiting={takeover.waiting}
          thumbnail={thumbnails[takeoverShot.id]}
        />
      ) : null}
    </FullScreen>
  );
}

export default function SpectatorView() {
  return (
    <AdminPage bare>
      <SpectatorScreen />
    </AdminPage>
  );
}
