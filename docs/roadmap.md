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
| **Before setup** | Accuracy and heading capture in, so the schema change rides the game's own `resetdb` and the night's telemetry is recorded.               | R5           |
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
| 1b    | **R6** Check the armband hexes on arrival   | On delivery, before the 19th | The armbands are ordered but not delivered; the palette is only as good as what actually turns up.            |
| 2     | **#6** Find the pubs                        | Now → 7 Sept                 | Needs other people to say yes. Start the conversations first, collect the data second.                         |
| 3     | **#12** Redraw the Westminster map          | ~31 Aug                      | Blocks #7, and retires the temporary resort test venue.                                                        |
| 4     | **#10** Colour-picking page                 | ~31 Aug build, live ~7 Sept  | The only software on the critical path. Also the mitigation for bring-your-own garments (see #9).              |
| 5     | **#7** Find the drop locations              | ~7 Sept                      | Needs #12 to place them; feeds #8.                                                                             |
| 6     | **#8** Print the run                        | ~12 Sept                     | Everything above becomes paper here.                                                                           |
| 6b    | **#5** Score candidates, not codewords       | **Before the 19th**          | Promoted from 13. Auto-actions are required, and they cannot work while identification decodes against the code. |
| 7     | **#4** False hits                           | Before the 19th *if it fits* | The one recognition item worth rushing; if it slips, run with auto-actions off.                                |
| 8     | **R1** Offline replay harness               | With #4                      | What makes #4 tractable in the time available rather than guesswork.                                           |
| 9     | **R5** Capture GPS accuracy and heading      | **Before the 19th**          | Telemetry not recorded on the night is lost forever. The only post-game item with a real deadline.             |
| 10    | **R3** Screen Wake Lock                     | Before the 19th *if it fits* | Thirty lines, and it stops the phone sleeping while it is being held as a weapon.                              |
| 10b   | **R7** Reference photo as a kit check       | Before the 19th *if it fits* | The manual gate needs no software; the vision dry run does. Upside only — the door check happens either way.   |
| —     | *— the game —*                              | **19 Sept**                  |                                                                                                                |
| 11    | **#1** "CharlesBot", not "AI"               | —                            | Twenty minutes, independent of everything. Ship whenever.                                                      |
| 12    | **R2** Adjudication scorecard               | —                            | The full version of R1; the game itself generates the data it needs.                                           |
| 14    | **#3** Ranked candidates in the review UI   | —                            | The surface of #5; same piece of plumbing.                                                                     |
| 15    | **#2** "CharlesBot thinks: hit on *name*"   | —                            | Needs the name, so it needs #5/#3.                                                                             |
| 16    | **#13** Higher-resolution capture           | —                            | Promoted: with #14 parked this is the *only* route to better photos, and #4, #5 and #11 all want them.         |
| 17    | **R4** Service worker and Web Push          | —                            | The notification half of what the native app was for, at no cost. Largest single win available to the web app. |
| 18    | **#11** Escalation to a stronger model      | —                            | Needs #5's posterior and a new photo-capture flow.                                                             |
| —     | **#14** Native app                          | **Parked**                   | Decided against: the Apple fee is unavoidable for iOS in any form. Analysis kept for whenever it is revisited. |

---

## Decisions taken

Recorded here so they are not re-litigated:

- **The game is on 19 September 2026, in Westminster.** House Absolute is in
  Westminster, so #6, #7 and #12 are all the same venue.
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
- **The reference photo is taken by the admin at the door on the night** (R7),
  not by the player at pick time. It is a manual gate on whether people actually
  wore what they said they would, so it has to be done by the person who can
  send them home to change. Answers open question 2.
- **`TEAM_CHANNEL` stays on the hat**, reversing the earlier decision to move it
  to the armbands. Each team bulk-buys hats in its colour; the armbands stay the
  free per-player channel we set on the night. See #9 and plan §12.6 — no code
  change, `TEAM_CHANNEL` is already `"hat"`.
- **Auto-actions must work on the night.** They are the point of the recognition
  work, not a bonus. This promotes **#5** onto the critical path, because the
  code-decode path in `slot_candidates_from_review` cannot see a player who is
  not wearing their exact codeword — which, with overrides or free choice, is
  most of them.
- **Players choose freely, seated as far apart as their wardrobe allows** (#10),
  rather than picking a canonical slot or being held to a hard distance
  threshold. Plan §12.6: everyone gets clothes they own, ~55% keep the full
  `d = 3`, ~45% sit at 2, ~0.2% at 1.
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

**Reversed: `TEAM_CHANNEL` stays on the hat, and each team bulk-buys its hats.**
An earlier draft of this section decided to move it to the armbands, on the
grounds that the armbands are the one garment we control. That reasoning was
right about the premise and wrong about the conclusion, and the numbers in plan
§12.6 say so:

- **It does not buy more outfits.** The code is MDS with `k = 2`, so any two
  garments determine the other two. Pinning *any* channel to the team leaves
  exactly one bucket of five slots (four for black) — identical for hat, t-shirt
  and armbands. The team-channel choice does not change capacity at all.
- **It decides which garments a player has to source.** With the team on the
  armbands, the five slots in a team each need a *different* hat colour, and
  almost nobody owns a coloured hat. With the team on the hat, the hat is a
  single bulk purchase — one person buys five caps — and the player sources only
  a t-shirt and trousers, which are things people own.
- **It is the difference between having a free channel and not having one.**
  Teammates share the team colour, so if that colour is the armbands, then within
  a team we have *no* channel left that we control — nothing to turn at handout
  time to separate two players whose wardrobes collide. Putting the team on the
  hat keeps the armband as a per-player variable we set on the night. That is the
  real value of controlling the armbands: not more slots, but a knob that still
  turns after everyone has chosen.

Measured (§12.6): with the team on the armbands, a player can fully wear ~0.06 of
their team's free slots and 46% wear at most one of their three garments as
recorded. With the team on the hat, that becomes ~0.56 and 10%.

**No code change is needed** — `TEAM_CHANNEL` is already `"hat"`. What changes is
the shopping list: seven armband colours (already ordered, #9) *plus* one hat
colour per team, bought by the team.

**Risk to name out loud:** two of the four channels are bring-your-own in the
free sense (t-shirt, trousers), the hat is bring-your-own but bulk-bought to a
single colour per team, and only the armbands are ours. The scheme's accuracy on
the night still depends on players owning and wearing what they picked. #10 is
the mitigation, and R7 is the check that it worked.

---

### R6 — Check the armband colours against the palette when they arrive *(proposed)*

**Status: ordered, not yet delivered.** The armbands were bought against the hex
values in `PALETTE_HEX["main"]` (`backend/identity/config.py`), but nobody has
seen them yet, so nobody knows how close the dye actually is.

**On delivery:** photograph the seven armbands together under the lighting they
will be used in, compare against the hex values, and **update `PALETTE_HEX` to
what was actually bought** rather than leaving the aspirational values in place.
The palette was chosen by optimising worst-case CIEDE2000 separation across three
illuminants (plan §9.1, §12.4); a silent substitution erodes exactly the property
the scheme rests on, and a recorded one can at least be re-checked.

If two of the delivered colours turn out to be closer than the design assumed,
that is a palette problem to solve before the night, not a decoder problem.

**Lands in:** `backend/identity/config.py` (`PALETTE_HEX`).
**Blocks:** nothing hard, but it should be true before #8 prints anything that
shows a colour swatch.

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

**Settled: the choice is free within the team, and seated by distance.** The
player is not offered a list of canonical slots. They say which t-shirt and
trouser colours they own; the backend seats them on the outfit that is as far as
possible from everyone already placed, with the hat fixed to the team and the
armband chosen by us. §12.5's capacity tax does not apply, because pinning the
hat to the team partitions the space and prevents the stranding that causes it —
inside a team, free choice and the code fit the same five players. See plan
§12.6 for the numbers and open question 5 for the reasoning.

**This depends on #5.** Freely chosen outfits are not codewords, so the
code-decode path in `shot_vision.slot_candidates_from_review` cannot identify
their wearers — and can confidently identify the *wrong* one. Auto-actions are
required on the night, so #5 ships first.

**Do ask each player to confirm they have the garments.** Do **not** ask them to
photograph themselves: that is deliberately deferred to R7, where the admin takes
the photo at the door on the night. A self-taken photo verifies nothing, because
the person submitting it is the person with a reason to fudge it.

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

**Status: fixed on the replay set (2026-08-25) by making the zoom mandatory**
— false-hit rate 0/40 over 5 replay runs, false-miss rate unchanged; details
at the bottom of this section. Awaiting confirmation on real game data.

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

**Tried this session (2026-08-24): suspects 1 and 2, together.** The crosshair
is now a single-pixel-wide red cross spanning the *entire* frame (no gap, no
short arms that can visually touch a target without the true centre landing on
it), and the prompt was rewritten around the single centre point per suspect 1
("only the pixel at the centre of the cross matters", explicitly told to
ignore anything the lines merely pass over). A first colour-coded version
(red/blue lines + a green centre pixel, to make the exact point unmistakable)
was tried and dropped: the single green pixel does not survive
`prepare_for_vision`'s downsize and JPEG re-encode — it lands as a muddy grey,
not identifiably green — so a uniform red cross is what actually ships.

Replayed 5x over all 13 fixtures (65 trials, `google/gemini-3.7-flash-20260813`,
0 errors; results at `tests/fixtures/shot_replay/replay_single_red_cross_run{1..5}.jsonl`).
**No measurable improvement**: false-hit rate 5/40 (12%), false-miss rate 20/25
(80%) — statistically identical to the original baseline. d91548d3, the
flagship false hit, came back `hit_player` at 0.95 confidence in **5/5** runs
(previously investigated as the marker-geometry bug; that bug is now fixed and
made no difference here). Reasoning text each time claims the crosshair lands
"directly on" the face/neck/forehead. Most other shots were equally consistent
run to run (11/13 unanimous across all 5), so this is not sampling noise — the
model has a *systematic* bias to call it a hit whenever the person is merely
close to centre-frame, and rewording/redrawing the marker around a single
point didn't move that bias. Likely reason: in this photo the subject really
is near the geometric centre of the frame (the miss is by inches, in foliage
above his head), which is exactly the kind of close call suspect 3
(asymmetric pressure: "when in doubt, it is a miss") and especially suspect 4
(replacing the hit/miss boolean with an observation like
`on_body`/`touching_outline`/`clearly_beside`/`nobody_near` that Python can
threshold) were aimed at. Suspects 3 and 4 are still untried — try those next,
not more marker-geometry tweaks.

**Also tried this session: suspects 3 and 4, folded into one prompt variant.**
`backend/shot_vision.build_prompt` was refactored to take the hit/miss
decision paragraph as a `decision_rule` parameter (default unchanged), so a
variant can swap it without duplicating the rest of the template. Added
`scripts/replay_shot_reviews.PROMPT_VARIANTS["boundary_scale"]`: instead of a
bare yes/no, it asks the model to place the cross's centre point into one of
four buckets -- *clearly hitting*, *on the boundary but just hitting*, *on the
boundary but just missing*, *miles away* -- and states the asymmetry
explicitly (a wrongly-called miss costs one bullet; a wrongly-called hit takes
a life from somebody never shot), telling the model to prefer "just missing"
when genuinely torn between the two boundary buckets. Same JSON contract, so
this is a pure reasoning-scaffold change.

Replayed 5x over all 13 fixtures (65 trials, 1 transient empty-reply error
retried and resolved; results at
`tests/fixtures/shot_replay/replay_boundary_scale_run{1..5}.jsonl`). **Still no
measurable improvement**, and the numbers are eerily exact: false-hit rate
5/40 (12%), false-miss rate 20/25 (80%) -- eleven of thirteen shots landed the
same outcome, run for run, as the plain single-red-cross variant above.
d91548d3 is `hit_player` at 0.95 confidence in all 5 runs here too, and in all
15 runs across both variants it **never once requests the zoom** — it isn't
torn between the boundary buckets, it just doesn't perceive that the centre
point is off the person at all. That rules out "the model is unsure but the
prompt doesn't reward saying so" as the explanation; asymmetric framing and an
explicit tie-breaker only help when the model registers a tie in the first
place.

At this point three independently-worded prompts (the original arms-with-a-gap
marker, the single-point red cross, and the four-bucket boundary scale) have
all landed on the *same* false-hit and false-miss ids at the *same* rates.
That points away from prompt wording entirely and toward one of: (a) a
resolution/perception limit -- the true aim point in this photo is only a few
percent of the frame width from the person, plausibly below what the vision
encoder can localise reliably at 1024px after JPEG compression, so nothing
written in English fixes it; or (b) making the zoom mandatory rather than
optional, since the model's self-assessed certainty is not tracking its actual
accuracy here (0.95 confidence on a shot it gets wrong every time). Try (b)
before spending more session time on further prompt rewording -- it's a
one-line change (drop the "if it is difficult to tell" gate and always take
the zoom) and directly tests the "it never asks because it never doubts itself"
theory.

**Tried 2026-08-25: (b), the mandatory zoom — and it worked.** `review_image`
grew an `always_zoom` mode (`backend/shot_vision.py`): the full frame and the
zoomed centre go in a *single* call as two user turns (one API call, so the
zoom no longer costs a second round-trip), the prompt tells the model both
views are already in front of it and `request_zoom` must be false, and the
reply is final. Replayed 5x over all 13 fixtures (65 trials,
`google/gemini-3.7-flash-20260813`, 3 transient empty-reply errors retried and
resolved; results at
`tests/fixtures/shot_replay/replay_always_zoom_run{1..5}.jsonl`). **False-hit
rate 0/40 (0%) — down from 5/40 in every previous variant — with the
false-miss rate unchanged at 20/25 (80%).** d91548d3, the flagship false hit
that survived all three prompt rewordings at 0.95 confidence, is now called
`miss` in 5/5 runs at 0.98 confidence, with reasoning that finally sees the
geometry: "the centre of the cross lands on the background foliage and sea to
the left of the person's head". The hypothesis was right: the model never
asked for the zoom because it never doubted itself, and with the zoom always
in front of it the aim point is no longer below its perception limit. The four
remaining false misses are unchanged and are *not* the model's error — they
are `classify()`'s two-readable-channels → `hit_bystander` mapping (the
model's channel observations match the admin notes exactly; whether that
mapping should instead escalate to a stronger reviewer is the separate
question in the 2026-08-24 handover), not a prompt problem.
**Shipped:** the live path (`backend/ai_shot_review.review_shot`) now passes
`always_zoom=True`, and the replay harness's `baseline` variant tracks it; the
old behaviour survives as the `optional_zoom` variant for comparison runs.

**Updated 2026-08-25 (later): the zoom is now gated on a screening question,
not sent unconditionally.** With the zoom factor doubled (`ZOOM_FACTOR = 8`)
the remaining failure mode was close shots that actually miss being called
hits, so `review_image`'s default flow changed again: turn one asks only "does
the person fill less than half of the screen?"
(`person_fills_less_than_half`); that reply is discarded and turn two is either
the zoomed view (small target, with the same question repeated) or a plain
request for the full reading. A still-small target after the first zoom gets
one final, closer view (`MAX_ZOOMS = 2`, compounding as `ZOOM_FACTOR**level`).
The `request_zoom` field is gone — the model never chooses the zoom, it only
ever answers how big the person is. `always_zoom=True` survives for replay
comparisons; the harness's `baseline` variant tracks the screening flow and
`optional_zoom` is retired.

**Replay-scored 2026-08-25:** one run of `baseline` over all 13 fixtures
(`tests/fixtures/shot_replay/replay_screening_gate_run1.jsonl`) — **false-hit
rate 0/8 (0%), false-miss rate 4/5 (80%)**, matching the always-zoom numbers
this variant replaces. d91548d3, the flagship false hit, is `miss` at 0.99
confidence. The four false misses are the same `hit_bystander` mapping noted
above (armbands hidden, other channels incomplete), not a regression from the
screening gate. Single run, not the 5x done for the earlier variants — worth
repeating before fully trusting the rate, but it confirms the screening gate
did not reintroduce the false-hit problem it was built to avoid.

**Admin visibility (2026-08-25):** two zooms sharing one `zoom_used` bool made
it impossible to tell from the queue or the replay workbench whether a shot
spent one zoom or two, and the workbench showed only the parsed final reading
-- nothing of what was actually said turn by turn. `ShotVisionResult` grew
`zoom_count` (0/1/2, `to_dict()` always) and `transcript` (every turn sent
plus the raw reply, `to_dict(include_transcript=True)` -- opt-in so a live
review's stored payload does not carry it on every shot). The queue and
workbench tags now read "Zoomed in ×N" (`ShotQueue.zoomTag`, falling back to
a bare "Zoomed in" for reviews stored before this); the workbench also gets a
collapsible "Full model transcript" per replayed shot, with a "Prettified
JSON" toggle that dumps the whole exchange instead of the per-turn cards.

**Refined 2026-08-25 (later):** two follow-up fixes once this was actually
used. First, the vision-images panel showed the full frame and one zoom crop
unconditionally, regardless of whether a zoom was actually spent -- now it
shows only the full frame until a replay runs, then exactly as many zoom
crops as `zoom_count` says were used (`admin_get_shot_vision_images` grew a
`zoomed2` alongside `zoomed`). Second, `transcript` was a list of *cumulative*
snapshots -- each exchange repeating every earlier turn verbatim before
adding its own -- which read as duplication once printed as JSON. The
conversation is append-only (nothing sent earlier is ever revised), so
`transcript` is now that flat chronological list directly: one entry per
turn, user prompts as text and assistant replies as the parsed JSON, with
nothing repeated. (Also checked: each turn already sends its text before its
image in the message content, which is what you want for prompt caching.)

**Reasoning trace surfaced (2026-08-26):** the transcript carried each
assistant turn's *parsed reply* only -- for a "thinking" model, OpenRouter
also returns the model's extended reasoning trace on `message.reasoning`
(included by default, no opt-in needed), and that was silently dropped.
`VisionClient` gained a `last_reasoning` property (`OpenRouterVisionClient`
reads it off the response; `FakeVisionClient` takes a `reasoning=` arg for
tests), and `shot_vision._assistant_turn` attaches it to each transcript
entry the workbench renders. The workbench shows it under a per-turn
"Model reasoning" disclosure, distinct from the short `reasoning` field the
model fills in as part of its JSON reply itself.

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

**Status: harness built** as `scripts/replay_shot_reviews.py` — `audit` scores
the reviews already stored in a database against the admin verdicts (free, no
API calls), `replay` re-runs the real vision pipeline over the saved photos
with a chosen model and prompt variant into a resumable JSONL, `score` turns a
replay file into the same report, and `extract` dumps shots' photos to PNG for
eyeballing the false hits. `export` writes shots to a fixture directory
(photos + `manifest.json`, including each shot's `admin_notes`) which the
other subcommands read back via `--fixtures`; the live set lives at
`tests/fixtures/shot_replay/` (thirteen resort test shots: the six of
2026-08-21 plus seven of 2026-08-24), all with real admin verdicts and
per-shot notes explaining what the vision agent should have returned. Prompt
variants for #4 land in its `PROMPT_VARIANTS` registry.

**In-browser counterpart (2026-08-25):** the admin "Shot replay" workbench
(`/admin/replay`, `react-ui/src/ShotReplay.js`) fires any selection of the
shots actually in the database through the same pipeline with the prompt
editable on the fly (`admin_replay_shot_review`, plus
`admin_get_default_vision_prompt` to seed the textarea). It stores nothing and
flags where the reading disagrees with the admin's verdict — the quick
half of the harness, for trialling a prompt edit before measuring it properly
with `replay`.

**What the first run found.** The live database held no admin verdicts at all
(the queue was never adjudicated), so the fixture labels are by eye. Even so:
a close-up the admin calls a **miss** (crosshair just top-left of the head)
was reviewed as `hit_player` at 0.95 confidence — a confident false hit that
would have auto-fired, i.e. #4 in the wild — and all four distant (~50 m)
shots came back `hit_bystander` on exactly two readable channels (t-shirt +
trousers; the armbands and hat are unresolvable at that range even through
the zoom), so auto-actions would have auto-bystandered four real hits. To
produce proper verdicts, the admin queue grew a **"Show adjudicated shots"**
toggle and a per-shot **admin notes** field (`Shot.admin_notes`,
`admin_get_shot_notes` / `admin_set_shot_notes`) so future exports carry real
adjudications and the reasoning behind them.

**Model-family sweep (2026-08-25).** `scripts/replay_shot_reviews.py` grew
`replay_to_file`, the reusable core of `cmd_replay`, and
`scripts/benchmark_vision_family.py` drives it over a list of models --
every size OpenRouter currently lists under Qwen3-VL (235B-A22B, 32B,
30B-A3B, 8B, instruct and thinking variants) plus the pipeline's own default
`google/gemini-3.7-flash-20260813` -- writing one resumable JSONL per model
under `--out-dir` and printing a side-by-side accuracy table plus a tool-use
tally (JSON-schema/parse failures, empty replies, rejected requests). A full
run against all 13 fixture shots is committed at
`tests/fixtures/shot_replay/family_benchmark/`; see
`docs/vision_model_family_benchmark_2026-08-25.md` for the results. Headline:
`gemini-3.7-flash` (the current default) remains the best-calibrated model
(0 false hits at 0.92 mean confidence); `qwen3-vl-235b-a22b-instruct` failed
outright (whitespace, no JSON) on 4/13 shots; `qwen3-vl-8b-thinking`
hallucinated confident hits on two shots every other model in the family,
including its own non-thinking sibling, correctly called empty/ambiguous.
The `d91548d3` marker-geometry false hit and the four-shot false-miss
cluster from the 2026-08-24 handover both reproduced across most of the
family, reinforcing that the aim-marker geometry and `classify()`'s
two-channel rule (not model choice) are the higher-leverage fixes.

**R2, after the game — the scorecard.** The admin-facing version: an endpoint and
a page reporting CharlesBot's outcome against the admin's over a game or all
games, broken down by whether the zoom was used and by how many channels were
readable, plus the same numbers restricted to reviews above the auto-action
confidence threshold — which is the number that decides whether
`ai_auto_actions_enabled` is safe to switch on. The 19th will generate more real
data than everything to date, so build this to consume it.

---

### #5 — Two readable channels should still identify somebody *(shipped)*

**Shipped** as `backend/shot_identification.py`, with the auto-action hit path
in `backend/shot_auto_actions.py` rewired onto it. What is *not* yet done is #3,
the admin-facing surface: the ranking is computed and acted on, but the queue UI
still shows only the old tags, so an admin cannot see the runners-up.


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
game, turns `location_context` into the weighting described below, calls
`decode()`, and stores the ranked result alongside the existing review payload.

#### Getting the probability model right

An earlier draft of this section said "build a `Prior` weighted by proximity to
the shooter". That is wrong, and wrong in a way that would have produced
confidently incorrect answers. Proximity is **evidence**, not a prior, and the
two must not be conflated.

The quantity wanted is `P(T = x | image, location)` — the probability that player
`x` is the person who was shot, given everything observed. Factorised, with the
photograph and the position fixes treated as independent measurement channels:

    P(T = x | image, location)  ∝  P(T = x) · P(image | T = x) · P(location | T = x)

**1. `P(T = x)` — the structural prior. Flat, then adjusted for game rules.**
Before looking at any evidence, what is known about who can have been shot? Only
the rules: the target is not the shooter, is not already knocked out, and is
unlikely — but *not* unable — to be a teammate. Note `hit_user` performs no team
check, so friendly fire is mechanically possible; the teammate term should
therefore be small and non-zero rather than an exclusion, for the same reason as
the floor below. Beyond that the prior is flat. Proximity does **not** belong
here.

**2. `P(image | T = x)` — the vision likelihood.** What `decoder.decode` already
computes from the reading and `x`'s codeword. Its misread and erasure rates
should start from `identity_demo.simulate()`, and be replaced by measured rates
once R2 has real adjudications to fit against.

**3. `P(location | T = x)` — the location likelihood, which must be a ratio.**
The generative story is: *if* `x` was the target, then `x` was inside the
shooter's engagement envelope at the moment the photo was taken. So the question
is not "how close is `x`" but "how much more likely is `x`'s observed fix under
that hypothesis than under the alternative that `x` is simply somewhere in the
game area":

    Λ_x  =  P(fix_x | x was at the shooter at time t)  /  P(fix_x | x is anywhere)

#### Why the distinction is not pedantry

**The teammate case, which the naive version gets exactly backwards.** Under
"prior ∝ proximity", a teammate standing at the shooter's shoulder receives the
*highest* prior of anyone — when they should receive nearly the lowest. People
stand near their teammates precisely *because* they are teammates. The correct
factorisation kills this in the structural term, and no amount of proximity
resurrects it.

**Double counting.** Players cluster, and teammates move as a group. Using
proximity as both the prior and the evidence counts one fact twice and yields
overconfident posteriors — which is the failure mode that matters, because
`confident_threshold` gates auto-actions.

**Crowds.** The ratio form says something a raw proximity weight cannot: a player
who is near the shooter *when everybody is near the shooter* is barely
discriminated, while a uniquely close player is strongly discriminated. In a
scrum the location evidence should go quiet, and under this form it does.

**Calibration.** With every term a likelihood, the output is a genuine
probability, so `confident_threshold` means what it says and R2 can check it. An
ad-hoc proximity weight produces a score, not a probability, and thresholding a
score is guesswork dressed up as inference.

#### Staleness falls out of it

A position is a measurement with an age. Treat the last fix as a distribution
over where the player is *now*, widening with age:

    sigma_eff(a)^2  =  sigma_fix^2  +  2 · D · a

where `a` is the age of the fix, `sigma_fix` its reported accuracy, and `D` a
diffusion constant from a plausible movement speed.

Feed that into `Λ_x` and the desired behaviour appears without being bolted on:
as the fix ages, numerator and denominator converge, `Λ_x → 1`, and the location
term drops out of the product entirely — leaving the structural prior and the
image evidence to decide. **Staleness widens the uncertainty; it never removes
the candidate.** That the limiting case is correct without special-casing is the
main evidence that the factorisation is the right one.

**Why a candidate must never reach zero.** The posterior is a product, so a zero
in any term is unrecoverable — no quality of colour match climbs back from it. A
stale player dropped from the candidate set means a photograph that reads their
outfit *perfectly* still names somebody else, and does so confidently. Mix in a
uniform floor, `p = (1 - eps) · p + eps · uniform`, as cheap insurance.

#### Implementation: the pure module does not change

`decode(reading, candidates, prior)` computes the image likelihood internally and
accepts a prior. Since `P(location | T = x)` is constant with respect to the
image reading, it can be folded into what is passed:

    prior_passed[x]  ∝  P(T = x) · Λ_x

which is exact, and needs no change to `backend/identity/`. What is being handed
over is "everything except the image evidence" — a pre-image posterior rather
than a spatial weight. Say so at the call site; do not rename the tested module
to suit the caller.

#### Two fields worth capturing now

`position.coords.accuracy` (which is `sigma_fix`) and the shooter's compass
heading (which turns the envelope from a disc into a cone) are both discarded
today and both unrecoverable after the fact. Written up as **R5**, which has to
happen before the 19th for that reason.

**Two things already in place.** `User.location_timestamp` is returned by
`get_locations`, so the age of every fix is already inside every shot's
`location_context` — no schema change, and the ages in historical shots can be
computed today. And `MapView.js` already fades other players' dots with age
(`TIME_UNTIL_TRANSPARENT = 5 * 60`), flooring at `MIN_ALPHA = 0.5` rather than
fading to nothing: the same instinct, already applied visually, and a reasonable
first guess at the timescale for `D`.

**Do not over-model it.** Staleness correlates with a pocketed phone, which
correlates with not being in an engagement — but a player who has just been
photographed was probably out in the open. Resist adding behavioural terms until
R2 has produced data to fit them against.

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

*(Aside, now resolved: `@maplibre/maplibre-react-native` sat in `package.json`
imported nowhere — an abandoned experiment. Removed in #127.)*

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

### R5 — Capture GPS accuracy and compass heading *(proposed — and this one has a deadline)*

Two fields the app already has in its hand and throws away. Both are inputs to
#5's probability model, and neither can be recovered after the fact.

**Why this is the one post-game item that is not post-game.** Everything else in
tracks A and C can be built in October against the data the 19th produces.
This cannot: telemetry that was not recorded on the night does not exist, and the
19th will be by far the largest body of real shots this game has ever generated —
the data that R2 scores, that #4's prompt work is validated against, and that
#5's diffusion constant is fitted to. Miss it and the next chance is the game
after next.

**The schema objection dissolves if it lands early.** Both fields need columns
and therefore a `resetdb`, which is normally a reason to defer — but the database
is being reset for the new game anyway. Done before game setup, the migration
costs nothing.

**The two halves have very different costs.** Take them separately.

#### R5a — GPS accuracy *(cheap; do this)*

`position.coords.accuracy` is already sitting in the `watchPosition` callback in
`MapView.js` and is discarded by `sendLocationUpdate(lat, long)`. It is
`sigma_fix` in #5's model — without it, every fix is assumed equally good, and in
Westminster it will not be: an urban-canyon fix can be tens of metres out where
an open-sky one is single figures.

The path is short and entirely mechanical: send it, add a `location_accuracy`
column to `User`, store it in `set_location`, and — the step easily missed —
return it from `get_locations`, since that is what serialises into every shot's
`location_context` and therefore what #5 will actually read.

#### R5b — Compass heading at the moment of the shot *(fiddly; do if it fits)*

This is what turns #5's engagement envelope from a disc into a cone, and it is
the "shooter orientation / aim" item plan §9 already lists as future work. It is
a property of the shot rather than of the player, so it belongs in a `heading`
column on `Shot`, captured in `MyWebcam.js` at the moment of capture.

**It is harder than it sounds, for three reasons worth knowing in advance.**

- **Not `position.coords.heading`.** That is direction of *travel*, and it is
  null when standing still — which is precisely when somebody is aiming.
- **iOS needs an explicit permission.** `DeviceOrientationEvent.requestPermission()`
  must be called from a user gesture, and the heading arrives as
  `webkitCompassHeading`.
- **Android needs the absolute event.** Plain `deviceorientation`'s `alpha` is
  measured from an arbitrary origin; `deviceorientationabsolute` is the one that
  means anything.

**Where the permission goes.** `OnboardingView.js` already walks players up a
gated ladder — camera, then location — using the request/check helper pair in
`utils.js`. A third rung follows that existing pattern rather than inventing a
new one.

**It must degrade silently.** A denied, unsupported or simply absent heading has
to store null and let the shot proceed exactly as now. Telemetry gathering must
never be able to stop somebody firing on the night; #5's envelope just stays
isotropic for those shots, which is where it is today anyway.

**Nothing should consume either field before the game.** That is the whole point:
capture now, use in October. Building the cone into #5 in the fortnight before
the 19th would be exactly the wrong risk to take.

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

### R7 — The reference photo as a kit check, run through the shot AI *(proposed)*

**Why the admin takes it, not the player.** The reference photo's first job is
not to feed #11 — it is a **manual gate**. Three of the four channels are
bring-your-own (#9), so the single largest risk to the night is somebody turning
up in the wrong colours, or in something they called "green" that photographs
khaki. Checking that is a job for the person standing at the door with the box of
armbands, because they are the only one who can do anything about it: swap a
garment, hand out a different armband, or record an override there and then. A
photo the player takes of themselves at pick time verifies nothing, since the
person submitting it is the person with a reason to fudge it. Hence: **at the
door, on the night, by the admin, one person at a time.**

**Why it should go through the vision pipeline.** Taking the photo is the check
by eye. Running it through **the same prompt and the same machinery the real
shots use** — `backend/shot_vision.py`, `backend/vision_client.py`, the identical
prompt, no special-casing — is the check that matters, because it answers the
only question that counts: *does this outfit actually decode to this person?*
Doing it at the door means a failure is discovered while it is still fixable,
rather than at 22:00 when the photo is of somebody running away.

**It must not count as a shot.** No `Shot` row that can be adjudicated, no HP
change, no ammo, no ticker entry, no place in the admin queue. Same code path,
different sink.

**What it gives us, in order of value:**

1. a go/no-go per player at the door — recognised correctly, or fix it now;
2. a real, per-player measurement of the recognition rate *before* the game
   starts, which is the honest input to the go/no-go on `ai_auto_actions_enabled`
   for the night (that decision currently rests on nothing);
3. clean labelled data — image plus known ground-truth identity — which is
   exactly what R1/R2 want and what §12's numbers were missing;
4. the reference images #11 needs, obtained without asking players for anything.

**Shape (not yet designed).** Probably an admin-mode capture that stores the
image against the user and calls the existing review path with the result written
somewhere that is not the shot queue. The interesting question is what to show
the admin: the decoded identity plus per-channel confidences, so a marginal
channel ("the trousers read as black at 0.4") is visible as a warning, not just a
pass/fail.

**Note the ordering trap:** this wants the identity to already be recorded, so it
runs *after* #10's picks are in and the armbands are handed out — it is the last
step at the door, not the first.

**Lands in:** a new admin capture view, `backend/shot_vision.py` (reused as-is),
and wherever the result is stored. **Feeds:** #11, R1/R2, and the auto-actions
go/no-go. **Depends on:** #10.

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

1. **Should the player-facing shot history name the target?** #2 gives the admin
   a name. Telling a shooter "CharlesBot thinks you hit Alice" before an admin has
   confirmed it leaks a player's position and identity to the other team, and it
   is wrong often enough to be a poor promise. Suggestion: name the target in the
   admin queue, and keep the player's view to hit / miss / bystander.
2. ~~**Do we ask players for a photo of themselves in their outfit at pick
   time?**~~ **Answered: no.** The photo moves to the door on the night, taken by
   the admin — see R7. Keeps the colour-picker a colour-picker, and makes the
   photo a check rather than a self-report.
3. **How long do reference photos live?** Suggestion: deleted with the game.
4. **Does the identification scheme survive three bring-your-own channels?** With
   only armbands provided (#9), this is the biggest open risk to the whole
   identification idea on the night. #10 is the mitigation; R1/R2 will tell us
   afterwards how well it worked.
5. ~~**Is free choice of outfit worth the capacity it costs?**~~ **Answered:
   yes, and it costs nothing here.** §12.5 measured free choice across the *whole*
   space, where unlucky picks strand regions. Pinning the hat to the team
   partitions the space into seven independent buckets of five and prevents that
   stranding: inside a team, free choice and the code have identical capacity,
   because `d >= 3` under a shared hat already forces distinct t-shirts, trousers
   and armbands, and the trousers palette caps a team at five either way. What
   free choice adds is that the five outfits can be chosen to fit the team's
   actual wardrobes — 82.8% of players in clothes they own against the code's
   57.4%. See plan §12.6.
