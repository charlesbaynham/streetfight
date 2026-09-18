// Everything a game night needs handed out, in one place, built by the
// running server (backend/printables.py, backend/team_cards.py) - the three
// printables, and above them the sign-up link, which is the one that is sent
// rather than printed.
//
// Before this page two of the three printables were CLIs run from a checkout,
// which is the wrong machine: a code is signed with the SECRET_KEY that minted
// it and carries that machine's WEBSITE_URL, so a sheet printed from a stale
// .env is one nobody can scan. Pressing a button here mints the codes on the
// box that will have to honour them.
//
// House style, same as the door kit check: one column of big targets, in the
// order the job is done - choose what to print, press once, read the verdict.
//
// The two minting panels say above the button how many codes a press mints,
// because a second press is a second set of codes rather than a re-download
// of the first - and two sheets for one hiding place is a confusing evening.

import React, { useEffect, useState } from "react";

import { AdminPage, adminDownload } from "./AdminCommon";
import { JoinCard } from "./JoinQRCodes";
import { sendAPIRequest } from "./utils";
import { WEAPONS, WEAPON_LOOT_NAMES } from "./weapons";

import styles from "./AdminPrintables.module.css";

// Ammo is the only item type that can be collected on behalf of a team:
// item_actions._ACTIONS has no team handler for armour, medpacks or weapons,
// so a card asking for one would raise on the first scan.
const TEAM_COLLECTABLE_TYPES = ["ammo"];

const ITEM_TYPES = [
  "ammo",
  "medpack",
  "armour",
  "weapon",
  "radar",
  "circle_warning",
];

// The two items measured in minutes rather than in how much of something they
// award, with the default each one's payload schema carries (backend/items.py).
const TIMED_TYPES = { radar: 5, circle_warning: 10 };

const CARDS_PER_SHEET = 8;

// Mirrors backend/map_poster.py's PAGE_SIZES_MM. Both are A-series, so the
// poster is one design at two scales rather than two layouts.
const POSTER_SIZES = ["A3", "A4"];

// Every code minted here carries a batch, so that a whole print run can be
// withdrawn at once later in the evening. The real cards are "game" and are
// never withdrawn; the sandbox's posters are "sandbox" and stop working at
// 16:00.
const DEFAULT_BATCH = "game";

// How many kinds of poster the sandbox sheet prints - the length of
// backend/printables.py's SANDBOX_CARDS. Only used to say how many codes a
// press mints, which is the one thing that panel warns about.
const SANDBOX_CARD_KINDS = 6;

// The batch the sandbox posters are minted into (backend/printables.py's
// SANDBOX_BATCH), and so the one that gets withdrawn at 16:00.
const SANDBOX_BATCH = "sandbox";

// The games to choose between, newest-first as the server gives them, with
// the first one selected. Two panels need this, so it is a hook rather than a
// copy in each.
function useGameChoice() {
  const [games, setGames] = useState(null);
  const [gameId, setGameId] = useState("");

  useEffect(() => {
    sendAPIRequest("admin_list_games", null, "GET", (loaded) => {
      setGames(loaded);
      if (loaded.length > 0) setGameId((current) => current || loaded[0].id);
    });
  }, []);

  return { games, gameId, setGameId };
}

function GameChooser({ games, gameId, setGameId }) {
  return (
    <>
      <Field label="Game">
        <select
          className={styles.input}
          value={gameId}
          onChange={(e) => setGameId(e.target.value)}
        >
          {(games || []).map((game) => (
            <option key={game.id} value={game.id}>
              {game.id.slice(0, 8)} (
              {game.teams.map((t) => t.name).join(", ") || "no teams"})
            </option>
          ))}
        </select>
      </Field>
      {games && games.length === 0 ? (
        <p className={styles.hint}>No games exist yet - create one first.</p>
      ) : null}
    </>
  );
}

// The sign-up link, which is the one thing here that is *not* printed: it goes
// out over WhatsApp days before the night, so what is wanted is a link to
// paste and a QR to scan off another screen, never a PDF. It needs no teams
// (that is the whole point of R15 - sign up first, team on the night), so it
// comes from /admin_game_join_url rather than the join-code generator, which
// refuses a game with no teams yet.
function SignUpLink() {
  const { games, gameId, setGameId } = useGameChoice();
  const [url, setUrl] = useState(null);

  useEffect(() => {
    setUrl(null);
    if (!gameId) return;
    sendAPIRequest("admin_game_join_url", { game_id: gameId }, "GET", (data) =>
      setUrl(data.game_url),
    );
  }, [gameId]);

  return (
    <section className={styles.panel} aria-label="Sign-up link">
      <h3 className={styles.panelTitle}>Sign-up link</h3>
      <p className={styles.blurb}>
        The link everybody gets before the night: it takes them through picking
        a name and an outfit, and leaves them in the game with no team. They
        scan a team card at the door to get a team.
      </p>
      <GameChooser games={games} gameId={gameId} setGameId={setGameId} />
      {url ? (
        <div className={styles.signupCard}>
          <JoinCard label="the game" url={url} title="Sign up" />
        </div>
      ) : null}
    </section>
  );
}

// One printable: what it is, the controls for it, and what happened last time
// the button was pressed. The verdict is words rather than a colour alone -
// green for a file that arrived, red for one that did not.
function Printable({ title, children, blurb, warning, action, label, ready }) {
  const [state, setState] = useState(null); // null | "working" | {ok, text}

  const run = () => {
    setState("working");
    action().then(
      (response) =>
        setState(
          response.ok
            ? { ok: true, text: "Downloaded - check your downloads folder" }
            : { ok: false, text: `Failed (${response.status})` },
        ),
      () =>
        setState({ ok: false, text: "Failed - no response from the server" }),
    );
  };

  return (
    <section className={styles.panel} aria-label={title}>
      <h3 className={styles.panelTitle}>{title}</h3>
      <p className={styles.blurb}>{blurb}</p>
      {children}
      {warning ? <p className={styles.warning}>{warning}</p> : null}
      <button
        className={styles.action}
        onClick={run}
        disabled={state === "working" || !ready}
      >
        {state === "working" ? "Building..." : label}
      </button>
      {state && state !== "working" ? (
        <span
          className={`${styles.status} ${
            state.ok ? styles.statusGood : styles.statusBad
          }`}
        >
          {state.text}
        </span>
      ) : null}
    </section>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className={styles.field}>
      <span className={styles.fieldLabel}>{label}</span>
      {children}
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </label>
  );
}

// The label minted into every code a press produces. It goes last in every
// panel because it is the field nobody changes: "game" is right for everything
// printed for the night itself.
function BatchField({ batch, setBatch }) {
  return (
    <Field
      label="Batch"
      hint="Minted into every code, so this run can be withdrawn as a set. Leave it as 'game' for the real cards."
    >
      <input
        className={styles.input}
        type="text"
        value={batch}
        onChange={(e) => setBatch(e.target.value)}
      />
    </Field>
  );
}

// The venue map on one sheet, with a numbered legend of the pubs. A GET like
// the team cards, and for a stronger reason: it mints nothing at all, it just
// draws what backend/venues.py already says.
function MapPoster() {
  const [size, setSize] = useState("A3");

  return (
    <Printable
      title="Map poster"
      blurb="The map to pin up in the pub, with every pub on it numbered and named underneath. No circles, no drop locations - players read this one."
      label="Download map poster (PDF)"
      ready={true}
      action={() =>
        adminDownload(
          "admin_map_poster_pdf",
          { size: size },
          `map_poster_${size.toLowerCase()}.pdf`,
          "GET",
        )
      }
    >
      <Field label="Paper" hint="A3 is the one to put on a wall.">
        <select
          className={styles.input}
          value={size}
          onChange={(e) => setSize(e.target.value)}
        >
          {POSTER_SIZES.map((paper) => (
            <option key={paper} value={paper}>
              {paper}
            </option>
          ))}
        </select>
      </Field>
    </Printable>
  );
}

// One A4 page per team, carrying that team's door code. No side effects worth
// worrying about, so this one is a GET.
function TeamCards() {
  const { games, gameId, setGameId } = useGameChoice();

  return (
    <Printable
      title="Team cards"
      blurb="One A4 notice of conscription per team, carrying that team's door code. Players scan it on the night to join a team."
      label="Download team cards (PDF)"
      ready={Boolean(gameId)}
      action={() =>
        adminDownload(
          "admin_team_cards_pdf",
          { game_id: gameId },
          "team_cards.pdf",
          "GET",
        )
      }
    >
      <GameChooser games={games} gameId={gameId} setGameId={setGameId} />
    </Printable>
  );
}

function PubPages() {
  const [count, setCount] = useState(6);
  const [bullets, setBullets] = useState(5);
  const [batch, setBatch] = useState(DEFAULT_BATCH);

  return (
    <Printable
      title="Pub certificates"
      blurb="One A4 poster per pub, each with a single ammo code the first team to scan it collects for every one of its members. The pages are anonymous, so deal them out in any order."
      warning={`Mints ${count} new code${count === 1 ? "" : "s"} when you press this.`}
      label="Mint and download (PDF)"
      ready={count >= 1}
      action={() =>
        adminDownload(
          "admin_pub_pages_pdf",
          { count: count, num_bullets: bullets, batch: batch },
          "pub_pages.pdf",
        )
      }
    >
      <Field label="Pages (one per pub)">
        <input
          className={styles.input}
          type="number"
          min="1"
          max="40"
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
        />
      </Field>
      <Field label="Bullets per team member">
        <input
          className={styles.input}
          type="number"
          min="1"
          value={bullets}
          onChange={(e) => setBullets(Number(e.target.value))}
        />
      </Field>
      <BatchField batch={batch} setBatch={setBatch} />
    </Printable>
  );
}

function ItemSheets() {
  const [itype, setItype] = useState("ammo");
  const [num, setNum] = useState(5);
  const [sheets, setSheets] = useState(1);
  const [weapon, setWeapon] = useState(WEAPON_LOOT_NAMES[0]);
  const [onceOnly, setOnceOnly] = useState(true);
  const [asTeam, setAsTeam] = useState(false);
  const [minutes, setMinutes] = useState(TIMED_TYPES.radar);
  const [batch, setBatch] = useState(DEFAULT_BATCH);

  // A weapon card is one of the named weapons, chosen the same way as on the
  // per-player select and the one-off item page; the stats are what the card
  // encodes, not something to type.
  const [damage, timeout] = WEAPONS[weapon];

  const teamable = TEAM_COLLECTABLE_TYPES.includes(itype);
  const timed = itype in TIMED_TYPES;
  const cards = sheets * CARDS_PER_SHEET;

  return (
    <Printable
      title="Drop cards"
      blurb={`Landscape A4 sheets of ${CARDS_PER_SHEET} item codes, to be cut up and hidden around the town. Every card is a distinct item.`}
      warning={`Mints ${cards} new code${cards === 1 ? "" : "s"} when you press this.`}
      label="Mint and download (PDF)"
      ready={sheets >= 1}
      action={() =>
        adminDownload(
          "admin_item_sheets_pdf",
          {
            itype: itype,
            num: num,
            sheets: sheets,
            damage: damage,
            timeout: timeout,
            collected_only_once: onceOnly,
            collected_as_team: teamable && asTeam,
            batch: batch,
            ...(timed ? { minutes: minutes } : {}),
          },
          `item_cards_${itype}.pdf`,
        )
      }
    >
      <Field label="Item">
        <select
          className={styles.input}
          value={itype}
          onChange={(e) => {
            const chosen = e.target.value;
            setItype(chosen);
            if (!TEAM_COLLECTABLE_TYPES.includes(chosen)) setAsTeam(false);
            if (chosen in TIMED_TYPES) setMinutes(TIMED_TYPES[chosen]);
          }}
        >
          {ITEM_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </Field>
      <Field
        label="Amount per card"
        hint="Bullets, hit points or armour - ignored for weapons."
      >
        <input
          className={styles.input}
          type="number"
          min="1"
          value={num}
          onChange={(e) => setNum(Number(e.target.value))}
        />
      </Field>
      {timed ? (
        <Field label="Minutes it lasts">
          <input
            className={styles.input}
            type="number"
            min="1"
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
          />
        </Field>
      ) : null}
      {itype === "weapon" ? (
        <Field
          label="Weapon"
          hint={`${damage} damage per shot, one shot every ${timeout}s.`}
        >
          <select
            className={styles.input}
            value={weapon}
            onChange={(e) => setWeapon(e.target.value)}
          >
            {WEAPON_LOOT_NAMES.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </Field>
      ) : null}
      <Field label={`Sheets (${cards} cards)`}>
        <input
          className={styles.input}
          type="number"
          min="1"
          max="20"
          value={sheets}
          onChange={(e) => setSheets(Number(e.target.value))}
        />
      </Field>
      <label className={styles.toggle}>
        <input
          type="checkbox"
          checked={onceOnly}
          onChange={(e) => setOnceOnly(e.target.checked)}
        />{" "}
        Each card can only ever be collected once
      </label>
      <label className={styles.toggle}>
        <input
          type="checkbox"
          checked={asTeam}
          disabled={!teamable}
          onChange={(e) => setAsTeam(e.target.checked)}
        />{" "}
        Collected for the whole team
        {teamable ? null : (
          <span className={styles.hint}> - only ammo can be</span>
        )}
      </label>
      <BatchField batch={batch} setBatch={setBatch} />
    </Printable>
  );
}

// The warm-up room's walls. Everything on them is unlimited and everything is
// in one batch, which is the whole point: a player scans the ammunition poster
// as often as they like, and the room stops working in a single press at 16:00.
// No controls but how many copies - what the posters *are* is decided in
// backend/printables.py's SANDBOX_CARDS, so that the paper and the codes
// cannot disagree.
//
// One A4 page per poster, and the word INFINITE across the top of each: the
// drawing on an unlimited code is the same drawing as on a card to be hidden
// round the town, so without the word a sandbox poster is one that can be
// shuffled into the box by mistake.
function SandboxSheets() {
  const [copies, setCopies] = useState(1);

  const pages = copies * SANDBOX_CARD_KINDS;

  return (
    <Printable
      title="Sandbox posters"
      blurb={`The warm-up room: ammunition, level 2 armour, a med pack and three weapons, one A4 page each, headed "INFINITE". Every one can be scanned again and again by the same player, so they work as posters on a wall.`}
      warning={`Prints ${pages} page${pages === 1 ? "" : "s"}, and mints ${SANDBOX_CARD_KINDS} new codes - one per poster. Withdraw the "sandbox" batch at 16:00 to turn them all off.`}
      label="Mint and download (PDF)"
      ready={copies >= 1}
      action={() =>
        adminDownload(
          "admin_sandbox_sheets_pdf",
          { copies: copies },
          "sandbox_sheets.pdf",
        )
      }
    >
      <Field label="Copies of each poster" hint="One A4 page per copy.">
        <input
          className={styles.input}
          type="number"
          min="1"
          max="5"
          value={copies}
          onChange={(e) => setCopies(Number(e.target.value))}
        />
      </Field>
    </Printable>
  );
}

// The only recall a printed code has. A card cannot be un-printed and
// rotating SECRET_KEY would take the team cards with it, so every code is
// minted carrying a batch and this turns one off: the sandbox's posters stop
// working at 16:00 while the game's own cards carry on.
//
// Not a Printable - nothing is built and nothing is downloaded - but the same
// shape: one field, one big button, and the state said in words underneath.
// The button names the batch it is about to withdraw, and a batch that is not
// the sandbox gets a warning first: mistyping "game" here at 16:00 would turn
// off every card in the town. It is one press rather than two because the way
// back is right there in the list below it.
function WithdrawCodes() {
  const [batch, setBatch] = useState(SANDBOX_BATCH);
  const [revoked, setRevoked] = useState(null);
  const [failure, setFailure] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    sendAPIRequest("admin_revoked_batches", null, "GET", setRevoked);
  }, []);

  const named = batch.trim();

  const change = (endpoint, which) => {
    setBusy(true);
    setFailure(null);
    sendAPIRequest(endpoint, { batch: which }, "POST", setRevoked)
      .then((response) => {
        if (!response.ok) setFailure(`Failed (${response.status})`);
      })
      .catch(() => setFailure("Failed - no response from the server"))
      .finally(() => setBusy(false));
  };

  return (
    <section className={styles.panel} aria-label="Withdraw codes">
      <h3 className={styles.panelTitle}>Withdraw codes</h3>
      <p className={styles.blurb}>
        Stops every code minted into a batch from working, wherever the paper
        has got to. Withdraw <b>{SANDBOX_BATCH}</b> at 16:00 to close the
        warm-up room. Codes minted before batches existed carry none and cannot
        be withdrawn this way.
      </p>
      <Field label="Batch">
        <input
          className={styles.input}
          type="text"
          value={batch}
          onChange={(e) => setBatch(e.target.value)}
        />
      </Field>
      {named && named !== SANDBOX_BATCH ? (
        <p className={styles.warning}>
          "{named}" is not the sandbox. Every card in the town minted into it
          stops working.
        </p>
      ) : null}
      <button
        className={styles.destructive}
        onClick={() => change("admin_withdraw_batch", named)}
        disabled={busy || !named}
      >
        {busy ? "Working..." : `Withdraw "${named || "..."}"`}
      </button>
      {failure ? (
        <span className={`${styles.status} ${styles.statusBad}`}>
          {failure}
        </span>
      ) : null}
      <WithdrawnBatches revoked={revoked} busy={busy} onRestore={change} />
    </section>
  );
}

// What is withdrawn right now, in words rather than by the absence of a list -
// "nothing is withdrawn" and "we have not asked yet" are different states, and
// an admin at 16:00 needs to know which one they are looking at.
function WithdrawnBatches({ revoked, busy, onRestore }) {
  if (revoked === null) {
    return <span className={styles.status}>Checking...</span>;
  }

  if (revoked.length === 0) {
    return (
      <p className={styles.hint}>
        Nothing is withdrawn - every code minted still works.
      </p>
    );
  }

  return (
    <>
      <p className={styles.hint}>Withdrawn:</p>
      {revoked.map((entry) => (
        <div className={styles.batchRow} key={entry.batch}>
          <span className={styles.batchName}>{entry.batch}</span>
          <button
            className={styles.rowAction}
            disabled={busy}
            onClick={() => onRestore("admin_restore_batch", entry.batch)}
          >
            Allow again
          </button>
        </div>
      ))}
    </>
  );
}

export function PrintablesPanel() {
  return (
    <>
      <h2>Printables</h2>
      <p className={styles.blurb}>
        Print at <b>actual size</b>, not "fit to page" - the QR codes are sized
        in millimetres so they scan from across a room. The sign-up link at the
        top is the exception: it is sent, not printed.
      </p>
      <SignUpLink />
      <MapPoster />
      <TeamCards />
      <PubPages />
      <ItemSheets />
      <SandboxSheets />
      <WithdrawCodes />
    </>
  );
}

export default function AdminPrintables() {
  return (
    <AdminPage>
      <PrintablesPanel />
    </AdminPage>
  );
}
