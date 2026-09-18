// Pointing the camera at a QR code to find out what it is - and nothing else.
//
// The game's other two scanners both spend what they see: the player's
// collects the item (QRParser.js), and the admin's code list writes a row so
// that card can be switched off (AdminCodes.js). Neither is safe for the
// question an admin actually has mid-game, holding a card found on the floor
// or a poster nobody can remember withdrawing: what is this, and would it
// still work? So this page answers that and writes nothing at all.
//
// It reads join codes too, which the other scanners do not: a team card is
// the one piece of paper on the night whose meaning an admin cannot get at
// any other way, since scanning it with their own phone would move them into
// that team.
//
// House style, like the door kit check: one column, the camera at the top,
// the answer in words underneath.

import React, { useCallback, useRef, useState } from "react";

import { AdminPage } from "./AdminCommon";
import { MyWebcam } from "./MyWebcam";
import useQRScanLoop from "./useQRScanLoop";
import { sendAPIRequest } from "./utils";

import styles from "./AdminScanCode.module.css";

const TONE_STYLES = {
  good: styles.statusGood,
  warn: styles.statusWarn,
  bad: styles.statusBad,
};

function Scanner({ onScan }) {
  const webcamRef = useRef(null);

  useQRScanLoop(webcamRef, onScan);

  return <MyWebcam ref={webcamRef} className={styles.camera} />;
}

// What came back, in the order the question is asked: what it is, whether it
// still works, then the small print. The verdict is a pill in the shared
// tones rather than an icon, so it reads as words on a phone in daylight.
function Identification({ result }) {
  return (
    <section className={styles.panel} aria-label="What that code is">
      <h3 className={styles.headline}>{result.headline}</h3>
      <span
        className={`${styles.status} ${TONE_STYLES[result.verdict.tone] || ""}`}
      >
        {result.verdict.text}
      </span>
      <dl className={styles.facts}>
        {result.facts.map((fact) => (
          <React.Fragment key={fact.label}>
            <dt className={styles.factLabel}>{fact.label}</dt>
            <dd className={styles.factValue}>{fact.value}</dd>
          </React.Fragment>
        ))}
      </dl>
    </section>
  );
}

export function ScanCodePanel() {
  const [scanning, setScanning] = useState(false);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const identify = useCallback((data) => {
    setBusy(true);
    setError(null);
    sendAPIRequest("admin_identify_code", null, "POST", null, { data: data })
      .then(async (response) => {
        if (!response.ok) {
          setError(`Could not read that code (${response.status})`);
          return;
        }
        setResult(await response.json());
      })
      .catch(() => setError("No response from the server"))
      .finally(() => setBusy(false));
  }, []);

  return (
    <>
      <h2>What's this code?</h2>
      <p className={styles.blurb}>
        Scan anything the game prints - an item card, a pub certificate, a
        sandbox poster, a team card or the sign-up link - and this says what it
        is and whether it still works.{" "}
        <b>Nothing is collected and nothing is changed</b>: it is safe to point
        at a card you are about to hide again.
      </p>

      <section className={styles.panel} aria-label="Scan a code">
        {scanning ? <Scanner onScan={identify} /> : null}
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
            identify(pasted.trim());
            setPasted("");
          }}
        >
          Tell me what that is
        </button>
        {error ? (
          <span className={`${styles.status} ${styles.statusBad}`}>
            {error}
          </span>
        ) : null}
      </section>

      {result ? <Identification result={result} /> : null}
    </>
  );
}

export default function AdminScanCode() {
  return (
    <AdminPage>
      <ScanCodePanel />
    </AdminPage>
  );
}
