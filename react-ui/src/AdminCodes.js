// Switching off one printed code, when withdrawing its whole batch is too
// much (backend/model.py's KnownCode).
//
// The server has no register of what was minted - a code is an HMAC over its
// payload and nothing else, which is exactly what lets a card be printed on
// Thursday for a server deployed on Friday - so there is no list to pick from
// and no way to build one except by pointing a camera at a card that really
// exists. That is what this page is: scan a code to put it on the list, then
// switch it on or off. Everything not on the list works, as it always did.
//
// House style, same as the door kit check: one column of big targets in the
// order the job is done - scan the card in your hand, read what it is, switch
// it off.

import React, { useCallback, useEffect, useRef, useState } from "react";

import { AdminPage } from "./AdminCommon";
import { MyWebcam } from "./MyWebcam";
import useQRScanLoop from "./useQRScanLoop";
import { sendAPIRequest } from "./utils";

import styles from "./AdminCodes.module.css";

// The server sends an epoch second (backend/model.py's KnownCode), so the
// phone reading this is free to be on British time while the droplet is on
// UTC.
function formatScannedAt(epochSeconds) {
  if (!epochSeconds) return null;

  const when = new Date(epochSeconds * 1000);
  if (isNaN(when.getTime())) return null;

  return when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// What a code is, in one line: what it hands out, then the things that decide
// whether switching it off is urgent - an unlimited code is a wall poster, so
// it is being scanned over and over right now.
function CodeSummary({ code }) {
  const scannedAt = formatScannedAt(code.first_seen);

  return (
    <div className={styles.codeSummary}>
      <span className={styles.codeDescription}>{code.description}</span>
      <small className={styles.codeMeta}>
        {code.unlimited ? "infinite · " : ""}
        {code.batch ? `batch "${code.batch}"` : "no batch"}
        {scannedAt ? ` · scanned ${scannedAt}` : ""}
      </small>
    </div>
  );
}

// One row of the list. The switch is the big target and says what it will do
// rather than what the state is - the pill above it says the state - and
// "Forget" is small and last, because it is for a card scanned in by mistake
// rather than a thing anybody does on purpose during a game.
function CodeRow({ code, busy, highlighted, onSetEnabled, onForget }) {
  return (
    <div
      className={`${styles.codeRow} ${highlighted ? styles.highlighted : ""}`}
    >
      <div className={styles.codeHeader}>
        <CodeSummary code={code} />
        <span
          className={`${styles.status} ${
            code.enabled ? styles.statusGood : styles.statusBad
          }`}
        >
          {code.enabled ? "Working" : "Switched off"}
        </span>
      </div>
      <button
        className={code.enabled ? styles.destructive : styles.action}
        disabled={busy}
        onClick={() => onSetEnabled(code.id, !code.enabled)}
      >
        {code.enabled ? "Switch this code off" : "Switch this code back on"}
      </button>
      <button
        className={styles.rowAction}
        disabled={busy}
        onClick={() => onForget(code.id)}
      >
        Forget it
      </button>
    </div>
  );
}

function CodeList({ codes, busy, highlighted, onSetEnabled, onForget }) {
  if (codes === null) {
    return <span className={styles.status}>Checking...</span>;
  }

  if (codes.length === 0) {
    return (
      <p className={styles.hint}>
        Nothing scanned in yet. Every printed code works until one is scanned
        here and switched off.
      </p>
    );
  }

  return (
    <>
      {codes.map((code) => (
        <CodeRow
          key={code.id}
          code={code}
          busy={busy}
          highlighted={code.id === highlighted}
          onSetEnabled={onSetEnabled}
          onForget={onForget}
        />
      ))}
    </>
  );
}

// The camera, only once it has been asked for: this page is also read with no
// card in hand - to switch something back on - and a camera nobody wants is a
// permission prompt and a hot phone.
function Scanner({ onScan }) {
  const webcamRef = useRef(null);

  useQRScanLoop(webcamRef, onScan);

  return <MyWebcam ref={webcamRef} className={styles.camera} />;
}

export function CodesPanel() {
  const [codes, setCodes] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState(null);
  const [highlighted, setHighlighted] = useState(null);

  useEffect(() => {
    sendAPIRequest("admin_known_codes", null, "GET", setCodes);
  }, []);

  const register = useCallback((data) => {
    setBusy(true);
    sendAPIRequest("admin_register_code", null, "POST", null, { data: data })
      .then(async (response) => {
        if (!response.ok) {
          setOutcome({
            good: false,
            // 403 is the only refusal with anything to say: the code is not
            // one of ours, or the camera read half of one.
            text:
              response.status === 403
                ? "That is not a code this server minted."
                : `Could not read that code (${response.status})`,
          });
          return;
        }

        const result = await response.json();
        setCodes(result.codes);
        setHighlighted(result.code.id);
        setOutcome({
          good: true,
          text: result.new
            ? `Added: ${result.code.description}`
            : `Already on the list: ${result.code.description}`,
        });
      })
      .catch(() =>
        setOutcome({ good: false, text: "No response from the server" }),
      )
      .finally(() => setBusy(false));
  }, []);

  const change = useCallback((endpoint, params) => {
    setBusy(true);
    setOutcome(null);
    sendAPIRequest(endpoint, params, "POST", setCodes)
      .then((response) => {
        if (!response.ok) {
          setOutcome({ good: false, text: `Failed (${response.status})` });
        }
      })
      .catch(() =>
        setOutcome({ good: false, text: "No response from the server" }),
      )
      .finally(() => setBusy(false));
  }, []);

  const setEnabled = useCallback(
    (code_id, enabled) =>
      change("admin_set_code_enabled", { code_id, enabled }),
    [change],
  );

  const forget = useCallback(
    (code_id) => change("admin_forget_code", { code_id }),
    [change],
  );

  return (
    <>
      <h2>Item codes</h2>
      <p className={styles.blurb}>
        A printed code cannot be un-printed, and the server has no list of what
        was minted - so a code has to be <b>scanned in here</b> before it can be
        switched off. Anything not on the list below still works. To turn off a
        whole print run at once instead, withdraw its batch on the Printables
        page.
      </p>

      <section className={styles.panel} aria-label="Scan a code">
        <h3 className={styles.panelTitle}>Scan a code</h3>
        <p className={styles.hint}>
          Scanning only puts a code on the list - nothing is collected and
          nobody's inventory changes.
        </p>
        {scanning ? <Scanner onScan={register} /> : null}
        <button
          className={styles.action}
          onClick={() => setScanning((on) => !on)}
        >
          {scanning ? "Stop the camera" : "Scan a code with the camera"}
        </button>
        <div className={styles.field}>
          <label className={styles.fieldLabel} htmlFor="pasted-code">
            Or paste a code
          </label>
          <input
            id="pasted-code"
            className={styles.input}
            type="text"
            value={pasted}
            placeholder="https://... or the raw code"
            onChange={(e) => setPasted(e.target.value)}
          />
        </div>
        <button
          className={styles.action}
          disabled={busy || !pasted.trim()}
          onClick={() => {
            register(pasted.trim());
            setPasted("");
          }}
        >
          Add that code to the list
        </button>
        {outcome ? (
          <span
            className={`${styles.status} ${
              outcome.good ? styles.statusGood : styles.statusBad
            }`}
          >
            {outcome.text}
          </span>
        ) : null}
      </section>

      <section className={styles.panel} aria-label="Scanned codes">
        <h3 className={styles.panelTitle}>Scanned codes</h3>
        <CodeList
          codes={codes}
          busy={busy}
          highlighted={highlighted}
          onSetEnabled={setEnabled}
          onForget={forget}
        />
      </section>
    </>
  );
}

export default function AdminCodes() {
  return (
    <AdminPage>
      <CodesPanel />
    </AdminPage>
  );
}
