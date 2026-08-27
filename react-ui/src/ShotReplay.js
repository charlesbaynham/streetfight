// The replay workbench: fire real shots from the database through the vision
// pipeline with the contract edited on the fly, and see what CharlesBot would
// have said. Nothing is stored - this is the in-browser counterpart of
// scripts/replay_shot_reviews.py, for trialling a prompt before shipping it.
//
// "The contract" is three things, and all three have to be editable together:
// the wording, the shape of the conversation (whether a zoom is screened for,
// sent up front, or not offered at all) and the JSON schema the reply must
// match. A prompt edited alone is a prompt overruled - the model can only
// answer the question its schema asks, and the pipeline's follow-up turns
// refer it back to "the JSON described above" whatever it was told.

import React, { useCallback, useEffect, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";
import { AdminPage } from "./AdminCommon";
import { getShotFromCache } from "./ShotCache";
import { verdictText, zoomTag } from "./ShotQueue";
import { Row, Col } from "react-bootstrap";

import styles from "./ShotReplay.module.css";
// The outcome tags are the ShotQueue's own, so a review reads the same here as
// in the queue.
import tagStyles from "./ShotQueue.module.css";

const OUTCOME_LABELS = {
  hit_player: ["HIT", tagStyles.outcomeHit],
  hit_bystander: ["Bystander - not a hit", tagStyles.outcomeBystander],
  miss: ["Miss", tagStyles.outcomeMiss],
};

// The conversation shapes the backend offers (shot_vision.ZOOM_MODES), and
// what each does to the exchange.
const ZOOM_MODES = [
  ["screened", "Screened zoom (live pipeline)"],
  ["upfront", "Both views up front"],
  ["single", "One turn, no zoom"],
];

// The coarse verdict a review implies, for comparison with the admin's own.
const OUTCOME_TO_VERDICT = {
  hit_player: "hit",
  hit_bystander: "bystander",
  miss: "miss",
};

// One shot's reading, rendered from the review dict the replay endpoint
// returns (same shape ShotAiTags displays in the queue).
function ReplayResult({ review }) {
  const [label, outcomeStyle] = OUTCOME_LABELS[review.outcome] || [
    review.outcome,
    tagStyles.outcomeMiss,
  ];

  // Under a contract of its own the reply has no outcome to render, and the
  // pipeline's default one would be a verdict the model never gave.
  if (review.parse_error) {
    return (
      <>
        <p className={styles.rawReplyNote}>
          The reply did not match the standard reading: {review.parse_error}
        </p>
        <pre className={styles.rawReply}>
          {JSON.stringify(review.raw_reply, null, 2)}
        </pre>
      </>
    );
  }

  return (
    <>
      <div className={tagStyles.tagRow}>
        <span className={`${tagStyles.tag} ${outcomeStyle}`}>{label}</span>
        <span className={tagStyles.tag}>
          confidence {Math.round(100 * (review.confidence || 0))}%
        </span>
        {zoomTag(review)}
        {Object.entries(review.channels || {}).map(([name, channel]) => (
          <span
            key={name}
            className={`${tagStyles.tag} ${
              channel.colour ? "" : tagStyles.tagUnknown
            }`}
          >
            {channel.hex ? (
              <span
                className={tagStyles.swatch}
                style={{ background: channel.hex }}
              />
            ) : null}
            {name}: {channel.colour || "unknown"}
          </span>
        ))}
      </div>
      <p className={tagStyles.aiReason}>
        {review.outcome_reason}
        {review.reasoning ? ` - ${review.reasoning}` : null}
      </p>
    </>
  );
}

// Every turn exchanged with the model on one replay, and what it said back --
// the debugging counterpart of ReplayResult's parsed summary. A flat,
// chronological conversation (the model never revises an earlier turn, so
// nothing here is ever repeated), collapsed by default. A raw-JSON toggle
// dumps the same list pretty-printed, for pasting elsewhere.
function TranscriptView({ transcript }) {
  const [raw, setRaw] = useState(false);

  if (!transcript || transcript.length === 0) return null;

  return (
    <details className={styles.transcript}>
      <summary>
        Full model transcript ({transcript.length} turn
        {transcript.length === 1 ? "" : "s"})
      </summary>
      <label className={styles.rawToggle}>
        <input
          type="checkbox"
          checked={raw}
          onChange={(event) => setRaw(event.target.checked)}
        />
        Prettified JSON
      </label>
      {raw ? (
        <pre className={styles.transcriptJson}>
          {JSON.stringify(transcript, null, 2)}
        </pre>
      ) : (
        transcript.map((turn, turnIndex) => (
          <div key={turnIndex} className={styles.turn}>
            <span className={styles.turnRole}>
              {turn.role}
              {turn.has_image ? " (+ image)" : ""}
            </span>
            {turn.reasoning ? (
              <details className={styles.turnReasoning}>
                <summary>Model reasoning</summary>
                <pre className={styles.turnReasoningText}>{turn.reasoning}</pre>
              </details>
            ) : null}
            <pre className={styles.turnText}>
              {turn.role === "assistant"
                ? JSON.stringify(turn.reply, null, 2)
                : turn.text}
            </pre>
          </div>
        ))
      )}
    </details>
  );
}

// Vision-formatted images, in the order the model actually saw them: the full
// frame, then one card per zoom actually spent (zoomCount, 0-2) -- not just
// the two the pipeline is *capable* of, which said nothing about what a given
// replay did. Before a replay has run (zoomCount undefined) only the full
// frame is shown, since nothing is known yet about whether a zoom followed.
// Fetched from admin_get_shot_vision_images, which formats identically to the
// pipeline (prepare_for_vision + zoom_image).
export function ShotVisionImages({ shot_id, zoomCount }) {
  const [images, setImages] = useState(null);

  useEffect(() => {
    setImages(null);
    if (!shot_id) return;
    let cancelled = false;
    sendAPIRequest("admin_get_shot_vision_images", { shot_id }).then(
      async (response) => {
        if (cancelled) return;
        if (!response.ok) return;
        const body = await response.json();
        if (!cancelled) setImages(body);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [shot_id]);

  if (!images)
    return <p className={styles.visionLoading}>Loading vision images...</p>;

  const zoomImages = [images.zoomed, images.zoomed2].slice(0, zoomCount || 0);

  return (
    <div className={styles.visionImages}>
      <div className={styles.visionImageWrapper}>
        <img
          className={styles.visionImg}
          alt="Full frame as vision sees it"
          src={images.full}
        />
        <span className={styles.visionLabel}>
          Full frame (as vision sees it)
        </span>
      </div>
      {zoomImages.map((src, zoomIndex) => (
        <div key={zoomIndex} className={styles.visionImageWrapper}>
          <img
            className={styles.visionImg}
            alt={`Zoom ${zoomIndex + 1} centre as vision sees it`}
            src={src}
          />
          <span className={styles.visionLabel}>
            Zoom {zoomIndex + 1} centre (as vision sees it)
          </span>
        </div>
      ))}
    </div>
  );
}

// One selectable shot: thumbnail, shooter, the admin's verdict if there is
// one, and whatever the last replay run said about it.
function ShotCard({ shot_id, selected, onToggle, result }) {
  const [shot, setShot] = useState(null);

  useEffect(() => {
    setShot(null);
    let cancelled = false;
    getShotFromCache(shot_id).then((s) => {
      if (!cancelled) setShot(s);
    });
    return () => {
      cancelled = true;
    };
  }, [shot_id]);

  if (!shot) return <div className={styles.card}>Loading...</div>;

  const replayVerdict =
    result && result.review ? OUTCOME_TO_VERDICT[result.review.outcome] : null;
  const disagrees =
    shot.checked && replayVerdict !== null && shot.result !== replayVerdict;

  return (
    <div
      className={`${styles.card} ${selected ? styles.cardSelected : ""}`}
      onClick={onToggle}
    >
      <label className={styles.cardPicker} onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" checked={selected} onChange={onToggle} />
      </label>
      <div className={styles.cardBody}>
        <em>
          {shot.user.name} - {new Date(shot.time_created).toLocaleString()}
        </em>
        <ShotVisionImages
          shot_id={shot_id}
          zoomCount={result && result.review ? result.review.zoom_count : 0}
        />
        {shot.checked ? (
          <p className={tagStyles.verdict}>Adjudicated: {verdictText(shot)}</p>
        ) : (
          <p>Not yet adjudicated</p>
        )}
        {result && result.status === "running" ? <p>Replaying...</p> : null}
        {result && result.status === "error" ? (
          <p className={styles.replayError}>Replay failed: {result.error}</p>
        ) : null}
        {result && result.review ? (
          <div onClick={(e) => e.stopPropagation()}>
            {disagrees ? (
              <p className={styles.disagreement}>
                Disagrees with the admin's verdict
              </p>
            ) : null}
            <ReplayResult review={result.review} />
            <TranscriptView transcript={result.review.transcript} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ShotReplayPanel() {
  const [shotIds, setShotIds] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [prompt, setPrompt] = useState(null);
  const [schemaText, setSchemaText] = useState(null);
  const [schemaError, setSchemaError] = useState(null);
  const [zoomMode, setZoomMode] = useState(ZOOM_MODES[0][0]);
  // "" means no override -- the live pipeline's OPENROUTER_REASONING_EFFORT
  // setting (or none at all) applies, exactly as it does for a real review.
  const [reasoningEffort, setReasoningEffort] = useState("");
  const [results, setResults] = useState({});
  const [running, setRunning] = useState(false);
  // What the backend last handed back, so an *untouched* box can follow a
  // change of conversation shape while an edited one is never clobbered.
  const seeded = useRef({ prompt: null, schema: null });

  const seedContract = useCallback((mode, force) => {
    sendAPIRequest(
      "admin_get_default_vision_prompt",
      { zoom_mode: mode },
      "GET",
      (body) => {
        const nextSchema = JSON.stringify(body.schema, null, 2);
        // Read against what was seeded *before* this fetch: the state updaters
        // below run after this callback returns, so comparing them against the
        // ref once it already holds the new values would find no match and
        // leave every box stale.
        const previous = seeded.current;
        seeded.current = { prompt: body.prompt, schema: nextSchema };
        setPrompt((current) =>
          force || current === null || current === previous.prompt
            ? body.prompt
            : current,
        );
        setSchemaText((current) =>
          force || current === null || current === previous.schema
            ? nextSchema
            : current,
        );
        setSchemaError(null);
      },
    );
  }, []);

  // Every shot in the database, newest first: this page replays history, so
  // the adjudicated shots the queue hides are the interesting ones.
  useEffect(() => {
    sendAPIRequest("admin_get_shots_info", { include_checked: true }).then(
      async (response) => {
        if (!response.ok) return;
        setShotIds((await response.json()).reverse());
      },
    );
  }, []);

  // The prompt describes the zoom it is about to be offered, so the default
  // text is only correct for one shape of conversation: reseed on a change.
  useEffect(() => {
    seedContract(zoomMode, false);
  }, [zoomMode, seedContract]);

  const toggle = useCallback((shot_id) => {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(shot_id)) {
        next.delete(shot_id);
      } else {
        next.add(shot_id);
      }
      return next;
    });
  }, []);

  const setResult = useCallback((shot_id, result) => {
    setResults((previous) => ({ ...previous, [shot_id]: result }));
  }, []);

  const replaySelected = useCallback(() => {
    let responseSchema;
    try {
      responseSchema = JSON.parse(schemaText);
    } catch (e) {
      setSchemaError(`The response schema is not valid JSON: ${e.message}`);
      return;
    }
    setSchemaError(null);
    setRunning(true);
    // Fire them all at once: the backend's semaphore bounds how many vision
    // calls are actually in flight.
    Promise.all(
      [...selected].map((shot_id) => {
        setResult(shot_id, { status: "running" });
        return sendAPIRequest("admin_replay_shot_review", {}, "POST", null, {
          shot_id,
          prompt,
          zoom_mode: zoomMode,
          response_schema: responseSchema,
          reasoning_effort: reasoningEffort || null,
        }).then(async (response) => {
          if (response.ok) {
            setResult(shot_id, {
              status: "done",
              review: await response.json(),
            });
          } else {
            setResult(shot_id, {
              status: "error",
              error: `${response.status}: ${await response.text()}`,
            });
          }
        });
      }),
    ).then(() => setRunning(false));
  }, [selected, prompt, schemaText, zoomMode, reasoningEffort, setResult]);

  return (
    <>
      <h1>Shot replay workbench</h1>
      <Row>
        <Col>
          <p>
            Replays real shots through the AI reviewer with the contract below.
            Nothing is stored and the game is not affected. Pick shots, edit the
            prompt, the conversation shape and the schema its reply must match,
            run. A reply that is not a standard reading is shown as it landed.
          </p>
          <textarea
            aria-label="Vision prompt"
            className={styles.promptBox}
            value={prompt === null ? "Loading the live prompt..." : prompt}
            onChange={(event) => setPrompt(event.target.value)}
          />
          <details className={styles.schemaPanel}>
            <summary>
              Response schema - the JSON shape the reply is forced into
            </summary>
            <textarea
              aria-label="Response schema"
              className={styles.schemaBox}
              value={
                schemaText === null ? "Loading the live schema..." : schemaText
              }
              onChange={(event) => setSchemaText(event.target.value)}
            />
          </details>
          {schemaError ? (
            <p className={styles.replayError}>{schemaError}</p>
          ) : null}
          <div className={styles.controls}>
            <button
              onClick={replaySelected}
              disabled={
                running ||
                selected.size === 0 ||
                prompt === null ||
                schemaText === null
              }
            >
              {running
                ? "Replaying..."
                : `Replay ${selected.size} selected shot${
                    selected.size === 1 ? "" : "s"
                  }`}
            </button>
            <button onClick={() => seedContract(zoomMode, true)}>
              Reset to live contract
            </button>
            <label>
              Conversation shape{" "}
              <select
                aria-label="Conversation shape"
                value={zoomMode}
                onChange={(event) => setZoomMode(event.target.value)}
              >
                {ZOOM_MODES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reasoning effort{" "}
              <select
                aria-label="Reasoning effort"
                value={reasoningEffort}
                onChange={(event) => setReasoningEffort(event.target.value)}
              >
                <option value="">Pipeline default</option>
                <option value="none">none</option>
                <option value="minimal">minimal</option>
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
                <option value="xhigh">xhigh</option>
                <option value="max">max</option>
              </select>
            </label>
            <button
              onClick={() => setSelected(new Set(shotIds))}
              disabled={shotIds.length === 0}
            >
              Select all
            </button>
            <button onClick={() => setSelected(new Set())}>Select none</button>
          </div>
        </Col>
      </Row>
      <Row>
        <Col>
          <div className={styles.grid}>
            {shotIds.map((shot_id) => (
              <ShotCard
                key={shot_id}
                shot_id={shot_id}
                selected={selected.has(shot_id)}
                onToggle={() => toggle(shot_id)}
                result={results[shot_id]}
              />
            ))}
          </div>
        </Col>
      </Row>
    </>
  );
}

export default function ShotReplay() {
  return (
    <AdminPage>
      <ShotReplayPanel />
    </AdminPage>
  );
}
