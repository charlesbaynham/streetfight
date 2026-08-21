# Roadmap

The planned work, re-ordered from the order it was thought of into the order it
wants doing. Nothing here is implemented yet: this file is the record of intent,
not a changelog.

Each item keeps its **original number** (`#1` … `#13`) so it can be matched back
to the list it came from. Items prefixed `R` are additions proposed while
writing this up — see [Proposed additions](#proposed-additions).

Every software item names the files it lands in, because most of them are
smaller than they sound: the pure identity module and the soft decoder already
exist and are tested, and several items are a matter of *wiring what is there*
rather than writing something new.

---

## The three tracks

The list interleaves three kinds of work that proceed independently and are
blocked by different things:

| Track                          | What it is                                                   | What gates it                                                      |
| ------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------------ |
| **A. Recognition correctness** | CharlesBot is currently *wrong* in ways that break the game. | Nothing. Start now.                                                |
| **B. Field logistics**         | Kit, locations, printing, the map.                           | Real-world lead times and the date of the next game.               |
| **C. Capability**              | Escalation, reference photos, better photos.                 | Track A (it needs the posterior) and the kit decisions in track B. |

Track B has the only *hard* deadline (a game night), and some of it has weeks of
lead time — armbands have to be ordered before colours can be assigned, and
colours have to be assigned before anything can be printed. So B's long-lead
items start in parallel with A even though A is more urgent in engineering
terms.

## Priority order

| Order | Item                                        | Track | Why here                                                                                |
| ----- | ------------------------------------------- | ----- | --------------------------------------------------------------------------------------- |
| 1     | **#4** False hits                           | A     | The game is unplayable with auto-actions on while this is live.                         |
| 2     | **R2** Adjudication scorecard               | A     | Free labelled data; makes #4 and #5 measurable instead of vibes.                        |
| 3     | **#5** Use every channel, not just armbands | A     | Wastes real information today and hands the admin "unable to tell".                     |
| 4     | **#3** Ranked candidates in the review UI   | A     | The surface of #5; same piece of plumbing.                                              |
| 5     | **#2** "CharlesBot thinks: hit on *name*"   | A     | Needs the name, so it needs #5/#3.                                                      |
| 6     | **#1** "CharlesBot", not "AI"               | A     | Trivial and self-contained; ride it in with #2.                                         |
| 7     | **#9** Buy armbands / decide on hats        | B     | Longest lead time of anything here, and #10 and #8 both wait on it.                     |
| 8     | **#12** Redraw the Westminster map          | B     | Blocks #7 (drops must be placeable) and un-blocks the temporary test venue.             |
| 9     | **#6** Find the pubs                        | B     | Feeds #8; independent of everything in track A.                                         |
| 10    | **#7** Find the drop locations              | B     | Needs #12 to place them; feeds #8.                                                      |
| 11    | **#10** Players pick their own colours      | B     | Needs #9 (you can only pick what exists) and drives #8's print run.                     |
| 12    | **#8** Print the run                        | B     | Last logistics step: everything above becomes paper here.                               |
| 13    | **#13** Higher-resolution capture           | C     | Raises the ceiling for #4/#5/#11, but they are worth doing at today's resolution first. |
| 14    | **#11** Escalation to a stronger model      | C     | The largest single piece; needs #5's posterior and a new photo-capture flow.            |

---

## Track A — recognition correctness

### #4 — CharlesBot calls clear misses "hit" *(highest priority)*

**Symptom.** Shots that visibly miss are reported as hits.

**Where it is decided.** `backend/shot_vision.py`: the model answers
`shot_hit_a_person`, and `classify()` turns that plus the channel reads into
`hit_player` / `hit_bystander` / `miss`. `classify()` cannot rescue a wrong
answer to the first question — if the model says a person was hit, no amount of
colour reading turns it back into a miss. So this is a prompt/geometry problem,
not a decoder problem.

**Suspects, in the order worth testing.**

1. **The hit definition is written leniently.** The current prompt says
   _"Hitting any part of their clothing or hands or shoes counts as a hit. It is
   only a miss if it entirely misses the person"_, which reads as an
   invitation to count anything near a person. It never says the crosshair marks
   a **single point** that must land **on** them. Rewrite it around the point:
   the crosshair is one pixel; a hit is that pixel lying on the person's body or
   clothing; beside them, above them, on the ground in front of them, or between
   two people is a **miss**.
2. **The crosshair has a hole in the middle.** `_draw_aim_marker_on()`
   (`backend/image_processing.py`) draws four arms with a gap: `arm =
max_dim // 20`, `gap = arm // 3`. On the 1024 px image that
   `prepare_for_vision()` sends, that is a ~34 px *empty square* at the exact
   place the shot landed — and a distant target can be smaller than the hole.
   The model is being asked "is the thing under the crosshair a person" while
   the thing is hidden by the crosshair, and a person standing anywhere in that
   gap looks "under" it. Try a small solid dot or a 1 px centre tick, and
   re-measure.
3. **The prompt applies pressure towards a decision.** _"You MUST ultimately
   make a decision on whether the shot is hitting a person or not"_ pushes
   towards a call, and the surrounding text gives no reason to prefer "miss"
   when torn. State the asymmetry explicitly: a wrongly-called miss costs the
   shooter one bullet; a wrongly-called hit takes a life off somebody who was
   never shot. When in doubt, it is a miss.
4. **Let Python own the threshold.** In keeping with the module's stated
   principle (*the model observes; Python decides*), replace the boolean with an
   observation the model can actually see: where the crosshair sits relative to
   the nearest person — e.g. `on_body` / `touching_their_outline` /
   `clearly_beside_them` / `nobody_near` — plus a rough gap in body-widths.
   `classify()` then applies the rule, so tightening or loosening it is a
   constant in Python and a test, not a prompt rewrite.

**Done when** the labelled set from **R2** shows the false-hit rate down to
something an admin can live with, with the false-miss rate reported alongside it
(this trade is the whole game; do not optimise one silently).

**Depends on:** nothing. **Feeds:** everything else in track A.

---

### R2 — Scorecard: what CharlesBot said vs what the admin decided *(proposed)*

Every shot already carries both halves of a labelled example:
`Shot.ai_review` (the JSON verdict) and `Shot.result` (`"hit"` / `"miss"` /
`"bystander"` / `"refunded"`, plus `target_user_id`). Nothing compares them.

**The work:** an admin endpoint and a small page that reports, over a game or
over all games: the confusion matrix of CharlesBot's outcome against the admin's,
broken down by whether the zoom was used and by how many channels were readable;
and the same numbers restricted to reviews above the auto-action confidence
threshold, which is the number that decides whether `ai_auto_actions_enabled` is
safe to switch on.

**Why it comes second.** #4 and #5 are both "make the model less wrong" tasks,
and there is currently no way to tell whether a prompt change helped. This is
close to free — the data is already in the database — and it turns the rest of
track A from guesswork into measurement. Every shot photo is also saved to disk
by `save_image()` (`backend/image_processing.py`), so the same pairing gives an
offline corpus to replay prompt variants against without touching a live game.

**Done when** a prompt change can be scored against real photos before it ships.

---

### #5 — Two readable channels should still identify somebody

**Symptom.** A distant shot read two of the four channels correctly. Two
erasures is exactly what the `[4,2,3]` code is meant to survive, but CharlesBot
said it could not tell — because neither of the two was the armbands.

**Why it does that.** `classify()` in `backend/shot_vision.py` treats the
armbands as the *player marker*: bystanders do not wear armbands, so armbands
read ⇒ player. When the armbands are erased, it falls back to demanding **all
three** other channels, and anything less is declared a bystander. Hence "two
channels, no armbands" → nothing. The reasoning behind that is sound as far as it
goes (with only `k = 2` readable positions, any reading completes to *some*
codeword, so the code vouches for nothing) — but it answers the wrong question.

**The fix is to split one question into two.**

- **"Is this person a player at all?"** genuinely needs redundancy, and armbands
  genuinely are strong evidence. Keep that — but as *evidence*, not as a gate.
- **"Which player is it?"** does **not** need the full codeword space. The
  candidate set is not the 34 usable slots, it is the handful of living players
  on other teams who were near the shooter — and two correctly-read channels
  discriminate sharply within a set that small, especially once the GPS prior is
  applied.

Today the second question is never asked when the first one fails.

**The plumbing already exists and is unused.**

- `shot_vision.to_reading()` builds the `Reading` the soft decoder consumes. Its
  own docstring says nothing calls it yet.
- `backend/identity/decoder.py` `decode()` takes a `Reading`, a candidate set,
  and a `Prior`, and returns ranked posteriors plus `inconsistent` / `ambiguous`
  / `confident` flags.
- `Shot.location_context` already stores every player's position at the moment
  the shot was fired (`user_interface.submit_shot`), which is the GPS prior in
  plan §8.3 — no schema change needed.

So the work is an integration-layer module (per the plan's rule that
`backend/identity/` stays pure) that: builds the candidate set from the shot's
game, builds the `Prior` from `location_context` (start with a Gaussian or
inverse-distance in metres), calls `decode()`, and stores the ranked result
alongside the existing review payload.

**Keep the auto-action gate conservative.** `slot_candidates_from_review()`
requires `k + 1` readable channels and is used by
`backend/shot_auto_actions.py`. That gate is *right* for firing a hit
automatically and should stay. What changes is that the admin's view is no
longer limited to what the auto-actions are willing to act on: a two-channel
read produces "if this is a player, it is most likely X (p = 0.8)" instead of
silence.

**Done when** a two-readable-channel photo produces a ranked candidate list, and
the auto-action behaviour is unchanged.

**Depends on:** nothing hard, but do #4 first so the input is trustworthy.
**Feeds:** #3, #2, #11.

---

### #3 — Show the ranked candidates in the admin review UI

**What.** In review mode, list the people CharlesBot thinks it hit, ranked by
posterior probability, each with its distance in **code space**.

**Where.** `react-ui/src/ShotQueue.js` already has most of the furniture:
`ShotAiTags` renders the review as coloured tags, and `NearestPlayers` /
`rankShotCandidates` already lists every other player with their distance in
metres, computed client-side from `location_context`. This item replaces that
list with the decoder's ranking, keeping the metres as one column.

**The row should carry:** name, team, posterior, code distance, metres. Code
distance is the Hamming distance between the read symbols and that player's
codeword counted over positions where both are known — `decoder._hamming_distance`
and `overrides.overlap_distance` already compute exactly this, so it should be
returned by the backend rather than recomputed in JavaScript. The posterior comes
from the same `decode()` call as #5; compute it server-side (the decoder is
Python) and extend the `admin_get_shot_ai_review` payload.

**Also worth showing:** the `ambiguous` / `inconsistent` flags, since "two
candidates are tied" is a different message to the admin than "the reading fits
nobody".

**Depends on:** #5.

---

### #2 — "CharlesBot thinks this is a hit on *Alice*"

**What.** The verdict should name the person, not just the outcome.

**Where.** `OUTCOME_LABELS` in `react-ui/src/ShotQueue.js` (admin) and the
`AI thinks: ${shot.ai_suggestion}` line in `react-ui/src/ShotHistory.js`
(player-facing).

**The backend piece.** The stored review holds a `slot`, not a name — the
slot → user resolution currently lives in `shot_auto_actions._decide()`. Resolve
it at read time in the review endpoint rather than denormalising a name into the
stored JSON, so a later identity correction is reflected without rewriting
history.

**Wording needs to degrade gracefully**, since the name is often unknown:

| Situation               | Admin sees                                                   |
| ----------------------- | ------------------------------------------------------------ |
| One confident candidate | *CharlesBot thinks: hit on Alice*                            |
| Several candidates      | *CharlesBot thinks: hit — probably Alice (0.6) or Bob (0.3)* |
| Player, unidentified    | *CharlesBot thinks: hit on a player, but can't tell who*     |
| Not a player            | *CharlesBot thinks: that's a bystander, not a hit*           |
| No person               | *CharlesBot thinks: miss*                                    |

See the open question about whether the **player-facing** history should name
the target at all.

**Depends on:** #5 (for the name), #3 (same payload).

---

### #1 — Call it "CharlesBot", not "AI"

**What.** Every user-facing string that says "AI" says "CharlesBot".

**Where.** `react-ui/src/ShotQueue.js` ("AI review failed", "Re-run AI review"),
`react-ui/src/ShotHistory.js` ("AI thinks:"), `react-ui/src/AdminMode.js` (both
toggle labels), and the tests that assert on those strings
(`ShotQueue.test.js`, `AdminMode.test.js`, `ShotHistory.test.js`,
`shotHistoryStore.test.js`, `testUtils.js`).

**Scope it to display strings.** Leave the API fields, database columns and
module names (`ai_review`, `ai_review_state`, `ai_shot_review_enabled`,
`backend/ai_shot_review.py`) alone: renaming them would invalidate stored review
payloads and buy nothing. Worth one comment at each boundary saying that
"CharlesBot" is the display name for the thing the code calls `ai_review`.

Bundle this with #2 — the same lines change twice otherwise.

---

## Track B — field logistics

### #9 — Buy armbands; decide about hats

**The constraint.** The palettes in `backend/identity/config.py` were chosen by
optimising worst-case CIEDE2000 separation across three illuminants (daylight,
warm-white LED, sodium street lighting) — see plan §9.1 and §12.4. Substituting
"close enough" colours because that is what was in stock erodes the property the
whole scheme rests on. Buy against the hex values, and where a real product
misses, record what was actually bought so the palette can be re-checked rather
than silently drifting.

Needed: **7 armband colours** (the main palette) and, if hats are provided,
**7 hat colours**.

**The hat decision is not cosmetic.** `backend/identity/allocation.py` spends the
hat channel on telling teams apart by eye — every member of a team gets the same
hat colour and no two teams share one. If hats are not provided, or are provided
but not reliably worn, then:

- the friend-or-foe-at-30m property disappears, and
- the hat becomes an unreliable channel, i.e. an erasure much of the time, which
  eats directly into the erasure budget that #5 is trying to spend better.

If hats are dropped entirely, `TEAM_CHANNEL` should move to whichever channel
*is* reliably provided (the armbands are the obvious candidate) rather than
being left pointing at a garment nobody is wearing.

**Done when** the kit is ordered and the actual colours are recorded against the
palette.

---

### #12 — Redraw the map for Westminster

**Current state.** `ACTIVE_VENUE` in `backend/venues.py` is
`VENUES["koyao_resort"]`, a temporary test venue, with a `TODO` saying to swap
back before it is played for real. Kingston is the other entry.

**What a venue needs** (`Venue` / `VenueMap`):

- the map image, dropped into `react-ui/src/images/` with one line added to
  `react-ui/src/mapImages.js` (the `image` key resolves against it);
- `width_px` / `height_px`;
- two `MapReferencePoint`s (pixel *and* lat/long). Deriving them from a known
  tile crop — as the resort venue does — is far more accurate than eyeballing
  two landmarks;
- `corner_width_km` for the mini-map window;
- the landmarks circles can be placed at.

Nothing in `MapView.js` should need touching. `VenueMap.bounds` exists so the
tests can check that every landmark actually lands on the image — keep that
passing.

**Do this before #7**, since a drop that is not on the map cannot be used, and it
is the natural place to sanity-check the game area's extent.

---

### #6 — Find the pubs near House Absolute

**What.** A shortlist of pubs within a chosen radius of House Absolute, probably
harvested from the existing Google Maps list (the Norby-playlist replacement)
rather than assembled from scratch.

**Getting the list out of Google Maps.** A saved list can be exported via Google
Takeout (Saved → `.csv` of place URLs) or shared as a link; either way the useful
output is name + lat/long per pub, which is the same shape as
`Venue.landmarks`.

**Per pub, the roadmap needs to know:** coordinates, opening hours on a game
night, and whether they are willing to hold a printed code behind the bar. That
last one is the actual gate — it is a conversation, not a data problem, and
should start early.

**Feeds:** #8 (they need something printed to hold), #12 (they become landmarks).

---

### #7 — Find new drop locations

**What.** Places a QR code can be physically hidden that will not read, to a
passer-by or a police officer, as somebody taping a device to street furniture.

**Suggested criteria** to write down and apply consistently:

- publicly accessible without trespass, and reachable at night;
- unremarkable to leave something at — a pub garden, a noticeboard, a café, a
  shop with permission — in preference to street furniture;
- **nothing near a security-sensitive site.** In Westminster specifically this
  rules out a lot: government buildings, embassies, barracks, and station or
  Tube infrastructure. This is the reason the item exists — treat it as a hard
  exclusion list drawn on the map, not a judgement call made at 11pm;
- sheltered enough that paper survives rain;
- inside the game area and on the map (hence #12 first).

**Mitigation to build into the print run** (#8): every card carries a line
saying what it is and a contact number, so anyone who finds one gets an answer
rather than a fright. Cheap, and it converts the failure mode from "incident" to
"curiosity".

**Depends on:** #12. **Feeds:** #8.

---

### #10 — Let players pick their own colours

**Current state.** `identity_admin.build_join_codes(game_id, slots_per_team)`
pre-allocates a block of slots per team (one hat colour each, via
`allocation.allocate_team_slots`) and mints one signed join URL **per slot**;
`claim_join_slot()` claims whatever slot the scanned code carries. So today a
player is handed an outfit, they do not choose one.

**What "picking" implies.**

- A pre-game page listing the team's *unclaimed* slots as outfits, with swatches
  — `hex_for()` and the swatch rendering in `AdminIdentity.js` / `IdentityDemo.js`
  already exist to reuse.
- The hat is fixed by the team (see #9), so the choice is really across the other
  three channels. Say so on the page, or it reads as a bug.
- The claim must be **atomic**: two people cannot end up wearing the same
  codeword, and this will be done by several people at once on their phones.
- It must work **before the night**, and plan §8.2 is explicit that slots must be
  pre-assignable before anybody has a `User` row — people need to know what to
  wear in advance.

**Suggested shape** (minimal change): keep the signed join code as the entry
point, but let it carry the **team's block** rather than a single slot, and have
the claim flow present the unclaimed slots in that block and take the player's
pick. `build_join_codes` then mints one code per team instead of one per slot,
which also makes the print run smaller.

**Depends on:** #9 (you can only offer colours you have). **Feeds:** #8.

---

### #8 — Print everything

**Three separate print runs**, with different deadlines:

1. **Drop codes** for the new locations (#7) — existing tooling:
   `backend/generate_qr_items.py` plus the templates in
   `backend/image_templates/`.
2. **Pub handouts** (#6) — probably a different format: something a bar will
   actually keep on display, plus the "this is a game, ring this number" line
   from #7.
3. **Player appearance cards** (#10) — what to wear, per player, plus their join
   code. `build_join_codes` already returns `appearance` per slot for exactly
   this.

**Do last**, but note the run cannot start until #6, #7 and #10 have all
resolved. If the schedule gets tight, the drop codes are the ones with a hard
dependency on the locations; the appearance cards can be sent digitally as a
fallback.

---

## Track C — capability

### #13 — Better photos, if the platform now allows it

**Current path.** `react-ui/src/MyWebcam.js` requests
`{ width: { ideal: 2048 }, height: { ideal: 1080 }, facingMode: "environment" }`,
draws the live `<video>` frame to a canvas, and calls `toDataURL("image/jpeg")`.
That is a *preview-stream grab*, which on most phones is well below what the
camera can actually take. The file opens with a comment about `react-webcam`
being broken on iOS, so iOS Safari is the binding constraint on any replacement.

**Worth testing, roughly in order of payoff-to-risk:**

- `track.getCapabilities()` → `applyConstraints()` to request the track's real
  maximum instead of a hard-coded 2048.
- `ImageCapture.takePhoto()`, which grabs a full still rather than a preview
  frame — but check current Safari support before committing to it, and keep the
  canvas path as the fallback.
- An explicit quality argument to `toDataURL("image/jpeg", q)`; the default is
  0.92 and is probably not what we want either way.
- `<input type="file" accept="image/*" capture="environment">` as a last resort:
  full sensor resolution via the native camera app, at the cost of leaving the
  game UI, which likely makes it unusable for a shooting mechanic.

**Note the ceiling this actually raises.** `prepare_for_vision()` downsizes to
`max_dimension = 1024` before the model sees anything, so a bigger original does
**not** help the first-pass read directly. It helps in two places: `zoom_image()`
deliberately crops from the *original* (that is the whole point of the zoom), and
the escalation path in #11 would want the largest image available. Raising
`max_dimension` is a separate, cheaper experiment worth running alongside — and
one that R2 can score.

Also weigh the cost: shot images are stored base64 in a database column, so
resolution multiplies straight into database size and upload time on a phone
network mid-game.

---

### #11 — Escalate the hard cases to a stronger model

**The idea.** When the posterior from #5 — GPS prior included — leaves the top
candidate below a threshold, or leaves two candidates tied, hand the case to a
stronger model (Opus, or Gemini) together with everything the cheap pass could
not use: the full-resolution photo, the zoom, the ranked candidate list _with
their prior probabilities and their outfits_, and **reference photographs of each
candidate taken at the start of the game**.

This is the largest item on the list. It has three separable pieces:

**(a) Reference photos of players — a prerequisite, and useful on its own.**
There is no capture flow today. Needs: where the photo is taken (onboarding on
the player's own phone, per `OnboardingView.js`, or admin-side at the start), a
place to store it (following `Shot.image_base64`'s pattern is the pragmatic
choice, at the cost of database size), and a deletion story — these are
photographs of identifiable people, and they should not outlive the game. A
game reset should take them with it.

**(b) The escalation trigger and the second client.** `backend/vision_client.py`
is already model-agnostic and reads `OPENROUTER_MODEL` from the environment, so a
second model is a second configured client rather than a new integration. The
trigger belongs next to the decode from #5 — escalate on
`not confident or ambiguous`, with its own threshold, and cap the candidate set
by the GPS prior (top ~5) because each candidate adds a reference photo to the
request and the bill scales with it.

**(c) The prompt for the escalated call is a different question.** The cheap pass
asks "what colours is this person wearing"; the escalation asks "which of these
five people is this, or none of them", with the priors stated. Keep it in the
same observe-then-decide shape: the model reports which candidate it matches and
how sure it is, Python applies the threshold.

**Why it is last.** It is a refinement of a pipeline that is currently
misjudging hits (#4) and throwing away good reads (#5) — those are worth more
per unit effort, and escalation built on top of an untrustworthy first pass will
mostly escalate the wrong things. It also cannot be tuned without R2.

**Depends on:** #5 (the posterior is its trigger), R2 (its threshold), and
benefits from #13.

---

## Proposed additions

- **R2 — the adjudication scorecard**, above. Strongly recommended: it is nearly
  free, and #4, #5, #11 and #13 all currently have no way to tell whether a
  change helped.
- **R1 — an offline replay harness** (a subset of R2): point a script at saved
  shot images plus their admin verdicts and re-run a prompt variant over them
  without a live game. Falls out of R2 almost for free, and is what makes #4
  tractable in an afternoon rather than over several game nights.

---

## Open questions

Answers to these change the shape of the work, not just its order.

1. **Is House Absolute in Westminster?** Assumed here: yes, #6/#7/#12 are all the
   same venue and the next game is a Westminster game. Note `HOUSE_ABSOLUTE` is
   currently a landmark in the *resort* test venue, so the name travels with the
   base rather than the place.
2. **Should the player-facing shot history name the target?** #2 gives the admin
   a name. Telling a shooter "CharlesBot thinks you hit Alice" before an admin has
   confirmed it leaks a player's position and identity to the other team, and it
   is wrong often enough to be a poor promise. Suggestion: name the target in the
   admin queue, and keep the player's view to hit / miss / bystander.
3. **When are the reference photos for #11 taken** — by the player at onboarding,
   or by an admin at the start of the night? The second is better lit, better
   framed and more likely to actually happen; the first scales without a queue at
   the door.
4. **How long do the reference photos live?** Suggestion: deleted with the game.
5. **Does the trousers channel survive contact with self-selection (#10)?** The
   trousers palette is already restricted to 5 colours because people wear what
   they own. If players are picking outfits rather than being issued them, this
   is the channel most likely to be wrong on the night.
