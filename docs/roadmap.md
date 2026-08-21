# Roadmap

The planned work, re-ordered from the order it was thought of into the order it
wants doing. Nothing here is implemented yet: this file is the record of intent,
not a changelog.

Each item keeps its **original number** (`#1` … `#14`) so it can be matched back
to the list it came from. Items prefixed `R` are additions proposed while
writing this up.

Every software item names the files it lands in, because most of them are
smaller than they sound: the pure identity module and the soft decoder already
exist and are tested, and several items are a matter of *wiring what is there*
rather than writing something new.

---

## The date drives everything

**The next game is Saturday 19 September 2026.** That is four weeks out, and it
changes the ordering completely: the logistics track has a hard, unmovable
deadline and most of the recognition work does not. Anything that has to be
bought, agreed with a landlord, printed, or worn by a person is on the critical
path. Anything that only has to be true in the code can slip to after the game.

**The safety valve.** `ai_auto_actions_enabled` defaults to off and is a
separate toggle from `ai_shot_review_enabled`. So if the recognition work is not
finished by the 19th, the game still runs: CharlesBot annotates the queue and the
admin adjudicates every shot by hand, exactly as before. Nothing in track A is
allowed to become a blocker for the night — it is all upside.

### Working backwards from the 19th

| By             | What must be true                                                                                                                          | Items        |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------ |
| **Now**        | Armbands ordered. Pub conversations started — a landlord agreeing to hold a code is a conversation with human latency, not a data problem. | #9, #6       |
| **~31 Aug**    | Westminster map drawn and active. Colour-picking page built. Drops scouted.                                                                | #12, #10, #7 |
| **~7 Sept**    | Picking page live; players choosing outfits and finding the clothes.                                                                       | #10          |
| **~12 Sept**   | Picks closed. Everything printed.                                                                                                          | #8           |
| **15–19 Sept** | Drops placed, pub packs delivered, go/no-go on auto-actions.                                                                               | #7, #8       |
| **After**      | Everything in tracks A and C that did not fit.                                                                                             | the rest     |

The tightest link in that chain is **#10 → #8**: nobody can be handed an
appearance card until they have chosen an appearance, and nobody can choose one
until the page exists. That makes the colour-picking page the single piece of
software with a real deadline, which is not where it started on the list.

## Priority order

| Order | Item                                        | Deadline                     | Why here                                                                                                       |
| ----- | ------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1     | **#9** Buy armbands                         | Now                          | Longest lead time; #10 and #8 both wait on it. In flight.                                                      |
| 2     | **#6** Find the pubs                        | Now → 7 Sept                 | Needs other people to say yes. Start the conversations first, collect the data second.                         |
| 3     | **#12** Redraw the Westminster map          | ~31 Aug                      | Blocks #7, and retires the temporary resort test venue.                                                        |
| 4     | **#10** Colour-picking page                 | ~31 Aug build, live ~7 Sept  | The only software on the critical path. Also the mitigation for bring-your-own garments (see #9).              |
| 5     | **#7** Find the drop locations              | ~7 Sept                      | Needs #12 to place them; feeds #8.                                                                             |
| 6     | **#8** Print the run                        | ~12 Sept                     | Everything above becomes paper here.                                                                           |
| 7     | **#4** False hits                           | Before the 19th *if it fits* | The one recognition item worth rushing; if it slips, run with auto-actions off.                                |
| 8     | **R1** Offline replay harness               | With #4                      | What makes #4 tractable in the time available rather than guesswork.                                           |
| 9     | **R3** Screen Wake Lock                     | Before the 19th *if it fits* | Thirty lines, and it stops the phone sleeping while it is being held as a weapon.                              |
| —     | *— the game —*                              | **19 Sept**                  |                                                                                                                |
| 10    | **#1** "CharlesBot", not "AI"               | —                            | Twenty minutes, independent of everything. Ship whenever.                                                      |
| 11    | **R2** Adjudication scorecard               | —                            | The full version of R1; the game itself generates the data it needs.                                           |
| 12    | **#5** Use every channel, not just armbands | —                            | Wastes real information today and hands the admin "unable to tell".                                            |
| 13    | **#3** Ranked candidates in the review UI   | —                            | The surface of #5; same piece of plumbing.                                                                     |
| 14    | **#2** "CharlesBot thinks: hit on *name*"   | —                            | Needs the name, so it needs #5/#3.                                                                             |
| 15    | **#13** Higher-resolution capture           | —                            | Promoted: with #14 parked this is the *only* route to better photos, and #4, #5 and #11 all want them.         |
| 16    | **R4** Service worker and Web Push          | —                            | The notification half of what the native app was for, at no cost. Largest single win available to the web app. |
| 17    | **#11** Escalation to a stronger model      | —                            | Needs #5's posterior and a new photo-capture flow.                                                             |
| —     | **#14** Native app                          | **Parked**                   | Decided against: the Apple fee is unavoidable for iOS in any form. Analysis kept for whenever it is revisited. |

---

## Decisions taken

Recorded here so they are not re-litigated:

- **The game is on 19 September 2026.**
- **We provide the armbands only** (#9). Hats, tops and trousers are the
  player's own. See #9 for what that costs and what to do about it.
- **Players pick their own colours from a pre-game web page** (#10), not on the
  night and not assigned by an admin.
- **`TEAM_CHANNEL` moves from the hat to the armbands** (#9), so team identity
  rests on the one garment we supply. Follows from armbands-only; see #9.
- **No native app and no app stores** (#14), for this run and by default. The
  Apple Developer Program fee is unavoidable for iOS in *any* distribution form,
  TestFlight included, and it is not worth paying for a party game. #14 stays on
  file as a future extension; the capability work it was meant to unlock moves to
  R3 and R4, which cost nothing.
- **Pub and drop locations live in the repo** as venue landmarks (#6, #7). The
  repository is public, so this publishes every hiding place to anyone who
  thinks to look; accepted deliberately on the grounds that this is a game
  between friends and the alternative is a second place to keep things in sync.

---

## Track B — the critical path

### #9 — Buy armbands *(in flight)*

**The constraint.** The palettes in `backend/identity/config.py` were chosen by
optimising worst-case CIEDE2000 separation across three illuminants (daylight,
warm-white LED, sodium street lighting) — see plan §9.1 and §12.4. Substituting
"close enough" colours because that is what was in stock erodes the property the
whole scheme rests on. Buy against the hex values, and where a real product
misses, **record what was actually bought** so the palette can be re-checked
rather than silently drifting.

Needed: **7 armband colours** (the main palette).

**The consequence of not providing hats.** `backend/identity/allocation.py`
currently spends the hat channel (`TEAM_CHANNEL`) on telling teams apart by eye:
every member of a team gets the same hat colour and no two teams share one. That
only works if people turn up wearing a hat in a specific one of seven colours —
which, with hats now bring-your-own, most will not.

**Decided: `TEAM_CHANNEL` moves to the armbands.** The armbands are the one
garment we control, so they are the only channel guaranteed to be both present
and the right colour. Making them the team marker means:

- friend-or-foe at 30 m survives, and reads off the item that is easiest to see;
- the allocation constraint lands on the channel that is never an erasure, so it
  costs the decoder nothing;
- the hat degrades gracefully into "a fourth channel when somebody happens to be
  wearing one", which is what it will be in practice.

This is a change to `TEAM_CHANNEL` in `backend/identity/config.py` and the tests
around `allocate_team_slots`; the decoder is unaffected, since allocation is
policy and not part of the code. **Do this before #10**, because the picking page
has to show people the right constraint.

**Risk to name out loud:** three of the four channels are now bring-your-own. The
scheme's accuracy on the night depends on players actually owning and wearing the
colours they picked. #10 is the mitigation — see below.

---

### #6 — Find the pubs near House Absolute

**What.** A shortlist of pubs within a chosen radius of House Absolute, probably
harvested from the existing Google Maps list (the Norby-playlist replacement)
rather than assembled from scratch.

**Start with the conversations, not the data.** The gating question is whether a
landlord will keep a printed code behind the bar, and that answer arrives on
human timescales. Getting a yes from four pubs is worth more than a perfect list
of forty.

**Getting the list out of Google Maps.** A saved list can be exported via Google
Takeout (Saved → `.csv` of place URLs) or shared as a link; either way the useful
output is name + lat/long per pub, which is exactly the shape of
`Venue.landmarks` in `backend/venues.py`.

**Per pub, record:** coordinates, opening hours on a Saturday night, and whether
they have agreed.

**Lands in:** `backend/venues.py` as landmarks on the Westminster venue.
**Feeds:** #8, #12.

---

### #12 — Redraw the map for Westminster

**Current state.** `ACTIVE_VENUE` in `backend/venues.py` is
`VENUES["koyao_resort"]`, a temporary test venue, with a `TODO` saying to swap
back before it is played for real. Kingston is the other entry. This item retires
that `TODO`.

**What a venue needs** (`Venue` / `VenueMap`):

- the map image, dropped into `react-ui/src/images/` with one line added to
  `react-ui/src/mapImages.js` (the `image` key resolves against it);
- `width_px` / `height_px`;
- two `MapReferencePoint`s (pixel *and* lat/long). Deriving them from a known
  tile crop — as the resort venue does, using the top-left and bottom-right
  pixels — is far more accurate than eyeballing two landmarks;
- `corner_width_km` for the mini-map window. Westminster is a much bigger area
  than the resort, so this wants choosing deliberately rather than copying;
- the landmarks circles can be placed at (#6, #7).

Nothing in `MapView.js` should need touching. `VenueMap.bounds` exists so the
tests can check that every landmark actually lands on the image — keep that
passing, and expect it to catch at least one coordinate typo.

**Do this before #7**, since a drop that is not on the map cannot be used, and it
is the natural place to sanity-check the game area's extent.

---

### #10 — Let players pick their own colours *(the software on the critical path)*

**Current state.** `identity_admin.build_join_codes(game_id, slots_per_team)`
pre-allocates a block of slots per team (one team-channel colour each, via
`allocation.allocate_team_slots`) and mints one signed join URL **per slot**;
`claim_join_slot()` claims whatever slot the scanned code carries. So today a
player is handed an outfit, they do not choose one.

**Suggested shape** (minimal change to what exists): keep the signed join code as
the entry point, but let it carry the **team's block** rather than a single slot,
and have the claim flow present the unclaimed slots in that block and take the
player's pick. `build_join_codes` then mints one code per team instead of one per
slot, which also makes the print run smaller.

**What the page needs:**

- the team's *unclaimed* slots rendered as outfits with colour swatches —
  `hex_for()` and the swatch rendering in `AdminIdentity.js` / `IdentityDemo.js`
  already exist to reuse;
- an explanation that the armbands are fixed by the team (see #9) and the choice
  is across the other three channels;
- an **atomic** claim: several people will be picking at once on their phones,
  and two players must never end up wearing the same codeword;
- it must work **before the night** and before anybody has a `User` row — plan
  §8.2 is explicit about this, and the whole point is that people need to know
  what to wear in advance.

**Self-selection is now load-bearing, not a nicety.** With only the armbands
provided (#9), three channels depend on players owning the right colours. Letting
someone choose the slot whose t-shirt, trousers and hat they *already have* is
the single best lever on how accurate the identification is on the night. So the
page should be built around "which of these can you actually wear on Saturday",
not "which is prettiest".

**Worth considering while building it:** ask each player to confirm they have the
garments, and optionally to photograph themselves in the outfit. That
verification is useful on its own — and it is exactly the reference-photo capture
flow that #11 needs, obtained for free at the one moment every player is already
engaged with the app.

**Depends on:** #9 (both the kit and the `TEAM_CHANNEL` move). **Feeds:** #8.

---

### #7 — Find new drop locations

**What.** Places a QR code can be physically hidden that will not read, to a
passer-by or a police officer, as somebody taping a device to street furniture.

**Suggested criteria** to write down and apply consistently:

- publicly accessible without trespass, and reachable at night;
- unremarkable to leave something at — a pub garden, a noticeboard, a café, a
  shop with permission — in preference to street furniture;
- **nothing near a security-sensitive site.** In Westminster specifically this
  rules out a great deal: government buildings, embassies, barracks, and station
  or Tube infrastructure. This is the reason the item exists — treat it as a hard
  exclusion zone drawn on the map in advance, not a judgement call made at 11pm;
- sheltered enough that paper survives rain;
- inside the game area and on the map (hence #12 first).

**Mitigation to build into the print run** (#8): every card carries a line saying
what it is and a contact number, so anyone who finds one gets an answer rather
than a fright. Cheap, and it converts the failure mode from "incident" to
"curiosity".

**Lands in:** `backend/venues.py` as landmarks. **Depends on:** #12.
**Feeds:** #8.

---

### #8 — Print everything

**Three separate print runs**, all landing by ~12 September:

1. **Drop codes** for the new locations (#7) — existing tooling:
   `backend/generate_qr_items.py` plus the templates in
   `backend/image_templates/`. Add the "this is a game, ring this number" line
   from #7 to the template.
2. **Pub handouts** (#6) — probably a different format: something a bar will
   actually keep on display.
3. **Player appearance cards** (#10) — what to wear, per player, plus their join
   code. `build_join_codes` already returns `appearance` per slot for exactly
   this.

**If the schedule slips**, the drop codes are the ones with a hard dependency on
physical placement; the appearance cards can be sent digitally as a fallback,
since by then #10 has already told each player what they are wearing.

---

## Track A — recognition correctness

### #4 — CharlesBot calls clear misses "hit" *(the one worth rushing)*

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
   only a miss if it entirely misses the person"_, which reads as an invitation
   to count anything near a person. It never says the crosshair marks a **single
   point** that must land **on** them. Rewrite it around the point: the crosshair
   is one pixel; a hit is that pixel lying on the person's body or clothing;
   beside them, above them, on the ground in front of them, or between two people
   is a **miss**.
2. **The crosshair has a hole in the middle.** `_draw_aim_marker_on()`
   (`backend/image_processing.py`) draws four arms with a gap: `arm =
max_dim // 20`, `gap = arm // 3`. On the 1024 px image that
   `prepare_for_vision()` sends, that is a ~34 px *empty square* at the exact
   place the shot landed — and a distant target can be smaller than the hole. The
   model is being asked "is the thing under the crosshair a person" while the
   thing is hidden by the crosshair, and anyone standing in that gap looks
   "under" it. Try a small solid dot or a 1 px centre tick, and re-measure.
3. **The prompt applies pressure towards a decision.** _"You MUST ultimately make
   a decision on whether the shot is hitting a person or not"_ pushes towards a
   call, and the surrounding text gives no reason to prefer "miss" when torn.
   State the asymmetry explicitly: a wrongly-called miss costs the shooter one
   bullet; a wrongly-called hit takes a life off somebody who was never shot.
   When in doubt, it is a miss.
4. **Let Python own the threshold.** In keeping with the module's stated
   principle (*the model observes; Python decides*), replace the boolean with an
   observation the model can actually see: where the crosshair sits relative to
   the nearest person — e.g. `on_body` / `touching_their_outline` /
   `clearly_beside_them` / `nobody_near` — plus a rough gap in body-widths.
   `classify()` then applies the rule, so tightening or loosening it is a
   constant in Python and a test, not a prompt rewrite.

**Done when** the replay set from R1 shows the false-hit rate down to something
an admin can live with, with the false-miss rate reported alongside it (this
trade is the whole game; do not optimise one silently).

**If it does not fit before the 19th**, leave `ai_auto_actions_enabled` off and
play with CharlesBot annotating only. That is the pre-existing behaviour and it
works.

---

### R1 / R2 — Measure what CharlesBot gets wrong *(proposed)*

Every shot already carries both halves of a labelled example:
`Shot.ai_review` (the JSON verdict) and `Shot.result` (`"hit"` / `"miss"` /
`"bystander"` / `"refunded"`, plus `target_user_id`). Nothing compares them. Every
shot photo is also written to disk by `save_image()`
(`backend/image_processing.py`).

**R1, before the game — the replay harness.** A script that points at saved shot
images plus their admin verdicts and re-runs a prompt variant over them offline,
reporting the confusion matrix. Small, and it is the difference between #4 taking
an afternoon and #4 taking several game nights.

**R2, after the game — the scorecard.** The admin-facing version: an endpoint and
a page reporting CharlesBot's outcome against the admin's over a game or all
games, broken down by whether the zoom was used and by how many channels were
readable, plus the same numbers restricted to reviews above the auto-action
confidence threshold — which is the number that decides whether
`ai_auto_actions_enabled` is safe to switch on. The 19th will generate more real
data than everything to date, so build this to consume it.

---

### #5 — Two readable channels should still identify somebody

**Symptom.** A distant shot read two of the four channels correctly. Two erasures
is exactly what the `[4,2,3]` code is meant to survive, but CharlesBot said it
could not tell — because neither of the two was the armbands.

**Why it does that.** `classify()` in `backend/shot_vision.py` treats the
armbands as the *player marker*: bystanders do not wear armbands, so armbands
read ⇒ player. When the armbands are erased, it falls back to demanding **all
three** other channels, and anything less is declared a bystander. Hence "two
channels, no armbands" → nothing. The reasoning behind that is sound as far as it
goes (with only `k = 2` readable positions, any reading completes to *some*
codeword, so the code vouches for nothing) — but it answers the wrong question.

**The fix is to split one question into two.**

- **"Is this person a player at all?"** genuinely needs redundancy, and armbands
  genuinely are strong evidence — more so now that they are the one garment we
  supply (#9). Keep that, but as *evidence*, not as a gate.
- **"Which player is it?"** does **not** need the full codeword space. The
  candidate set is not the 34 usable slots, it is the handful of living players
  on other teams who were near the shooter — and two correctly-read channels
  discriminate sharply within a set that small, especially once the GPS prior is
  applied.

Today the second question is never asked when the first one fails.

**The plumbing already exists and is unused.**

- `shot_vision.to_reading()` builds the `Reading` the soft decoder consumes. Its
  own docstring says nothing calls it yet.
- `backend/identity/decoder.py` `decode()` takes a `Reading`, a candidate set and
  a `Prior`, and returns ranked posteriors plus `inconsistent` / `ambiguous` /
  `confident` flags.
- `Shot.location_context` already stores every player's position at the moment
  the shot was fired (`user_interface.submit_shot`), which is the GPS prior in
  plan §8.3 — no schema change needed.

So the work is an integration-layer module (per the plan's rule that
`backend/identity/` stays pure) that builds the candidate set from the shot's
game, builds the `Prior` from `location_context` (start with a Gaussian or
inverse-distance in metres), calls `decode()`, and stores the ranked result
alongside the existing review payload.

**Keep the auto-action gate conservative.** `slot_candidates_from_review()`
requires `k + 1` readable channels and is used by `backend/shot_auto_actions.py`.
That gate is *right* for firing a hit automatically and should stay. What changes
is that the admin's view is no longer limited to what the auto-actions are
willing to act on: a two-channel read produces "if this is a player, it is most
likely X (p = 0.8)" instead of silence.

**Done when** a two-readable-channel photo produces a ranked candidate list, and
the auto-action behaviour is unchanged. **Feeds:** #3, #2, #11.

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
nobody". **Depends on:** #5.

---

### #2 — "CharlesBot thinks this is a hit on *Alice*"

**What.** The verdict should name the person, not just the outcome.

**Where.** `OUTCOME_LABELS` in `react-ui/src/ShotQueue.js` (admin) and the
`AI thinks: ${shot.ai_suggestion}` line in `react-ui/src/ShotHistory.js`
(player-facing).

**The backend piece.** The stored review holds a `slot`, not a name — the slot →
user resolution currently lives in `shot_auto_actions._decide()`. Resolve it at
read time in the review endpoint rather than denormalising a name into the stored
JSON, so a later identity correction is reflected without rewriting history.

**Wording needs to degrade gracefully**, since the name is often unknown:

| Situation               | Admin sees                                                   |
| ----------------------- | ------------------------------------------------------------ |
| One confident candidate | *CharlesBot thinks: hit on Alice*                            |
| Several candidates      | *CharlesBot thinks: hit — probably Alice (0.6) or Bob (0.3)* |
| Player, unidentified    | *CharlesBot thinks: hit on a player, but can't tell who*     |
| Not a player            | *CharlesBot thinks: that's a bystander, not a hit*           |
| No person               | *CharlesBot thinks: miss*                                    |

See the open question about whether the **player-facing** history should name the
target at all. **Depends on:** #5, #3.

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

Independent of everything else and about twenty minutes' work, so it can ship
whenever — including before the game, since it touches nothing that could break
the night.

---

## Track C — after the game

### #13 — Better photos, if the platform now allows it

**Current path.** `react-ui/src/MyWebcam.js` requests
`{ width: { ideal: 2048 }, height: { ideal: 1080 }, facingMode: "environment" }`,
draws the live `<video>` frame to a canvas, and calls `toDataURL("image/jpeg")`.
That is a *preview-stream grab*, which on most phones is well below what the
camera can actually take. The file opens with a comment about `react-webcam`
being broken on iOS, so iOS Safari is the binding constraint on any replacement.

**Worth testing, roughly in order of payoff-to-risk:**

- `track.getCapabilities()` → `applyConstraints()` to request the track's real
  maximum instead of a hard-coded 2048;
- `ImageCapture.takePhoto()`, which grabs a full still rather than a preview
  frame — but check current Safari support before committing to it, and keep the
  canvas path as the fallback;
- an explicit quality argument to `toDataURL("image/jpeg", q)`; the default is
  0.92 and is probably not what we want either way;
- `<input type="file" accept="image/*" capture="environment">` as a last resort:
  full sensor resolution via the native camera app, at the cost of leaving the
  game UI, which likely makes it unusable for a shooting mechanic.

**Note the ceiling this actually raises.** `prepare_for_vision()` downsizes to
`max_dimension = 1024` before the model sees anything, so a bigger original does
**not** help the first-pass read directly. It helps in two places: `zoom_image()`
deliberately crops from the *original* (that is the whole point of the zoom), and
the escalation path in #11 would want the largest image available. Raising
`max_dimension` is a separate, cheaper experiment worth running alongside — and
one that R1 can score.

Also weigh the cost: shot images are stored base64 in a database column, so
resolution multiplies straight into database size and upload time on a phone
network mid-game.

**Promoted now that #14 is parked.** This was written up as the stopgap for a
native camera that is no longer coming, which makes it the only route to better
photographs that exists. That matters more than it sounds: #4 is partly a
question of whether the model can see the target at all, #5's erasures are mostly
distant targets, and #11 wants the largest image available. Worth doing properly
rather than as a holding action — including the `max_dimension` experiment, which
is a one-line change that R1 can score.

---

### #11 — Escalate the hard cases to a stronger model

**The idea.** When the posterior from #5 — GPS prior included — leaves the top
candidate below a threshold, or leaves two candidates tied, hand the case to a
stronger model (Opus, or Gemini) together with everything the cheap pass could
not use: the full-resolution photo, the zoom, the ranked candidate list *with
their prior probabilities and their outfits*, and **reference photographs of each
candidate taken at the start of the game**.

This is the largest item in track A/C. It has three separable pieces:

**(a) Reference photos of players — a prerequisite, and useful on its own.**
There is no capture flow today. Needs: where the photo is taken, a place to store
it (following `Shot.image_base64`'s pattern is the pragmatic choice, at the cost
of database size), and a deletion story — these are photographs of identifiable
people and they should not outlive the game; a game reset should take them with
it. **See #10:** the colour-picking page is the natural place to capture these,
since it is the one moment every player is already in the app and thinking about
what they will be wearing.

**(b) The escalation trigger and the second client.** `backend/vision_client.py`
is already model-agnostic and reads `OPENROUTER_MODEL` from the environment, so a
second model is a second configured client rather than a new integration. The
trigger belongs next to the decode from #5 — escalate on
`not confident or ambiguous`, with its own threshold, and cap the candidate set
by the GPS prior (top ~5), because each candidate adds a reference photo to the
request and the bill scales with it.

**(c) The prompt for the escalated call is a different question.** The cheap pass
asks "what colours is this person wearing"; the escalation asks "which of these
five people is this, or none of them", with the priors stated. Keep it in the
same observe-then-decide shape: the model reports which candidate it matches and
how sure it is, Python applies the threshold.

**Depends on:** #5 (the posterior is its trigger), R2 (its threshold), and
benefits from #13 or #14.

---

### #14 — A native app: React Native or Flutter *(parked)*

**Decided against, August 2026.** Not for the 19th, and not by default
afterwards. The blocker is not the engineering estimate below but the fee: Apple
charges for the Developer Program and there is **no free way to put an app on an
iPhone**, TestFlight and ad-hoc distribution included. Expo's free tier is
generous but it does not touch that — it covers building and updating, not the
right to install. Android alone could be done for nothing by sideloading an APK,
but an iPhone-less party game is not a game.

Everything below is kept as-is, because the analysis is the expensive part and it
will still be true whenever this is reconsidered. What it was *for* —
background support — moves to **R3** and **R4**, which need no accounts and no
fees.

**The motivation was.** Two real weaknesses, neither of which the current web app
can fully fix: **background support** and **native camera access**. Both are
worth having; both cost months.

**What "no background support" means concretely today.** The app is an
add-to-home-screen PWA (`react-ui/src/AddToHomeScreen.js` plus
`react-ui/public/manifest.json`) with **no service worker**, so:

- **the screen sleeps mid-game.** There is no Screen Wake Lock, so the phone
  locks itself while it is being held as a weapon, and the camera stream, the
  SSE connection and the position watch all have to come back up afterwards;
- **nothing is delivered while the app is backgrounded.** The recovery is
  already handled well — `UpdateListener.js` has a keepalive watchdog that
  restarts the stream when the counter desyncs or nothing has arrived for a
  while, so a player who returns to the app is resynchronised. What cannot be
  fixed from inside the page is that a suspended tab receives nothing *at the
  time*, so ticker messages and circle warnings wait for the player to look;
- **there are no push notifications at all**, so nothing can reach a player who
  is not looking at the screen. For a game about being ambushed in the street,
  that is the biggest gap on this list;
- **the position watch stops when the page is suspended.** Note the app is
  already doing the right thing here — `MapView.js` runs a three-tier watch
  (expanded / foreground / background) that drops to `enableHighAccuracy: false`
  and a 15 s upload interval once `document.hidden` — so this is a platform
  ceiling, not a gap in the code. No browser keeps the callback firing once the
  screen locks.

**Try the cheap web fixes first — genuinely, before committing months.** Several
of the above have web answers that are days rather than months of work:

**Screen Wake Lock** (`navigator.wakeLock.request("screen")`) asks the OS not to
dim or lock the screen while the page is visible. It returns a sentinel object
that the browser releases automatically whenever the tab is hidden, so it has to
be re-acquired on `visibilitychange` — that re-acquisition is the part people
forget. Secure context only, which this app already is. Supported on Chrome and,
since 16.4, on iOS Safari.

It buys exactly one thing, and it is the thing a player notices most: the phone
stops locking itself mid-game. No more unlocking to fire, and no more tearing
down and rebuilding the camera stream, the SSE connection and the position watch
every time it sleeps. It does **not** run anything in the background — it only
keeps the screen awake while the app is in front. Perhaps thirty lines as a
`useWakeLock()` hook mounted in `UserMode`, and worth a toggle, since holding the
screen on is the single biggest battery draw in the game.

**Web Push** lets the *server* wake the phone with a notification when the app is
closed. It needs four pieces, none of which exist yet: a **service worker** (the
app has none) that handles the `push` event and calls `showNotification`; a
`PushSubscription` obtained from `pushManager.subscribe()` with a VAPID public
key; storage for those subscriptions against the `User` row; and a sender on the
backend — `pywebpush` is the usual Python choice — that signs with the VAPID
private key and posts to whatever endpoint the subscription names.

For this game it closes the ambush gap: "you have been shot", "the circle is
closing", "your shot was validated" can reach somebody whose phone is in their
pocket. Two constraints worth knowing before planning around it. On iOS it works
only for PWAs **installed to the home screen**, which makes
`AddToHomeScreen.js` mandatory rather than a nicety, and permission must be
requested from a user gesture. And a service worker only wakes *briefly*, to
handle a push the server sent — it is not a background thread. It cannot poll,
cannot hold the SSE stream open, and cannot read the GPS.

**Background geolocation is the one with no web answer at all.** Neither of the
above helps: a suspended page stops reporting positions, and a service worker has
no geolocation access. So player positions go stale whenever a phone is pocketed
between engagements — which matters beyond the map, because `location_context` is
captured at shot time from those same stored positions and is exactly what the
GPS prior in #5 leans on. Stale positions mean a weaker prior on every
identification. If that is a hard requirement, it is the argument for going
native, and it should be *the* argument — not the camera, which #13 can partly
address.

Doing that spike first is the highest-value thing here: it either solves most of
the problem for 1% of the cost, or it produces a specific, defensible reason to
go native.

**What makes the native project tractable.** The backend is already a REST and
SSE API with almost no coupling to the web client, and — the big one — **the
admin interface never needs to be native**. `AdminMode`, `ShotQueue`,
`AdminIdentity` and `IdentityDemo` are a desk job done on a phone or a laptop;
they stay a web page, and `server/` keeps serving them. That is very nearly half
the frontend excluded from the port before any work starts.

### How big is it, measured

`react-ui/src`, counted rather than guessed:

| | Lines | Fate on the native path |
| --- | --- | --- |
| Admin-only JS | 3,223 | **Untouched.** Stays a web page. |
| Player + shared JS | 3,359 | Ported. |
| CSS Modules | 1,178 | Dead — RN has no CSS. Re-expressed as `StyleSheet`. |
| `modernizr.js` (vendored) | 389 | Dead. |
| Player-side tests | 2,887 | Migrated to `@testing-library/react-native`. |
| Admin-side tests | 2,091 | Untouched. |

**Ten of the twenty runtime dependencies are web-only** and need a replacement:
`bootstrap` / `react-bootstrap`, `framer-motion`, `react-tooltip`,
`react-zoom-pan-pinch`, `qr-scanner`, `use-sound`, `react-full-screen`,
`add-to-homescreen`, `react-router-dom`, `react-qr-code`. Some of those swaps are
upgrades — `expo-camera` does in a few lines what `MyWebcam.js` hand-rolls around
iOS bugs, and its barcode scanner replaces `qr-scanner` outright.

*(Aside: `@maplibre/maplibre-react-native` is already in `package.json` and
imported nowhere — an abandoned experiment. Delete it.)*

**`MapView.js` is the single hardest piece** and deserves its own estimate. It is
not a map widget: it is a `div` with a `backgroundImage` whose
`background-position` and `background-size` are computed from the venue's
georeferencing, with absolutely-positioned dots at `left`/`bottom`, wrapped in
`react-zoom-pan-pinch`, and laid out in three modes (corner, popped-out,
expanded) by CSS. None of that mechanism exists in React Native. The geometry in
`venue.js` ports untouched; the rendering is a rewrite on
`react-native-gesture-handler` + `reanimated`. Budget two or three weekends for
this component alone.

**The one thing that genuinely does touch the backend.** Player identity is a
signed session **cookie** (`request.session["UUID"]` in `backend/user_id.py`).
That mostly survives in a native app's `fetch`, but it does *not* survive
reliably in the two places this project actually needs: an `EventSource`
polyfill, and a **background location task**, which runs in its own context while
the app is asleep. So `get_user_id` needs to accept a bearer token as well as a
cookie, issued at join and kept in `expo-secure-store`. It is a small change —
but it is on the critical path for background GPS, which is the entire
justification for going native, so it cannot be deferred. (It would also retire
the `no_cookie_clients` IP-keyed fallback, which is the shakiest thing in that
file and would misbehave with a party's worth of phones behind one carrier NAT.)

**Framework: React Native with Expo**, if it happens at all. It keeps the
language and the React idioms this codebase is already written in; Expo has
first-party modules aimed at exactly the three weaknesses (`expo-camera`,
`expo-location` background updates, `expo-notifications`); and OTA updates avoid
an app-store round trip for every iteration. Flutter's advantages — rendering
consistency, a better story for custom-drawn UI like the map — are real but do
not outweigh throwing away the existing JavaScript, for a personal project.

### Four ways to do it, and what each costs

"Keep supporting the web version" can mean four quite different things, and the
difficulty is decided almost entirely by which one:

**D. A thin native shell — recommended.** An Expo app that wraps the existing web
app in a `WebView` and adds *only* the two things the web cannot do: a background
location task posting to `/api/set_location`, and push notifications. The game UI
stays the web app, which keeps being maintained once rather than twice. Camera
stays on the web path, so #13 still applies and the native-camera win is
deferred. **~2–3 weekends**, most of it distribution faff rather than code.

**A. Native player app; admin stays web.** The player web app is retired. Two
codebases, no shared abstraction, no risk to admin. **~8–12 weekends** to reach
parity — and parity is not the goal, so note that the features that motivate the
whole exercise (background location, push) are perhaps a fifth of that number.
Everything else is re-typing UI that already works.

**C. Two frontends over a shared logic core.** As A, plus extracting the genuinely
portable ~500 lines (`venue.js` geometry, the `utils.js` API layer,
`shotHistoryStore.js`, `UpdateListener.js`'s protocol handling) into a module both
consume, so the web player app survives as a fallback for people who will not
install anything. **A + ~1 weekend**, plus a permanent duplication tax on every
feature thereafter. The right answer only if the web player app must live.

**B. One universal codebase via `react-native-web` / Expo web.** Sounds like the
answer and is the trap: it requires rewriting every style anyway, has no answer
for the `background-image` map, and the web output ends up *worse* than what
exists today. **A + 30–50%**, for a downgrade. Don't.

### The cost nobody counts

**Distribution friction.** Today a guest scans a QR code and is playing in
seconds. With a native app, every guest needs TestFlight (accept invite, install
TestFlight, install the app) or an Android sideload — *before* the night, on the
same critical path as the armbands and the printing, and it is a fresh way for
somebody to turn up unable to play. For a fixed guest list this is survivable,
but it should be weighed honestly against "background GPS is nicer", because it
is a certain cost against a speculative benefit.

**Recommendation: do the Wake Lock and Web Push spike first (days), then D
(2–3 weekends) if background GPS still matters after a game with the spike in
place.** Only consider A after playing a game on D and finding the camera to be
the binding constraint — by which point there is real evidence about whether the
install friction is tolerable.

**"App stores" and "native" are separate decisions.** This is a private game for
a known guest list, and public store distribution may be actively unhelpful:

- Apple requires a paid developer account (~£79/$99 a year) either way;
- App Review is a plausible obstacle for a game whose core loop is photographing
  people in the street — expect questions about user-generated content
  moderation, and about the camera and background-location justifications;
- **TestFlight and Android's internal-testing track distribute to a fixed list of
  people without public review**, which is exactly the shape of this game.

So: go native for the capabilities if the PWA spike says they are unreachable,
but treat a public listing as a later, optional decision rather than the goal.

### What it costs to run

**Expo's free tier is comfortably enough** (checked August 2026): 15 iOS and 15
Android builds *per month*, 1 concurrency on a low-priority queue, a 45-minute
build timeout, and EAS Update to 1,000 monthly active users. A game with twenty
players and a handful of builds a year is nowhere near any of those numbers. EAS
is optional anyway — `expo-updates` can point at a self-hosted update server, and
builds can be made locally with Xcode / Android Studio at no cost and no quota.
EAS Build's real value is not needing a Mac.

**The recurring cost is Apple's, not Expo's:** the Developer Program is ~£79/$99
a year and is required even for TestFlight. Google Play is a one-off $25, or
nothing at all if Android players sideload an APK.

**Over-the-air updates do not remove the need to build.** An OTA update ships
JavaScript and assets only; anything in the native layer needs a new binary:

- adding or upgrading a native module — so each capability added after the first
  build (`expo-notifications`, background `expo-location`) costs a build;
- changing permissions or entitlements — `UIBackgroundModes`,
  `ACCESS_BACKGROUND_LOCATION` and friends are native config;
- Expo SDK upgrades. Updates are bound to a **runtime version**, so an update
  built against a newer SDK is simply not served to an older binary — you cannot
  OTA past an SDK bump;
- store and OS requirements — Google Play mandates raising the target API level
  annually or the app stops being installable;
- **certificate and build expiry, which is the one that actually bites here.**
  TestFlight builds expire 90 days after upload, and iOS distribution
  certificates and provisioning profiles last a year. A game played once or twice
  a year on TestFlight therefore needs a fresh build *every time*, even if not a
  line of code changed. Confirm the current figures when planning, but budget for
  a rebuild per game night rather than a rebuild per release.

**On the shell path (D), OTA barely matters anyway.** The UI is served from our
own web server, so a UI change is an ordinary deploy of the React app: live
immediately, no runtime-version coupling, no MAU ceiling, no Expo involved. The
shell would only be rebuilt when its native capabilities change — or when
TestFlight expires it.

**Timeline.** Not before 19 September, and not close. Post-game, and probably
post-*next*-game — this is the kind of item that competes with everything else in
this file for the same evenings. It supersedes #13 if it happens.

---

### R3 — Screen Wake Lock *(proposed, and now the answer rather than a spike)*

`navigator.wakeLock.request("screen")` stops the phone locking itself while the
app is in front — see #14 for the mechanics and the re-acquisition trap. Roughly
thirty lines as a `useWakeLock()` hook mounted in `UserMode`, behind a toggle
because a screen held awake is the biggest battery draw in the game.

With #14 parked this stops being a step towards something and becomes the fix.
It is also the only item in this file that could plausibly be built and tested in
an evening before the 19th, and it removes a real irritation: the phone is being
held as a weapon, and it keeps going to sleep.

**Candidate for before the game**, alongside #4, if either evening exists.

---

### R4 — Service worker and Web Push *(proposed)*

The notification half of what #14 was for: let the server wake a player's phone
when the app is closed — "you have been shot", "the circle is closing". Needs a
service worker, a `PushSubscription` with a VAPID key, storage against the `User`
row, and a sender on the backend (`pywebpush`). Mechanics and the iOS
home-screen-install constraint are written up under #14.

Bigger than R3 and touching the backend, so **not before the 19th** — a service
worker misconfigured on the night would be a poor trade for a notification. After
the game, this is the largest single improvement available to the web app, and it
costs nothing but time.

Note it makes `AddToHomeScreen.js` mandatory for iPhone players rather than a
nicety, which is a change to how the game is joined and worth deciding
deliberately.

---

## Open questions

Answers to these change the shape of the work, not just its order.

1. **Is House Absolute in Westminster?** Assumed throughout: yes, and #6/#7/#12
   are all the same venue. Worth confirming, because #12's map crop depends on
   it. (Note `HOUSE_ABSOLUTE` is currently a landmark in the *resort* test venue,
   and the PWA manifest reads "Streetfight by House Absolute", so the name
   travels with the house rather than the place.)
2. **Should the player-facing shot history name the target?** #2 gives the admin
   a name. Telling a shooter "CharlesBot thinks you hit Alice" before an admin has
   confirmed it leaks a player's position and identity to the other team, and it
   is wrong often enough to be a poor promise. Suggestion: name the target in the
   admin queue, and keep the player's view to hit / miss / bystander.
3. **Do we ask players for a photo of themselves in their outfit at pick time?**
   Cheap to add to #10, verifies they actually have the clothes, and hands #11
   its reference photos. The cost is that it turns a fun colour-picker into
   something that asks for a photograph, and those photos then need a retention
   story.
4. **How long do reference photos live?** Suggestion: deleted with the game.
5. **Does the identification scheme survive three bring-your-own channels?** With
   only armbands provided (#9), this is the biggest open risk to the whole
   identification idea on the night. #10 is the mitigation; R1/R2 will tell us
   afterwards how well it worked.
