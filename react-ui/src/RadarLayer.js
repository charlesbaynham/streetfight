import React, { useCallback, useEffect, useState } from "react";

import Dot from "./Dot";
import { CountdownTimer } from "./GuideImages";
import prose from "./prose";
import { sendAPIRequest } from "./utils";

import styles from "./RadarLayer.module.css";

// How often the radar asks the server again. The admin map's number: a phone
// uploads a fix every five seconds at best, so anything faster buys nothing.
const RADAR_POLL_MS = 5 * 1000;

// A radar contact fades as its fix ages, on the same principle as the dots on
// the admin map - the card promises "last seen", never "is". Its own constants
// rather than MapView's, because a radar contact goes properly faint: a fix
// ten minutes old is somewhere the holder should not be running to.
const RADAR_TIME_UNTIL_FAINT = 10 * 60;
const RADAR_MIN_ALPHA = 0.25;

// Where the radar is drawn and where the player is told about it are two
// different places on the screen: the map's coordinate space, inside a
// pinch-zoomable transform, and the strip at the top of the HUD. The strip is
// the half that knows, because UserMode has the player's own /user_info - so
// it publishes here and the layer inside the map reads it. Same shape as
// shotRefusalStore.js, and for the same reason: a prop threaded through
// MapView would put a player's radar on the admin's map and the spectator
// screen too, neither of which has any business polling for it.
let radarState = { radarUntil: null, teamName: null };
const subscribers = new Set();

function publishRadar(next) {
  radarState = next;
  subscribers.forEach((callback) => callback(radarState));
}

function subscribeRadar(callback) {
  subscribers.add(callback);
  return () => subscribers.delete(callback);
}

// Is this deadline still in the future? Null and a moment already past both
// mean "no radar", exactly as they do on the server (User.radar_until).
function radarIsLive(radarUntil) {
  return typeof radarUntil === "number" && radarUntil * 1000 > Date.now();
}

// True while the deadline is in the future, flipping to false the moment it
// passes rather than waiting for the next thing to happen - a strip stuck at
// 00:00, or dots that outlive the card, are worse than nothing.
function useLiveUntil(radarUntil) {
  const [live, setLive] = useState(() => radarIsLive(radarUntil));

  useEffect(() => {
    const isLive = radarIsLive(radarUntil);
    setLive(isLive);
    if (!isLive) return undefined;
    const handle = setTimeout(
      () => setLive(false),
      radarUntil * 1000 - Date.now(),
    );
    return () => clearTimeout(handle);
  }, [radarUntil]);

  return live;
}

// What the player is told about their own radar: a band at the top of the HUD
// saying it is running and how long is left. Mounted from UserMode beside
// NextEventStrip, and also what tells the layer below there is a radar to
// draw. Renders nothing at all when there is none, which is most of the night.
export function RadarStrip({ user }) {
  const radarUntil =
    user && typeof user.radar_until === "number" ? user.radar_until : null;
  const teamName = user ? user.team_name : null;

  useEffect(() => {
    publishRadar({ radarUntil, teamName });
    return () => publishRadar({ radarUntil: null, teamName: null });
  }, [radarUntil, teamName]);

  const live = useLiveUntil(radarUntil);

  if (!live) return null;

  return (
    <div className={styles.strip} data-testid="radar-strip">
      <span className={styles.label}>{prose.radar.stripLabel}</span>{" "}
      <span className={styles.clock}>
        <CountdownTimer deadline={radarUntil * 1000} />
      </span>{" "}
      <span className={styles.tail}>{prose.radar.stripTail}</span>
    </div>
  );
}

// "3 min ago", or "just now" for a fix younger than a minute. Minutes rather
// than seconds because a fix is never fresher than the poll that fetched it,
// and a number ticking once a second would read as a live position, which this
// deliberately is not.
function ageLabel(secondsAgo) {
  const minutes = Math.floor(secondsAgo / 60);
  return minutes < 1 ? prose.radar.justNow : prose.radar.lastSeen(minutes);
}

// The dots themselves, in the map's own coordinate space: mounted from MapView
// inside the zoomable content so they pan and scale with the map like the
// circles do. It draws nothing, and asks the server for nothing, unless a
// RadarStrip above it says a radar is running.
export default function RadarLayer({ calculators }) {
  const [{ radarUntil, teamName }, setRadar] = useState(radarState);
  const [contacts, setContacts] = useState([]);

  useEffect(() => {
    setRadar(radarState);
    return subscribeRadar(setRadar);
  }, []);

  const live = useLiveUntil(radarUntil);

  const poll = useCallback(async () => {
    const response = await sendAPIRequest("radar");
    if (!response.ok) return;
    const rows = await response.json();
    // Re-based against this phone's own clock the moment they arrive: the
    // server sends ages rather than timestamps precisely so that the two
    // clocks never have to agree, and this is what lets a contact go on
    // ageing between polls instead of freezing for five seconds at a time.
    const now = Date.now();
    setContacts(
      rows.map((row) => ({ ...row, seenAt: now - 1000 * row.seconds_ago })),
    );
  }, []);

  // One interval for both jobs: fetch the positions again, and re-render so
  // the ages under the dots keep counting up in between.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!live) {
      setContacts([]);
      return undefined;
    }
    poll();
    const handle = setInterval(() => {
      poll();
      setTick((n) => n + 1);
    }, RADAR_POLL_MS);
    return () => clearInterval(handle);
  }, [live, poll]);

  if (!live) return null;

  const now = Date.now();

  return (
    <div className={styles.radarContainer} data-testid="radar-layer">
      {contacts.map((contact, index) => {
        const [x, y] = calculators.coordsToPixels(contact.lat, contact.long);
        if (isNaN(x) || isNaN(y)) return null;

        const secondsAgo = Math.max(0, (now - contact.seenAt) / 1000);
        const alpha = Math.max(
          1 - ((1 - RADAR_MIN_ALPHA) * secondsAgo) / RADAR_TIME_UNTIL_FAINT,
          RADAR_MIN_ALPHA,
        );

        // Colour means certainty here too: grey for anybody not on their feet,
        // and otherwise which side they are on - which nobody can tell by eye
        // any more (roadmap R15), so this is the only place it gets said.
        const alive = contact.state === "alive";
        const colour = !alive
          ? "gray"
          : teamName && contact.team === teamName
            ? "limegreen"
            : "crimson";

        return (
          <React.Fragment key={index}>
            <Dot x={x} y={y} color={colour} alpha={alpha} />
            <span
              className={styles.contactLabel}
              style={{ left: x, bottom: y, opacity: alpha }}
            >
              <span className={styles.contactName}>{contact.name}</span>
              <span className={styles.contactAge}>
                {" "}
                {alive ? ageLabel(secondsAgo) : prose.radar.out}
              </span>
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
}
