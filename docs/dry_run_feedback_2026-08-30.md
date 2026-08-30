# Dry-run feedback — 30 August 2026

Written up from Charles's own notes and guest comments during and after the
30 August dry run (~10 real players, on their own phones — see "The dry run:
Sunday 30 August" in `docs/roadmap.md`). Twelve issues, each investigated
against the actual code rather than guessed at; tracked to done as
**R13** in `docs/roadmap.md`. One reported issue (a misspelling of
"parliament" somewhere in the backend) was withdrawn by Charles as a false
alarm — searched exhaustively, not found anywhere in the checked-out code.

Ordered as reported, not by severity — see each item's own note on how
serious it is.

---

## 1. Join links, not just QR codes

**Report.** Joining with a QR code on a single phone is annoying — you can't
both display the code and scan it on the same device.

**Diagnosis.** `react-ui/src/JoinQRCodes.js` (the admin's per-team join-code
generator) only exposes each team's join URL as the `href` of the `<a>`
wrapping the QR image (`team.encoded_url`, lines 39–47). There is no visible,
copyable plain-text link on the page — an admin who wants to paste the link
into a WhatsApp text message has no easy way to get at it; forwarding the QR
as an image is useless if the recipient is reading it on the same phone
they'd scan with.

**Fix direction.** Render the plain URL as visible, copyable text next to
each team's QR code (e.g. a `readonly` text input or a `<code>` block),
so it can be copied and pasted directly into a chat message.

**Severity.** Low — logistics annoyance, not a blocker.

---

## 2. Multi-select on the colour-picking page isn't obvious

**Report.** People need it made clear they can pick more than one piece of
clothing per colour channel, and in fact should pick as many as possible.

**Diagnosis.** `react-ui/src/PickOutfit.js`'s wardrobe step already carries
the line "Tick everything you own - the more you tick, the more choices you
get" (`wardrobeIntro`, line ~533), but it's a single sentence at reduced
opacity, easy to skim past. Worse: the swatch buttons themselves
(`PickOutfit.module.css` `.swatchButton` / `.swatchSelected`) look like a
single-choice colour picker — a highlighted border on selection, no
checkbox/tick glyph — so the UI's own affordance contradicts the copy's
intent. See also item 12, which reports guests acting on exactly this
confusion.

**Fix direction.** Stronger, harder-to-miss copy, plus a checkbox-style
visual cue on selected swatches so multi-select reads correctly at a glance
rather than relying on prose alone.

**Severity.** Medium — degrades identification accuracy (a player who ticks
only one colour per channel gets a much smaller, likely worse-ranked, set of
outfit options) without producing an outright failure.

---

## 3. Name entry silently doesn't save

**Report.** People keep struggling with submitting their name — they think
it's been submitted when it hasn't.

**Diagnosis.** `NameEntry` (`react-ui/src/OnboardingView.js`, lines 47–87)
only submits on pressing Enter or tapping a small circular return-arrow
button next to the input — nothing saves on blur or automatically. Mobile
keyboards don't reliably surface a clear "Enter"/"Go" affordance, so a guest
who types their name and then just taps away (to dismiss the keyboard, scroll,
whatever) has saved nothing. The only feedback is the input's border/text
turning green (`.done .nameInput`, `OnboardingView.module.css:52`) — subtle,
and invisible unless they look back at the field; an unsubmitted name still
just looks like "a name I typed in a box."

**Fix direction.** Submit on blur as well as on Enter/button-tap, so leaving
the field is enough by itself. Make the saved state much more obviously
visible than a colour change alone.

**Severity.** High — this is a silent failure with no error shown, blocking
onboarding (a name is required before an outfit can be claimed).

---

## 4. Replace "please screenshot this page" with a real save/share button

**Report.** Add a button that takes a screenshot for the player, instead of
relying on them to do it manually.

**Diagnosis.** `ResultScreen` in `react-ui/src/PickOutfit.js` (the "You're
set... Locked in - please screenshot this page!" confirmation) is plain
HTML/CSS, not an existing canvas — unlike `MyWebcam.js`, which already
captures from a real video element. Turning it into a shareable image needs
a DOM-rasterization step.

**Fix direction.** Add `html2canvas` (not currently a dependency — flagging
since it's a new addition to `react-ui/package.json`) to rasterize the result
card, then hand the image to the Web Share API (`navigator.share` with an
image file) so the native share sheet opens — better fit for a phone than a
plain download link, since it lets the guest save to Photos or forward the
image directly. Fall back to a download link for browsers that can't share
files.

**Severity.** Low — convenience improvement, not a failure.

---

## 5. Safari: some users can't tap the location-permission button

**Report.** Some users on Safari can't click the location permission button.
Hard to reproduce. Flagged as the most serious of the batch, since it blocks
onboarding outright for whoever hits it.

**Diagnosis.** `OnboardingView.js` (lines 117–201): the location-permission
row is a real `<button>`, and `requestGeolocationPermission`
(`utils.js:121–132`) calls `navigator.geolocation.getCurrentPosition`
synchronously within the click handler — no `await` beforehand — so this
isn't the classic iOS "lost user-gesture" trap.

Leading suspect instead: every row in the action-item list
(`ActionItem` → `motion.div layout`, wrapped in `AnimatePresence`) animates
into a new position via framer-motion's layout (FLIP) system every time the
list grows by one row — which happens right as the location row appears.
Safari's touch hit-testing is known to be less reliable than Chrome's
mid-CSS-transform, so a tap landing while a row is still animating into
place can miss. This would explain "hard to reproduce" — it's timing-
dependent on exactly when someone taps relative to the reflow, not a
deterministic permission/API bug.

**What would help pin it down**, if available from an affected guest: does
the button show any press/highlight state on tap (dead-to-touch vs.
registers-but-nothing-happens)? Were they in Safari proper or a
home-screen-installed PWA?

**Fix direction (defensible even without full repro).** Drop the `layout`
animation specifically from the two gating rows (webcam, location) — the
smooth-reflow effect is purely cosmetic there, and not worth the risk on the
one button that's load-bearing for the whole join flow.

**Severity.** High — blocks onboarding outright for affected users, with no
workaround visible to them.

---

## 6. No route from the colour-picking page into the actual game

**Report.** When the game starts, people need to be bumped straight from the
colour-picking page to the game page — otherwise there's no way for them to
actually play.

**Diagnosis.** `/pick` (`PickOutfit.js`) and `/` (`UserMode.js`) are
completely separate routes (`react-ui/src/index.js:24–30`) with nothing
connecting them. `UserMode.js` already does the right thing on its own: it
shows `OnboardingView`'s "Wait for game to start..." row while
`!user.active`, and flips live to the real game view the instant the game
goes active, via its existing SSE connection (`UpdateSSEConnection` +
`UpdateListener update_type="user"`, `UserMode.js:143–152`). But nobody who
finishes on `/pick` is ever sent to `/` — `PickOutfit.js`'s `ResultScreen`
just stops after "You're set." A guest who picks their outfit ahead of time
and leaves that tab open has no way into the game when it kicks off.

**Fix direction.** `PickOutfit.js` deliberately avoids SSE and polling by
design (its own file comment: "no map, no webcam, no SSE, no permission
polling"), so a lightweight poll (check every ~10–15s, the same idiom
`UserMode.js` already uses for its own permission recheck) that hard-
redirects to `/` once the game goes active is the minimal fix, rather than
pulling in the whole SSE stack this page was deliberately kept out of. Once
redirected, `/` already handles everything else correctly with no further
work needed there.

**Severity.** High — "there's no way for them to actually play" is as
serious as it sounds.

---

## 7. Weapon loot items should be picked from an enum, not typed by hand

**Report.** Weapon allocation needs to be selected from a dropdown rather
than typed in manually.

**Diagnosis.** This is about the loot-item creation page, not the per-player
admin controls (which already do this correctly): `react-ui/src/AdminMode.js`
already has a `WEAPONS` enum (`{"Pewster": [1,6], "Tracka-Tracka": [2,6],
...}`, lines 15–21) driving a `<select>` for direct per-player weapon
assignment (lines 99–114). But `react-ui/src/NewItems.js` — where the admin
generates a QR-code loot pickup for a weapon — never reuses it:
`ITEM_PARAMS.weapon = ["shot_damage", "shot_timeout"]` (line 11) renders two
raw `<input type="number">` fields, so making a weapon loot drop means
manually typing the damage/timeout pair and remembering which combination
corresponds to which named gun.

**Fix direction.** Share the `WEAPONS` enum between the two files rather
than each hand-rolling its own, and render a `<select>` of weapon names for
the `weapon` item type in `NewItems.js`, translating the pick into
`shot_damage`/`shot_timeout` before posting — the exact pattern
`AdminMode.js` already demonstrates.

**Severity.** Low — admin-only inconvenience, easy to fat-finger but not
player-facing.

---

## 8. Shots should say which weapon fired them

**Report.** The shot record/review should show which weapon was used to take
the shot.

**Diagnosis.** `Shot.shot_damage` is already captured at the moment of firing
(`backend/user_interface.py:559`; `backend/model.py:166` — "Required since
users could pick up upgrades after taking this shot"), but there is no
`Shot.shot_timeout` column, and `submit_shot` never records it. That matters
because the existing weapon-name lookup (`AdminMode.js`'s `WEAPONS` enum)
keys on **both** `(shot_damage, shot_timeout)` — e.g. "Pewster" is `[1, 6]`
and "Eat-a-bullet" is `[1, 1]`, both damage 1. Damage alone can't
disambiguate those two, so naming the weapon on a shot correctly needs the
timeout too, which isn't stored anywhere per-shot today.

**This needs a schema change.** Per this repo's current state (a live game
running, no migrations), adding `Shot.shot_timeout` means a hand-written
`ALTER TABLE` against the live droplet's database — **raise this with
Charles before writing the model change, not after**, per `CLAUDE.md`.

**Fix direction.**
- **Proper fix**: add `Shot.shot_timeout`, ALTER the live DB, then render the
  weapon name in `ShotQueue.js` / `ShotHistory.js` via the same `WEAPONS`
  lookup as item 7 — reusing it rather than re-deriving.
- **Cheap stopgap** (no schema change): derive the weapon name from
  `shot_damage` alone, accepting that damage-1 weapons (Pewster vs.
  Eat-a-bullet) can't be told apart and would show as "Pewster or
  Eat-a-bullet."

**Severity.** Low — nice-to-have for review, blocked on a decision rather
than effort.

---

## 9. Escalation transcript in the shot replay workbench

**Report.** Add a transcript option for the escalated model to the shot
replay admin view, so the reasoning behind an escalated shot can be seen the
same way the primary model's can.

**Diagnosis.** `react-ui/src/ShotReplay.js` already has a `TranscriptView`
component (lines 81–105) rendering a collapsible turn-by-turn transcript,
fed by `ai_shot_review.replay_shot_review(..., include_transcript=True)` —
but that only ever runs the *primary* review pipeline.
`admin_replay_shot_review` (`backend/main.py:763–794`) has no escalation path
at all; escalating a shot only happens via the stateful `admin_escalate_shot`
(`shot_escalation.enqueue_escalation` → `AdminInterface().
store_shot_escalation`), not a no-store "try it and show me" replay like the
workbench does for the primary model.

The escalation transcript itself is already built the same way, though:
`shot_escalation._run_escalation` (`backend/shot_escalation.py:562–646`)
assembles a full `transcript` list via the same `_transcript_turn` /
`_assistant_turn` helpers the primary pipeline uses (line 645) — it's just
discarded into a stored payload rather than handed back raw.

**Fix direction.** Add a no-store "replay escalation" path mirroring how
`replay_shot_review` relates to the real stored review — call into a
refactored, non-persisting version of `_run_escalation` and return its
transcript, then reuse `ShotReplay.js`'s existing `TranscriptView` for a
second "escalation transcript" section. One precondition carries over from
`admin_escalate_shot`: escalation needs a completed primary review to build
its candidate ranking from, so the workbench would use the shot's
already-stored review, same as the real escalate-shot button requires.

**Severity.** Low — a tooling/workflow improvement for Charles, not
player-facing.

---

## 10. Map zoom is unreliable (likely root cause found)

**Report.** Zooming on the map is reliably terrible.

**Diagnosis — this looks like an actual bug, not a library-tuning issue.**
`VenueMapView`'s `clickCatcher` div (`react-ui/src/MapView.js:467–479`) sits
*inside* the `TransformComponent` (i.e. it zooms and pans along with the
map), and its `onClick` handler is only disabled when `alwaysExpanded` — it
is **not** conditioned on `poppedOut`. So even once the map is already popped
out and in interactive zoom/pan mode, any tap on it still fires
`setPoppedOut(!poppedOut)` **and** `resetTransform()` **and**
`handleResize()` — collapsing the map back to its small corner view and
snapping the zoom back to 1× on the same tap.

That lines up exactly with "reliably terrible": pinch-zoom gestures on touch
devices very commonly end with a synthesized click/tap event when the
fingers lift, so the moment someone finishes zooming in, this handler fires,
undoes the zoom, and shrinks the map back down.

**Fix direction.** Only wire the pop-out-toggle-and-reset behaviour for the
*unexpanded* corner state (tap the small corner map to open it). Once
`poppedOut` is true, taps on the map should just be normal interaction
(pan/zoom/select); closing the map should go through an explicit close
action instead of any tap on the map surface.

**Severity.** High confidence, medium player impact — annoying rather than
blocking, but a very concrete, well-evidenced fix once found.

---

## 11. Shot browser needs to jump, not just step one at a time

**Report.** Add a dropdown or a jump-forward-by-10 control to the shot
browser — stepping through shots one at a time is tedious.

**Diagnosis.** `react-ui/src/ShotQueue.js` (the admin's shot queue/history
browser, lines 855–898): "Shot {currentShotIdx + 1} of
{shotsInQueue.length}" with only `nextShot` / `previousShot` buttons that
move `currentShotIdx` by exactly one. No jump control, no dropdown — for a
long queue or contested-shot history that's a lot of clicking to reach, say,
shot #40.

**Fix direction.** Reusing the existing `currentShotIdx` /
`setCurrentShotIdx` state: add a "+10"/"-10" button pair (clamped to
`[0, shotsInQueue.length - 1]`, the same way `nextShot`/`previousShot`
already clamp), plus a `<select>` listing every shot index so the admin can
jump straight to one.

**Severity.** Low — admin convenience.

---

## 12. The colour-picking flow is confusing, and some guests never actually joined

**Report (Charles, summarising general guest confusion):** people weren't
sure whether to select what they *want* to wear or what they're *actually*
wearing, and picked aspirationally rather than reporting their real
wardrobe. People weren't aware they could select multiple things (see item
2). And people didn't realise there was a separate "click, then confirm"
step — a lot of people ticked a couple of colours, got offered one outfit
option, tapped it, and believed that was the end of it. **They never actually
joined the game.**

**Diagnosis.** Walking `PickOutfit.js`'s actual flow:

1. **Tick your wardrobe colours** (`WardrobeChannel`) — item 2's multi-select
   confusion applies here directly. New point: the copy never states "what
   you currently own" vs. "what you'd like" in so many words — if someone's
   skimming, ticking favourite colours rather than actual wardrobe is an easy
   misread, and it quietly makes identification worse: CharlesBot scores the
   shot photo against what a player *said* they own, so a wishful tick
   actively works against them.
2. **Tap an outfit option** (`OptionRow`, `onClick={() => onPick(option)}`)
   — this is **purely local React state** (`setSelectedOption`). No API call
   at all. It just opens the confirm screen.
3. **Confirm screen** — a checkbox ("I will wear this on the night") plus a
   separate "Lock in my choice" button. **Only this** calls `pick_outfit`
   and actually claims the slot (`claimOption`).

So someone who ticks a couple of colours, sees one option offered, taps it,
and closes the tab has done **nothing** as far as the backend is concerned —
no slot claimed, not in the game. Same shape of silent failure as item 3
(name entry), but worse in consequence: not a stray missing field, the
entire join fails with no error and no visible sign anything is missing,
since a picked-but-unconfirmed option looks visually complete.

**Fix direction, building on items 2 and 3.**
- Make the wardrobe-tick copy state the "what you're actually wearing, not
  what you fancy" distinction unambiguously.
- Collapse or visually merge the tap-option and confirm-and-lock-in steps so
  picking an outfit reads as one continuous action rather than two, with the
  second half impossible to miss — matching item 3's fix (no silent stopping
  points).

**Severity.** High — this is the one directly costing real player signups.

---

## Summary table

| # | One-line | Severity | Needs a decision first? |
| - | -------- | -------- | ------------------------ |
| 1 | Join links as visible text, not just QR | Low | No |
| 2 | Multi-select ticking unclear | Medium | No |
| 3 | Name entry silently fails to save | High | No |
| 4 | "Screenshot" → save/share button | Low | No |
| 5 | Safari location button sometimes dead | High | Would benefit from more repro info |
| 6 | No route from `/pick` to the game | High | No |
| 7 | Weapon loot: dropdown, not free text | Low | No |
| 8 | Shots should name their weapon | Low | Yes — live-DB schema change |
| 9 | Escalation transcript in replay workbench | Low | No |
| 10 | Map zoom breaks itself on tap | Medium (high confidence) | No |
| 11 | Shot browser needs a jump control | Low | No |
| 12 | Outfit flow: some guests never actually joined | High | No |

Tracked to completion as **R13** in `docs/roadmap.md`.
