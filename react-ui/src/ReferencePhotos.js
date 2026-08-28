// Reference photographs: the kit check the admin runs at the door.
//
// Two of the four identity channels are bring-your-own, so the largest risk to
// the night is somebody turning up in something they called "green" that
// photographs khaki. This page is where that is caught while it is still
// fixable: photograph each player as they arrive, run the picture through the
// same vision pipeline a real shot uses, and see whether their outfit actually
// decodes to *them*. Nothing here is a shot - no HP, no ammo, no queue.
//
// Driven one-handed on a phone with a box of armbands in the other, so it is a
// single column of big targets: pick a player, take the photo, read the
// verdict, move on.

import React, { useCallback, useEffect, useState } from "react";

import { sendAPIRequest } from "./utils";
import { AdminPage, adminPost } from "./AdminCommon";
import UpdateListener from "./UpdateListener";
import { MyWebcam } from "./MyWebcam";
import { ChannelTags, isMarginal, outcomeTag, zoomTag } from "./ShotQueue";

import styles from "./ReferencePhotos.module.css";
// The reading is rendered with the shot queue's own tags, so a review reads
// the same here as it does there.
import tagStyles from "./ShotQueue.module.css";

// Below this the model's colour reading is a warning rather than a result -
// the same line identity/config.py's confident_threshold draws.
const MARGINAL_CONFIDENCE = 0.6;

function formatProbability(probability) {
  return typeof probability === "number" ? probability.toFixed(2) : "?";
}

// One roster row's verdict, as [text, className]: the states the admin acts on
// at the door - nothing taken yet, still thinking, decoded to the right
// person, decoded to somebody else, or nothing to decode against.
//
// Green and red are for answers. A photo nothing was readable in, and a
// ranking the decoder itself would not call confident, are amber: both look
// exactly like a result once a name and a probability are printed next to
// them, and neither is one.
function rosterStatus(row) {
  if (!row.has_photo) return ["No photo yet", styles.statusNone];
  if (row.review_state === "pending")
    return ["Reviewing...", styles.statusPending];
  if (row.review_state === "error") return ["Review failed", styles.statusBad];
  if (row.review_state !== "done")
    return ["Photo stored, not reviewed", styles.statusNone];
  if (row.readable_channels === 0)
    return ["Nothing readable - retake", styles.statusWarn];
  if (row.matches_expected === null || row.matches_expected === undefined)
    return ["No outfit picked", styles.statusWarn];

  const probability = formatProbability(row.top_probability);
  if (row.confident !== true)
    return [
      `? Unsure: ${row.top_name || "someone"} (p=${probability})`,
      styles.statusWarn,
    ];
  if (row.matches_expected)
    return [`✓ Recognised (p=${probability})`, styles.statusGood];
  return [
    `✗ Reads as ${row.top_name || "someone else"} (p=${probability})`,
    styles.statusBad,
  ];
}

function Roster({ rows, onSelect }) {
  if (rows.length === 0)
    return <p className={styles.hint}>No players in this game yet.</p>;

  return (
    <ul className={styles.roster}>
      {rows.map((row) => {
        const [text, statusStyle] = rosterStatus(row);
        return (
          <li key={row.user_id}>
            <button
              className={styles.rosterRow}
              onClick={() => onSelect(row.user_id)}
            >
              <span className={styles.rosterName}>
                {row.name || row.user_id}
                <small className={styles.rosterTeam}>
                  {row.team_name || "no team"}
                </small>
              </span>
              <span className={`${styles.status} ${statusStyle}`}>{text}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

// The answer the whole page exists for: did this outfit decode to this player?
// Green go, red stop, amber "there is nothing to check against".
//
// Amber covers two ways of having no answer, and both used to print as green.
// A photo with no readable garment carries no evidence at all, so the ranking
// is the flat prior handed back - p=0.50 between two players, p=1.00 for a
// lone one - and the backend now sends no ranking with it. A reading the
// decoder would not call confident is a guess, and a guess is not a pass.
function IdentificationVerdict({ identification, playerName }) {
  if (!identification)
    return (
      <div className={`${styles.verdict} ${styles.verdictWarn}`}>
        No identification - nobody in this game has an outfit to compare
        against.
      </div>
    );

  const ranked = identification.ranked || [];
  const top = ranked[0];
  const topName = top ? top.name : playerName;
  const probability = formatProbability(top && top.probability);
  const confident = identification.confident !== false;

  let tone = styles.verdictWarn;
  let text = `${playerName} has not picked an outfit, so this photo cannot be checked against them.`;

  if (identification.readable_channels === 0) {
    text = `No garment could be read in this photo, so it says nothing about who is in it. Retake it with ${playerName}'s outfit in frame.`;
  } else if (identification.matches_expected === true) {
    tone = confident ? styles.verdictGood : styles.verdictWarn;
    text = confident
      ? `Recognised as ${topName} (p=${probability})`
      : `Probably ${topName} (p=${probability}), but not clearly enough to call it.`;
  } else if (identification.matches_expected === false) {
    tone = confident ? styles.verdictBad : styles.verdictWarn;
    if (!top) {
      text = `Does not read as ${playerName}`;
    } else if (confident) {
      text = `Reads as ${top.name} (p=${probability}), not ${playerName}`;
    } else {
      text = `Closest match is ${top.name} (p=${probability}), not ${playerName} - but not clearly enough to call it.`;
    }
  }

  const flags = [];
  if (identification.confident === false) flags.push("not a confident reading");
  if (identification.ambiguous) flags.push("two candidates are too close");
  if (identification.inconsistent)
    flags.push("the colours fit no outfit cleanly");

  return (
    <>
      <div className={`${styles.verdict} ${tone}`}>{text}</div>
      {flags.length > 0 ? (
        <p className={styles.flags}>Warning: {flags.join("; ")}.</p>
      ) : null}
      {ranked.length > 1 ? (
        <ul className={styles.runnersUp}>
          {ranked.slice(1, 4).map((candidate) => (
            <li key={candidate.user_id}>
              {candidate.name} (p={formatProbability(candidate.probability)})
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function ReviewView({ state, review, playerName }) {
  if (!state)
    return (
      <p className={styles.hint}>
        Not reviewed - no vision model is configured.
      </p>
    );

  if (state === "pending") return <p className={styles.hint}>Reviewing...</p>;

  if (state === "error")
    return (
      <div className={styles.errorBox}>
        Review failed: {(review && review.error) || "unknown error"}
      </div>
    );

  if (!review) return null;

  const marginal = Object.entries(review.channels || {}).filter(([, channel]) =>
    isMarginal(channel, MARGINAL_CONFIDENCE),
  );

  return (
    <>
      <IdentificationVerdict
        identification={review.identification}
        playerName={playerName}
      />
      <div className={tagStyles.tagRow}>
        {outcomeTag(review)}
        {zoomTag(review)}
        <ChannelTags
          channels={review.channels}
          warnBelow={MARGINAL_CONFIDENCE}
        />
      </div>
      {marginal.length > 0 ? (
        <p className={styles.marginalWarning}>
          Marginal:{" "}
          {marginal
            .map(
              ([name, channel]) =>
                `${name} read as ${channel.colour} at ${channel.confidence.toFixed(2)}`,
            )
            .join(", ")}
          . Check the garment before letting them go.
        </p>
      ) : null}
      <p className={tagStyles.aiReason}>
        {review.outcome_reason}
        {review.reasoning ? ` - ${review.reasoning}` : null}
      </p>
    </>
  );
}

// One player's capture/detail view: the camera, the stored photo, and what the
// pipeline made of it.
function PlayerDetail({ row, onClose, onChanged }) {
  const userId = row.user_id;
  const playerName = row.name || "This player";

  const [hasPhoto, setHasPhoto] = useState(row.has_photo);
  const [photo, setPhoto] = useState(null);
  const [state, setState] = useState(null);
  const [review, setReview] = useState(null);
  const [capturing, setCapturing] = useState(!row.has_photo);
  const [trigger, setTrigger] = useState(0);
  const [busy, setBusy] = useState(false);

  const refreshPhoto = useCallback(() => {
    sendAPIRequest(
      "admin_get_reference_photo",
      { user_id: userId },
      "GET",
      (stored) => setPhoto(stored),
    );
  }, [userId]);

  const refreshReview = useCallback(() => {
    sendAPIRequest(
      "admin_get_reference_review",
      { user_id: userId },
      "GET",
      (body) => {
        setState(body.state);
        setReview(body.review);
      },
    );
  }, [userId]);

  // Only ask for the image when there is one: the endpoint 404s otherwise,
  // and a 404 lands in the admin error log as if something had gone wrong.
  useEffect(() => {
    if (hasPhoto) refreshPhoto();
  }, [hasPhoto, refreshPhoto]);

  useEffect(refreshReview, [refreshReview]);

  const capture = useCallback(
    (imageSrc) => {
      if (!imageSrc) return;
      setBusy(true);
      sendAPIRequest("admin_capture_reference_photo", null, "POST", null, {
        user_id: userId,
        photo: imageSrc,
      }).then((response) => {
        setBusy(false);
        if (!response.ok) return;
        // A new photo invalidates the old reading, backend and screen alike.
        setState(null);
        setReview(null);
        setPhoto(null);
        setHasPhoto(true);
        setCapturing(false);
        refreshPhoto();
        refreshReview();
        onChanged();
      });
    },
    [userId, refreshPhoto, refreshReview, onChanged],
  );

  const rerunReview = useCallback(() => {
    adminPost("admin_review_reference_photo", { user_id: userId }).then(
      (response) => {
        if (response.ok) setState("pending");
        refreshReview();
      },
    );
  }, [userId, refreshReview]);

  const deletePhoto = useCallback(() => {
    adminPost("admin_delete_reference_photo", { user_id: userId }).then(
      (response) => {
        if (!response.ok) return;
        setPhoto(null);
        setHasPhoto(false);
        setState(null);
        setReview(null);
        setCapturing(true);
        onChanged();
      },
    );
  }, [userId, onChanged]);

  return (
    <div className={styles.detail}>
      {/* The review lands seconds after the photo it describes. */}
      <UpdateListener update_type="admin" callback={refreshReview} />
      <div className={styles.detailHeader}>
        <button className={styles.backButton} onClick={onClose}>
          &larr; Roster
        </button>
        <h2>
          {playerName}{" "}
          <small className={styles.rosterTeam}>
            {row.team_name || "no team"}
          </small>
        </h2>
      </div>

      {capturing ? (
        <>
          <MyWebcam
            className={styles.camera}
            trigger={trigger}
            onCapture={capture}
          />
          <button
            className={styles.bigButton}
            disabled={busy}
            onClick={() => setTrigger((previous) => previous + 1)}
          >
            {busy ? "Uploading..." : `Photograph ${playerName}`}
          </button>
          {hasPhoto ? (
            <button onClick={() => setCapturing(false)}>Cancel</button>
          ) : null}
        </>
      ) : (
        <>
          {photo ? (
            <img
              className={styles.photo}
              alt={`${playerName} in the kit they arrived in`}
              src={photo}
            />
          ) : (
            <p className={styles.hint}>Loading the stored photo...</p>
          )}
          <ReviewView state={state} review={review} playerName={playerName} />
          <div className={styles.buttonRow}>
            <button
              className={styles.bigButton}
              onClick={() => setCapturing(true)}
            >
              Retake
            </button>
            <button onClick={rerunReview}>Re-run review</button>
            <button onClick={deletePhoto}>Delete photo</button>
          </div>
        </>
      )}
    </div>
  );
}

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

export function ReferencePhotosPanel() {
  const [games, setGames] = useState(null);
  const [gameId, setGameId] = useState(null);
  const [rows, setRows] = useState([]);
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    sendAPIRequest("admin_list_games", null, "GET", (loadedGames) => {
      setGames(loadedGames);
      if (loadedGames.length > 0) setGameId(loadedGames[0].id);
    });
  }, []);

  const refreshRoster = useCallback(() => {
    if (!gameId) return;
    sendAPIRequest(
      "admin_get_reference_photo_status",
      { game_id: gameId },
      "GET",
      setRows,
    );
  }, [gameId]);

  useEffect(refreshRoster, [refreshRoster]);

  if (games === null) return <p>Loading games...</p>;
  if (games.length === 0) return <p>No games exist yet - create one first.</p>;

  const selected = rows.find((row) => row.user_id === selectedId);

  return (
    <div>
      {/* Captures, deletions and finished reviews all arrive this way. */}
      <UpdateListener update_type="admin" callback={refreshRoster} />
      <h1>Reference photos</h1>

      {selected ? (
        <PlayerDetail
          key={selected.user_id}
          row={selected}
          onClose={() => setSelectedId(null)}
          onChanged={refreshRoster}
        />
      ) : (
        <>
          <p className={styles.hint}>
            The kit check at the door: photograph each player as they arrive and
            see whether their outfit decodes to them. Not a shot - nothing here
            touches the game.
          </p>
          <GameSelector games={games} gameId={gameId} setGameId={setGameId} />
          <Roster rows={rows} onSelect={setSelectedId} />
        </>
      )}
    </div>
  );
}

export default function ReferencePhotos() {
  return (
    <AdminPage>
      <ReferencePhotosPanel />
    </AdminPage>
  );
}
