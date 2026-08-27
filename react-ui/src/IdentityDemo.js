// Admin sandbox for the colour-code player-identification scheme.
//
// Deliberately ugly: this is a workbench for me, not a player-facing view. It
// lets you build a scheme, type in a reading as if the (not yet existing)
// image recognition had produced it, decode it, and run a Monte-Carlo
// simulation to compare schemes.

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { sendAPIRequest } from "./utils";

async function postJSON(endpoint, body) {
  const response = await sendAPIRequest(endpoint, null, "POST", null, body);
  let data = null;
  try {
    data = await response.json();
  } catch (e) {
    data = null;
  }
  if (!response.ok) {
    if (response.status === 403) {
      throw new Error("Not logged in as admin - go to /admin/login first");
    }
    const detail = data && data.detail;
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail || data),
    );
  }
  return data;
}

function splitList(text) {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

// "red:0.6, blue:0.4" -> {red: 0.6, blue: 0.4}
function parseDistribution(text) {
  const out = {};
  splitList(text).forEach((entry) => {
    const [label, weight] = entry.split(":");
    if (label === undefined) return;
    out[label.trim()] = weight === undefined ? 1 : parseFloat(weight);
  });
  return out;
}

function pct(x) {
  return `${(100 * x).toFixed(2)}%`;
}

const cell = { border: "1px solid #ccc", padding: "2px 6px" };
const table = { borderCollapse: "collapse", marginBottom: "1em" };
const panel = {
  border: "1px solid #999",
  padding: "0.5em",
  marginBottom: "1em",
};
const errorStyle = { color: "red", whiteSpace: "pre-wrap" };
const unwearableStyle = { ...cell, color: "#999" };

// The backend sends appearance = null for a codeword a restricted channel has
// no colour for: the algebra is fine, but nobody could be wearing it. Render a
// dash rather than reading through the null.
function AppearanceCells({ appearance, channels }) {
  return channels.map((c) => (
    <td key={c.name} style={appearance ? cell : unwearableStyle}>
      {appearance ? appearance[c.name] : "—"}
    </td>
  ));
}

function SchemeEditor({ spec, setSpec }) {
  const setChannel = (idx, patch) => {
    const channels = spec.channels.map((c, i) =>
      i === idx ? { ...c, ...patch } : c,
    );
    setSpec({ ...spec, channels });
  };

  return (
    <div style={panel}>
      <h3>1. Scheme</h3>

      <div>
        <label>
          Palette (comma separated):{" "}
          <input
            size={60}
            value={spec.paletteText}
            onChange={(e) => setSpec({ ...spec, paletteText: e.target.value })}
          />
        </label>
      </div>

      <div>
        <label>
          q (field size, blank = palette length):{" "}
          <input
            size={4}
            value={spec.qText}
            onChange={(e) => setSpec({ ...spec, qText: e.target.value })}
          />
        </label>{" "}
        <small>
          must be prime; set below the palette length to keep spare colours
        </small>
      </div>

      <h4>Channels</h4>
      <table style={table}>
        <thead>
          <tr>
            <th style={cell}>#</th>
            <th style={cell}>name</th>
            <th style={cell}>labels (blank = palette)</th>
            <th style={cell}></th>
          </tr>
        </thead>
        <tbody>
          {spec.channels.map((channel, idx) => (
            <tr key={idx}>
              <td style={cell}>{idx}</td>
              <td style={cell}>
                <input
                  value={channel.name}
                  onChange={(e) => setChannel(idx, { name: e.target.value })}
                />
              </td>
              <td style={cell}>
                <input
                  size={40}
                  value={channel.labelsText}
                  onChange={(e) =>
                    setChannel(idx, { labelsText: e.target.value })
                  }
                />
              </td>
              <td style={cell}>
                <button
                  onClick={() =>
                    setSpec({
                      ...spec,
                      channels: spec.channels.filter((_, i) => i !== idx),
                    })
                  }
                >
                  remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        onClick={() =>
          setSpec({
            ...spec,
            channels: [
              ...spec.channels,
              { name: `channel${spec.channels.length + 1}`, labelsText: "" },
            ],
          })
        }
      >
        add channel
      </button>

      <h4>Code</h4>
      <div>
        <label>
          type:{" "}
          <select
            value={spec.code_type}
            onChange={(e) => setSpec({ ...spec, code_type: e.target.value })}
          >
            <option value="auto">auto (simplest reaching distance)</option>
            <option value="parity">parity [n, n-1, 2]</option>
            <option value="reed_solomon">reed_solomon [n, k, n-k+1]</option>
          </select>
        </label>{" "}
        <label>
          target distance d:{" "}
          <input
            size={3}
            value={spec.target_distanceText}
            onChange={(e) =>
              setSpec({ ...spec, target_distanceText: e.target.value })
            }
          />
        </label>{" "}
        <label>
          k:{" "}
          <input
            size={3}
            value={spec.kText}
            onChange={(e) => setSpec({ ...spec, kText: e.target.value })}
          />
        </label>{" "}
        <small>parity ignores both; auto uses d (or derives it from k)</small>
      </div>
    </div>
  );
}

function SchemeSummary({ info }) {
  if (!info) return null;
  return (
    <div style={panel}>
      <h3>Scheme built</h3>
      <p>
        <b>
          [n={info.n}, k={info.k}, d={info.min_distance}] over GF({info.q})
        </b>{" "}
        ({info.code_type}, d {info.min_distance_source}) &mdash; capacity{" "}
        <b>{info.capacity}</b> players
      </p>
      <p>{info.guarantees.summary}</p>
      <p>
        <b>{info.usable_capacity}</b> of those slots are actually assignable:
        the rest ask a restricted channel for a colour it doesn&apos;t have (or
        are slot 0, all-black).
      </p>

      <details>
        <summary>
          Codebook ({info.codebook.length} rows
          {info.codebook_truncated ? ", truncated" : ""})
        </summary>
        <table style={table}>
          <thead>
            <tr>
              <th style={cell}>slot</th>
              <th style={cell}>codeword</th>
              <th style={cell}>wearable</th>
              {info.channels.map((c) => (
                <th key={c.name} style={cell}>
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {info.codebook.map((row) => (
              <tr key={row.slot}>
                <td style={cell}>{row.slot}</td>
                <td style={cell}>{row.codeword.join(" ")}</td>
                <td style={row.wearable ? cell : unwearableStyle}>
                  {row.wearable ? "yes" : "no"}
                </td>
                <AppearanceCells
                  appearance={row.appearance}
                  channels={info.channels}
                />
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function CandidateEditor({ candidates, setCandidates, capacity }) {
  const [count, setCount] = useState("10");

  const regenerate = () => {
    const n = Math.max(0, Math.min(parseInt(count, 10) || 0, capacity || 0));
    setCandidates(
      Array.from({ length: n }, (_, i) => ({
        name: `player${i}`,
        slot: String(i),
        prior: "",
      })),
    );
  };

  const setCandidate = (idx, patch) =>
    setCandidates(
      candidates.map((c, i) => (i === idx ? { ...c, ...patch } : c)),
    );

  return (
    <div style={panel}>
      <h3>2. Players in play</h3>
      <p>
        <small>
          These are the candidates the decoder ranks (in the real game: alive
          players on other teams). Priors are optional relative weights, e.g.
          from GPS proximity; blank = uniform.
        </small>
      </p>
      <label>
        count:{" "}
        <input
          size={4}
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
      </label>{" "}
      <button onClick={regenerate}>regenerate slots 0..n-1</button>{" "}
      <span>capacity = {capacity === null ? "?" : capacity}</span>
      <table style={table}>
        <thead>
          <tr>
            <th style={cell}>name</th>
            <th style={cell}>slot</th>
            <th style={cell}>prior</th>
            <th style={cell}></th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate, idx) => (
            <tr key={idx}>
              <td style={cell}>
                <input
                  size={12}
                  value={candidate.name}
                  onChange={(e) => setCandidate(idx, { name: e.target.value })}
                />
              </td>
              <td style={cell}>
                <input
                  size={4}
                  value={candidate.slot}
                  onChange={(e) => setCandidate(idx, { slot: e.target.value })}
                />
              </td>
              <td style={cell}>
                <input
                  size={6}
                  value={candidate.prior}
                  onChange={(e) => setCandidate(idx, { prior: e.target.value })}
                />
              </td>
              <td style={cell}>
                <button
                  onClick={() =>
                    setCandidates(candidates.filter((_, i) => i !== idx))
                  }
                >
                  remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        onClick={() =>
          setCandidates([
            ...candidates,
            { name: `player${candidates.length}`, slot: "0", prior: "" },
          ])
        }
      >
        add player
      </button>
    </div>
  );
}

function ReadingEditor({ info, reading, setReading, onLoadSlot }) {
  const [slotToLoad, setSlotToLoad] = useState("0");

  if (!info) return null;

  const setObservation = (idx, patch) =>
    setReading(reading.map((o, i) => (i === idx ? { ...o, ...patch } : o)));

  return (
    <div style={panel}>
      <h3>3. Reading (pretend this came from the image recognition)</h3>
      <p>
        <small>
          Pick what the vision model "saw" per channel. best_guess = one symbol
          with a confidence; distribution = "red:0.6, blue:0.4"; erasure = the
          channel was obscured.
        </small>
      </p>

      <div style={{ marginBottom: "0.5em" }}>
        <label>
          Load the true appearance of slot{" "}
          <input
            size={4}
            value={slotToLoad}
            onChange={(e) => setSlotToLoad(e.target.value)}
          />
        </label>{" "}
        <button onClick={() => onLoadSlot(parseInt(slotToLoad, 10))}>
          load
        </button>{" "}
        <small>then corrupt a channel or two by hand</small>
      </div>

      <table style={table}>
        <thead>
          <tr>
            <th style={cell}>channel</th>
            <th style={cell}>kind</th>
            <th style={cell}>symbol / distribution</th>
            <th style={cell}>confidence</th>
          </tr>
        </thead>
        <tbody>
          {info.channels.map((channel, idx) => {
            const obs = reading[idx] || {};
            return (
              <tr key={channel.name}>
                <td style={cell}>{channel.name}</td>
                <td style={cell}>
                  <select
                    value={obs.kind || "best_guess"}
                    onChange={(e) =>
                      setObservation(idx, { kind: e.target.value })
                    }
                  >
                    <option value="best_guess">best_guess</option>
                    <option value="erasure">erasure</option>
                    <option value="distribution">distribution</option>
                  </select>
                </td>
                <td style={cell}>
                  {obs.kind === "erasure" ? (
                    <i>unreadable</i>
                  ) : obs.kind === "distribution" ? (
                    <input
                      size={40}
                      value={obs.distributionText || ""}
                      placeholder="red:0.6, blue:0.4"
                      onChange={(e) =>
                        setObservation(idx, {
                          distributionText: e.target.value,
                        })
                      }
                    />
                  ) : (
                    <select
                      value={obs.symbol || channel.labels[0]}
                      onChange={(e) =>
                        setObservation(idx, { symbol: e.target.value })
                      }
                    >
                      {channel.labels.map((label) => (
                        <option key={label} value={label}>
                          {label}
                        </option>
                      ))}
                    </select>
                  )}
                </td>
                <td style={cell}>
                  {obs.kind === "best_guess" || obs.kind === undefined ? (
                    <input
                      size={6}
                      value={
                        obs.confidence === undefined ? "0.9" : obs.confidence
                      }
                      onChange={(e) =>
                        setObservation(idx, { confidence: e.target.value })
                      }
                    />
                  ) : (
                    <i>n/a</i>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DecodeResultView({ result, info }) {
  if (!result) return null;

  const flag = (name, value, bad) => (
    <span
      style={{
        marginRight: "1em",
        fontWeight: "bold",
        color: value === bad ? "red" : "green",
      }}
    >
      {name}: {String(value)}
    </span>
  );

  return (
    <div style={panel}>
      <h3>Decode result</h3>
      <p>
        Best: <b>{result.best === null ? "(none)" : result.best}</b> with
        posterior {result.best_posterior.toFixed(4)}
      </p>
      <p>
        {flag("confident", result.confident, false)}
        {flag("ambiguous", result.ambiguous, true)}
        {flag("inconsistent", result.inconsistent, true)}
        {flag("auto_accept", result.auto_accept, false)}
      </p>
      <p>
        Hard decision:{" "}
        <code>
          {result.hard_reading
            .map((label) => (label === null ? "?" : label))
            .join(" / ")}
        </code>{" "}
        &mdash; valid codeword:{" "}
        {result.hard_reading_is_codeword === null
          ? "n/a (erasures)"
          : String(result.hard_reading_is_codeword)}
        . Erasures: {result.num_erasures}. Distance to nearest candidate:{" "}
        {String(result.min_distance_to_codeword)} (code d ={" "}
        {result.code_min_distance}).
      </p>
      <table style={table}>
        <thead>
          <tr>
            <th style={cell}>rank</th>
            <th style={cell}>player</th>
            <th style={cell}>slot</th>
            <th style={cell}>posterior</th>
            <th style={cell}>distance</th>
            <th style={cell}>codeword</th>
            {info.channels.map((c) => (
              <th key={c.name} style={cell}>
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.ranked.map((row, idx) => (
            <tr key={row.name}>
              <td style={cell}>{idx + 1}</td>
              <td style={cell}>{row.name}</td>
              <td style={cell}>{row.slot}</td>
              <td style={cell}>{row.posterior.toFixed(4)}</td>
              <td style={cell}>{row.distance}</td>
              <td style={cell}>{row.codeword.join(" ")}</td>
              <AppearanceCells
                appearance={row.appearance}
                channels={info.channels}
              />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SimulationPanel({ schemeSpec, thresholds, candidates }) {
  const [params, setParams] = useState({
    trials: "2000",
    num_players: "10",
    p_erasure: "0.1",
    p_misread: "0.1",
    confidence: "0.8",
    seed: "0",
    useCandidates: false,
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const data = await postJSON("admin_identity_simulate", {
        scheme: schemeSpec,
        thresholds,
        trials: parseInt(params.trials, 10),
        num_players: parseInt(params.num_players, 10),
        p_erasure: parseFloat(params.p_erasure),
        p_misread: parseFloat(params.p_misread),
        confidence: parseFloat(params.confidence),
        seed: parseInt(params.seed, 10),
        candidates: params.useCandidates ? candidates : null,
      });
      setResult(data);
    } catch (e) {
      setResult(null);
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const field = (name, label) => (
    <label style={{ marginRight: "1em" }}>
      {label}:{" "}
      <input
        size={6}
        value={params[name]}
        onChange={(e) => setParams({ ...params, [name]: e.target.value })}
      />
    </label>
  );

  return (
    <div style={panel}>
      <h3>5. Simulation</h3>
      <p>
        <small>
          Corrupt each channel independently (erasure with p_erasure, else a
          wrong colour with p_misread) and decode. The number that matters is{" "}
          <b>error given auto-accept</b>: how often the decoder is confident,
          unflagged, and wrong.
        </small>
      </p>
      <div>
        {field("trials", "trials")}
        {field("num_players", "players")}
        {field("p_erasure", "p_erasure")}
        {field("p_misread", "p_misread")}
        {field("confidence", "confidence")}
        {field("seed", "seed")}
        <label style={{ marginRight: "1em" }}>
          <input
            type="checkbox"
            checked={params.useCandidates}
            onChange={(e) =>
              setParams({ ...params, useCandidates: e.target.checked })
            }
          />{" "}
          use the player list above instead of slots 0..n-1
        </label>
        <button onClick={run} disabled={running}>
          {running ? "running..." : "run simulation"}
        </button>
      </div>

      {error ? <p style={errorStyle}>{error}</p> : null}

      {result ? (
        <>
          <h4>
            Rates over {result.counts.trials} trials, {result.num_candidates}{" "}
            candidates, code d = {result.code_min_distance}
          </h4>
          <table style={table}>
            <tbody>
              <tr>
                <td style={cell}>top-ranked player correct</td>
                <td style={cell}>{pct(result.rates.top_correct)}</td>
              </tr>
              <tr>
                <td style={cell}>auto-accepted (confident, unflagged)</td>
                <td style={cell}>{pct(result.rates.auto_accept)}</td>
              </tr>
              <tr>
                <td style={cell}>
                  <b>auto-accepted AND wrong (silent failures)</b>
                </td>
                <td style={cell}>
                  <b>{pct(result.rates.auto_accept_wrong)}</b>
                </td>
              </tr>
              <tr>
                <td style={cell}>
                  <b>error given auto-accept</b>
                </td>
                <td style={cell}>
                  <b>{pct(result.rates.error_given_auto_accept)}</b>
                </td>
              </tr>
              <tr>
                <td style={cell}>flagged for admin review</td>
                <td style={cell}>{pct(result.rates.flagged)}</td>
              </tr>
              <tr>
                <td style={cell}>flagged inconsistent</td>
                <td style={cell}>{pct(result.rates.inconsistent)}</td>
              </tr>
              <tr>
                <td style={cell}>flagged ambiguous</td>
                <td style={cell}>{pct(result.rates.ambiguous)}</td>
              </tr>
            </tbody>
          </table>

          <details>
            <summary>raw counts</summary>
            <pre>{JSON.stringify(result.counts, null, 2)}</pre>
          </details>

          {result.silent_failure_examples.length > 0 ? (
            <details open>
              <summary>
                example silent failures ({result.silent_failure_examples.length}
                )
              </summary>
              <table style={table}>
                <thead>
                  <tr>
                    <th style={cell}>true player</th>
                    <th style={cell}>true codeword</th>
                    <th style={cell}>seen</th>
                    <th style={cell}>decoded as</th>
                    <th style={cell}>posterior</th>
                    <th style={cell}>erasures</th>
                    <th style={cell}>misreads</th>
                  </tr>
                </thead>
                <tbody>
                  {result.silent_failure_examples.map((example, idx) => (
                    <tr key={idx}>
                      <td style={cell}>{example.true_name}</td>
                      <td style={cell}>{example.true_codeword.join(" ")}</td>
                      <td style={cell}>
                        {example.seen
                          .map((label) => (label === null ? "?" : label))
                          .join(" / ")}
                      </td>
                      <td style={cell}>{example.decoded_as}</td>
                      <td style={cell}>{example.posterior.toFixed(3)}</td>
                      <td style={cell}>{example.num_erasures}</td>
                      <td style={cell}>{example.num_misreads}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export default function IdentityDemo() {
  const [spec, setSpec] = useState(null);
  const [thresholdsText, setThresholdsText] = useState({
    confident_threshold: "0.6",
    ambiguous_margin: "0.15",
    epsilon: "0.000001",
  });
  const [info, setInfo] = useState(null);
  const [schemeError, setSchemeError] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [reading, setReading] = useState([]);
  const [decodeResult, setDecodeResult] = useState(null);
  const [decodeError, setDecodeError] = useState(null);

  // Start from the real config defaults so the demo reflects the game's scheme.
  useEffect(() => {
    sendAPIRequest("admin_identity_defaults", null, "GET", (defaults) => {
      setSpec({
        paletteText: defaults.palette.join(", "),
        qText: "",
        channels: defaults.channels.map(({ name, labels }) => ({
          name,
          // Blank means "use the palette"; only a channel with an alphabet of
          // its own carries an explicit one.
          labelsText: labels ? labels.join(", ") : "",
        })),
        code_type: "auto",
        target_distanceText: String(defaults.target_distance),
        kText: "",
      });
      setThresholdsText({
        confident_threshold: String(defaults.thresholds.confident_threshold),
        ambiguous_margin: String(defaults.thresholds.ambiguous_margin),
        epsilon: String(defaults.thresholds.epsilon),
      });
      setCandidates(
        Array.from({ length: 10 }, (_, i) => ({
          name: `player${i}`,
          slot: String(i),
          prior: "",
        })),
      );
    });
  }, []);

  // The wire format the backend expects, derived from the editor's text fields.
  const schemeSpec = useMemo(() => {
    if (!spec) return null;
    const palette = splitList(spec.paletteText);
    return {
      palette,
      channels: spec.channels.map((c) => ({
        name: c.name,
        labels: splitList(c.labelsText).length ? splitList(c.labelsText) : null,
      })),
      code_type: spec.code_type,
      target_distance:
        spec.target_distanceText === ""
          ? null
          : parseInt(spec.target_distanceText, 10),
      k: spec.kText === "" ? null : parseInt(spec.kText, 10),
      q: spec.qText === "" ? null : parseInt(spec.qText, 10),
    };
  }, [spec]);

  const thresholds = useMemo(
    () => ({
      confident_threshold: parseFloat(thresholdsText.confident_threshold),
      ambiguous_margin: parseFloat(thresholdsText.ambiguous_margin),
      epsilon: parseFloat(thresholdsText.epsilon),
    }),
    [thresholdsText],
  );

  // Rebuild the scheme (debounced) whenever the editor changes.
  const schemeSpecJSON = JSON.stringify(schemeSpec);
  useEffect(() => {
    if (!schemeSpec) return undefined;
    const handle = setTimeout(() => {
      postJSON("admin_identity_scheme", schemeSpec)
        .then((data) => {
          setInfo(data);
          setSchemeError(null);
        })
        .catch((e) => {
          setInfo(null);
          setSchemeError(e.message);
        });
    }, 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schemeSpecJSON]);

  // Keep the reading the same length as the channel list.
  useEffect(() => {
    if (!info) return;
    setReading((old) =>
      info.channels.map((channel, idx) => {
        const previous = old[idx];
        const stillValid =
          previous &&
          (previous.kind !== "best_guess" ||
            channel.labels.includes(previous.symbol));
        if (stillValid) return previous;
        return {
          kind: "best_guess",
          symbol: channel.labels[0],
          confidence: "0.9",
          distributionText: "",
        };
      }),
    );
  }, [info]);

  const loadSlot = useCallback(
    (slot) => {
      if (!info) return;
      const row = info.codebook.find((r) => r.slot === slot);
      if (!row) {
        setDecodeError(`slot ${slot} is not in the loaded codebook`);
        return;
      }
      if (!row.appearance) {
        setDecodeError(
          `slot ${slot} is not wearable: a restricted channel has no colour ` +
            `for its codeword ${row.codeword.join(" ")}, so there is no ` +
            "appearance to load",
        );
        return;
      }
      setDecodeError(null);
      setReading(
        info.channels.map((channel) => ({
          kind: "best_guess",
          symbol: row.appearance[channel.name],
          confidence: "0.9",
          distributionText: "",
        })),
      );
    },
    [info],
  );

  const runDecode = useCallback(async () => {
    setDecodeError(null);
    try {
      const data = await postJSON("admin_identity_decode", {
        scheme: schemeSpec,
        thresholds,
        candidates: candidates.map((c) => ({
          name: c.name,
          slot: parseInt(c.slot, 10),
          prior: c.prior === "" ? null : parseFloat(c.prior),
        })),
        reading: reading.map((obs) => ({
          kind: obs.kind,
          symbol: obs.kind === "best_guess" ? obs.symbol : null,
          confidence:
            obs.confidence === undefined || obs.confidence === ""
              ? 1
              : parseFloat(obs.confidence),
          distribution:
            obs.kind === "distribution"
              ? parseDistribution(obs.distributionText || "")
              : null,
        })),
      });
      setDecodeResult(data);
    } catch (e) {
      setDecodeResult(null);
      setDecodeError(e.message);
    }
  }, [schemeSpec, thresholds, candidates, reading]);

  if (!spec) return <p>Loading... (are you logged in at /admin/login?)</p>;

  return (
    <div style={{ padding: "1em", fontFamily: "sans-serif" }}>
      <h1>Identity code workbench</h1>
      <p>
        Admin sandbox for the colour-code player identification (see{" "}
        <code>backend/identity/</code>). Nothing here touches the database.{" "}
        <Link to="/admin">back to admin</Link>
      </p>

      <SchemeEditor spec={spec} setSpec={setSpec} />
      {schemeError ? (
        <p style={errorStyle}>Scheme error: {schemeError}</p>
      ) : null}
      <SchemeSummary info={info} />

      <CandidateEditor
        candidates={candidates}
        setCandidates={setCandidates}
        capacity={info ? info.capacity : null}
      />

      <ReadingEditor
        info={info}
        reading={reading}
        setReading={setReading}
        onLoadSlot={loadSlot}
      />

      <div style={panel}>
        <h3>4. Decode</h3>
        <div style={{ marginBottom: "0.5em" }}>
          {["confident_threshold", "ambiguous_margin", "epsilon"].map((key) => (
            <label key={key} style={{ marginRight: "1em" }}>
              {key}:{" "}
              <input
                size={8}
                value={thresholdsText[key]}
                onChange={(e) =>
                  setThresholdsText({
                    ...thresholdsText,
                    [key]: e.target.value,
                  })
                }
              />
            </label>
          ))}
        </div>
        <button onClick={runDecode} disabled={!info}>
          decode this reading
        </button>
        {decodeError ? (
          <p style={errorStyle}>Decode error: {decodeError}</p>
        ) : null}
      </div>

      {info ? <DecodeResultView result={decodeResult} info={info} /> : null}

      <SimulationPanel
        schemeSpec={schemeSpec}
        thresholds={thresholds}
        candidates={candidates.map((c) => ({
          name: c.name,
          slot: parseInt(c.slot, 10),
          prior: c.prior === "" ? null : parseFloat(c.prior),
        }))}
      />
    </div>
  );
}
