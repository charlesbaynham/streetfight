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

// Every code minted here carries a batch, so that a whole print run can be
// withdrawn at once later in the evening. The real cards are "game" and are
// never withdrawn; the sandbox's posters are "sandbox" and stop working at
// 16:00.
const DEFAULT_BATCH = "game";

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
  const [damage, setDamage] = useState(1);
  const [timeout, setTimeoutSeconds] = useState(25);
  const [onceOnly, setOnceOnly] = useState(true);
  const [asTeam, setAsTeam] = useState(false);
  const [minutes, setMinutes] = useState(TIMED_TYPES.radar);
  const [batch, setBatch] = useState(DEFAULT_BATCH);

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
        <>
          <Field label="Damage per shot">
            <input
              className={styles.input}
              type="number"
              min="1"
              value={damage}
              onChange={(e) => setDamage(Number(e.target.value))}
            />
          </Field>
          <Field label="Seconds between shots">
            <input
              className={styles.input}
              type="number"
              min="0"
              step="0.5"
              value={timeout}
              onChange={(e) => setTimeoutSeconds(Number(e.target.value))}
            />
          </Field>
        </>
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
      <TeamCards />
      <PubPages />
      <ItemSheets />
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
