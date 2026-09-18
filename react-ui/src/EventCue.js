import React, { useRef, useState } from "react";

import { adminPost } from "./AdminCommon";

// Start (or call off) the countdown every player's phone shows: the circle
// closing, or a drop landing (backend/next_event.py). The circle itself is
// placed by the plan (backend/circles.py) before anybody presses anything
// here, so on the night this is the only button a circle needs; CircleControl
// above is for the circle that goes somewhere the plan did not say.
//
// Cueing a circle is also what spends every early-warning card in the game:
// the card buys a head start on this announcement.
//
// Defaults are the ones from the plan: ten minutes for a circle, five for a
// drop. They are the numbers an admin will want nine times out of ten, and the
// box is there for the tenth.
const DEFAULT_MINUTES = { circle: 10, drop: 5 };

function whenWords(at) {
  if (!at) return null;
  const seconds = Math.round(at - Date.now() / 1000);
  if (seconds <= 0) return "due now";
  if (seconds < 90) return `in ${seconds}s`;
  return `in ${Math.round(seconds / 60)} min`;
}

export default function EventCue({ game }) {
  const [kind, setKind] = useState("circle");
  const minutesInput = useRef(null);
  const noteInput = useRef(null);

  const cued = Boolean(game.next_event_at);

  // The box is keyed on the kind, so switching between circle and drop
  // re-mounts it with that kind's default rather than leaving the other's
  // number in place.
  const minutesBox = (
    <input
      key={kind}
      type="number"
      step="1"
      min="1"
      defaultValue={DEFAULT_MINUTES[kind]}
      ref={minutesInput}
      required
    />
  );

  return (
    <>
      <p>
        {cued ? (
          <>
            Counting down to <b>{game.next_event_kind}</b>{" "}
            <b>{whenWords(game.next_event_at)}</b>
            {game.next_event_note ? <> &mdash; {game.next_event_note}</> : null}
          </>
        ) : (
          <>Nothing cued &mdash; the players see no countdown</>
        )}{" "}
        <button
          onClick={() => adminPost("admin_cancel_cue", { game_id: game.id })}
        >
          Cancel countdown
        </button>
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          adminPost("admin_cue_next_event", {
            game_id: game.id,
            kind,
            minutes: parseFloat(minutesInput.current.value),
            // Only sent when there is one: an empty string would be stored as
            // a note and drawn as a dash with nothing after it.
            ...(noteInput.current && noteInput.current.value.trim()
              ? { note: noteInput.current.value.trim() }
              : {}),
          });
        }}
      >
        <label>
          Event:{" "}
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="circle">circle closes</option>
            <option value="drop">drop lands</option>
          </select>
        </label>{" "}
        {minutesBox} minutes{" "}
        {kind === "drop" ? (
          <input
            type="text"
            placeholder="what's in it (shown to players)"
            ref={noteInput}
            size={30}
          />
        ) : null}{" "}
        <button type="submit">Start countdown</button>
      </form>
      <p>
        The circle cue promotes whatever is in NEXT to the exclusion circle when
        it reaches zero, and then arms the next circle of the plan ready for the
        one after. It promotes nothing if NEXT is empty &mdash; the panel above
        says whether it is.
      </p>
      <p>
        A drop cue only announces itself &mdash; at zero the ticker says the
        courier has set off and the countdown clears. Nothing appears on
        anybody's map until the courier starts broadcasting from the courier
        page, so be ready to open it.
      </p>
    </>
  );
}
