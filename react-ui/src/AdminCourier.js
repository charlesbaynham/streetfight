import React, { useCallback, useEffect, useRef, useState } from "react";

import { AdminPage, adminPost } from "./AdminCommon";
import { sendAPIRequest } from "./utils";
import useWakeLock from "./useWakeLock";

import styles from "./AdminCourier.module.css";

// The same tier MapViewSelf uses when a player has the map popped out: the
// courier is the one person on the night whose position is being read off
// somebody else's screen, so it is worth the radio.
const COURIER_GEO_OPTIONS = {
  enableHighAccuracy: true,
  maximumAge: 1 * 1000,
  timeout: 20 * 1000,
};

// How often the fix is posted. The server writes every one and throttles the
// fan-out to the players itself (AdminInterface.COURIER_ANNOUNCE_INTERVAL_S),
// so this only has to be often enough that stopping is prompt.
const UPLOAD_INTERVAL_MS = 1000;

// The drop circle this page places. A tight one: it marks where the crate is,
// not an area to search.
const DROP_RADIUS_KM = 0.02;

// Two-tap confirm, as on the reset button: the first tap arms, and an armed
// button disarms itself after this long.
const ARMED_MS = 6000;

function GameSelector({ games, gameId, setGameId }) {
  if (games.length <= 1) return null;

  return (
    <p>
      <label>
        Game:{" "}
        <select
          value={gameId || ""}
          onChange={(e) => setGameId(e.target.value)}
        >
          {games.map((game) => (
            <option key={game.id} value={game.id}>
              {game.id.slice(0, 8)} (
              {game.teams.map((t) => t.name).join(", ") || "no teams"})
            </option>
          ))}
        </select>
      </label>
    </p>
  );
}

// Seconds since a fix, said the way somebody glancing at a phone reads it
function ageWords(seconds) {
  if (seconds < 2) return "just now";
  if (seconds < 90) return `${Math.round(seconds)} s ago`;
  return `${Math.round(seconds / 60)} min ago`;
}

export function CourierPanel() {
  const held = useWakeLock();

  const [games, setGames] = useState(null);
  const [gameId, setGameId] = useState("");

  const [broadcasting, setBroadcasting] = useState(false);
  const [fix, setFix] = useState(null);
  const [geoError, setGeoError] = useState(null);
  const [placed, setPlaced] = useState(false);
  const [armed, setArmed] = useState(false);

  // Re-render once a second so the "last fix N s ago" line counts up on its
  // own: between fixes nothing else changes, and a frozen age reads as a
  // frozen page.
  const [, setTick] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const lastUpload = useRef(0);

  useEffect(() => {
    sendAPIRequest("admin_list_games", null, "GET", (loaded) => {
      setGames(loaded);
      if (loaded.length > 0) setGameId((current) => current || loaded[0].id);
    });
  }, []);

  useEffect(() => {
    if (!armed) return undefined;
    const timeout = setTimeout(() => setArmed(false), ARMED_MS);
    return () => clearTimeout(timeout);
  }, [armed]);

  // The watch itself. Every callback updates what the page says; uploads are
  // throttled, exactly as MapViewSelf does it.
  useEffect(() => {
    if (!broadcasting || !gameId) return undefined;
    if (!navigator.geolocation) {
      setGeoError("This browser has no geolocation.");
      return undefined;
    }

    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        setGeoError(null);
        setFix({
          lat: position.coords.latitude,
          long: position.coords.longitude,
          accuracy: position.coords.accuracy,
          at: Date.now(),
        });

        const now = Date.now();
        if (now - lastUpload.current < UPLOAD_INTERVAL_MS) return;
        lastUpload.current = now;

        adminPost("admin_set_courier_location", {
          game_id: gameId,
          lat: position.coords.latitude,
          long: position.coords.longitude,
          accuracy: position.coords.accuracy,
        });
      },
      (error) => setGeoError(error.message || "Could not get a fix."),
      COURIER_GEO_OPTIONS,
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [broadcasting, gameId]);

  const stop = useCallback(() => {
    setBroadcasting(false);
    setArmed(false);
    setFix(null);
    if (gameId) adminPost("admin_clear_courier", { game_id: gameId });
  }, [gameId]);

  // Placing the drop goes through the ordinary circle endpoint, so the ticker
  // message and the circle event are the same ones an admin placing it from
  // the map would fire. Then the courier's job is done, so it stops.
  const placeDrop = useCallback(() => {
    if (!fix || !gameId) return;
    adminPost("admin_set_circle", {
      game_id: gameId,
      name: "DROP",
      lat: fix.lat,
      long: fix.long,
      radius_km: DROP_RADIUS_KM,
    }).then((response) => {
      if (!response.ok) return;
      setPlaced(true);
      stop();
    });
  }, [fix, gameId, stop]);

  if (games === null) return <p>Loading games...</p>;
  if (games.length === 0) return <p>No games exist yet - create one first.</p>;

  const ageSeconds = fix ? (Date.now() - fix.at) / 1000 : null;

  return (
    <div className={styles.page}>
      <h1>Courier</h1>

      <GameSelector games={games} gameId={gameId} setGameId={setGameId} />

      <p>
        <span
          className={
            styles.status +
            " " +
            (broadcasting ? styles.statusGood : styles.statusNone)
          }
        >
          {broadcasting
            ? fix
              ? `Broadcasting - last fix ${ageWords(ageSeconds)}, ±${Math.round(
                  fix.accuracy,
                )} m`
              : "Broadcasting - waiting for a fix"
            : "Not broadcasting"}
        </span>
      </p>

      {geoError ? <p className={styles.bad}>{geoError}</p> : null}

      {broadcasting ? (
        <button className={styles.bigButton} onClick={stop}>
          Stop broadcasting
        </button>
      ) : (
        <button
          className={styles.bigButton}
          onClick={() => {
            setPlaced(false);
            lastUpload.current = 0;
            setBroadcasting(true);
          }}
        >
          Broadcast my location
        </button>
      )}

      <button
        className={
          styles.bigButton +
          (armed ? " " + styles.armed : "") +
          " " +
          styles.place
        }
        disabled={!fix}
        onClick={() => (armed ? placeDrop() : setArmed(true))}
      >
        {armed ? "Tap again to put the crate here" : "Place drop here"}
      </button>

      <p className={styles.hint}>
        Placing the drop puts the drop circle at your current fix, tells the
        players it is there, and stops broadcasting - the crate is on the
        ground, so the courier is no longer worth following.
      </p>

      {placed ? (
        <p className={styles.good}>Drop placed. Crate is down.</p>
      ) : null}

      {held ? null : (
        <p className={styles.bad}>
          The screen may lock itself - keep the phone awake by hand.
        </p>
      )}
    </div>
  );
}

export default function AdminCourier() {
  return (
    <AdminPage>
      <CourierPanel />
    </AdminPage>
  );
}
