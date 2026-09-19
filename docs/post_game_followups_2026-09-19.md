# Post-game follow-ups — 19 September 2026

Charles's own notes from running the game on 19 September, recorded as they
came in and investigated against the code rather than guessed at. This is a
**work list, not work done**: each item says what was reported, what the code
actually does, and a direction — nothing here is a decision about how to fix
it, and none of it is on the live box.

Same shape as `docs/dry_run_feedback_2026-08-30.md`, and ordered as reported
rather than by severity.

---

## 1. The med kit INFINITE poster does not work

**Report.** "The infinite poster for the med kit appears to not work
properly. Not sure why."

**Diagnosis.** Two candidates, both real, and the second may be the one that
was actually seen on the night.

*A medpack refuses anybody who is not knocked out.*
`item_actions._handle_medpack` (`backend/item_actions.py:87`) raises unless
`user.state == KNOCKED_OUT`, so every scan by a healthy player is a 403
reading "Medpacks can only be used on knocked-out players". That is
deliberate and tested (`tests/test_items.py`,
`test_collecting_revive_while_alive`) — but it means the medpack poster in
the warm-up room can never do anything at all, because the room is full of
players at full hit points. It is the one sandbox card whose only possible
effect is an error message.

*A knocked-out player cannot collect from a URL at all.*
`CollectItemFromQueryParam` is mounted inside `BulletCount`
(`react-ui/src/BulletCount.js:108`), which `UserMode` renders only while
`isAlive` (`react-ui/src/UserMode.js:100`). So a player who scans a medpack
card with their **phone's own camera** — which opens `{WEBSITE_URL}/?d=…` —
gets no request, no error and no reaction, at exactly the moment the medpack
is the one card they need. The in-app scanner (`QRParser`, mounted via
`WebcamView` regardless of state) still works, so whether the poster "works"
depends on which camera the player used.

Ruled out along the way: the artwork exists
(`backend/image_templates/medpack_1.png`), so the poster prints; `unlimited`
correctly skips the duplicate check on a rescan
(`user_interface.collect_item`); and `hit()` re-sets `time_of_death` on every
knockout, so `award_HP` not clearing it (unlike `set_HP`) is not a live bug.

**Fix direction.** Two separate decisions. For the sandbox: either let a
medpack top up a living player, or drop it from `printables.SANDBOX_CARDS`
so the room does not hand out a card that cannot work. For the URL path:
mount the collector at the top level of `UserMode` beside
`JoinFromQueryParams` — noting that doing so loses `BulletCount`'s
`anyActive` gate, which is what stops a collection navigating home in the
middle of a pickup animation, so that gate needs somewhere else to live.

**Severity.** Medium for the sandbox (a confusing poster in the warm-up
hour); **high** for the URL path, which silently breaks the one item whose
whole purpose is to be used under time pressure.

**Related.** The armour poster is half-dead for the same family of reason:
`_handle_armour` refuses armour no better than what you have, so the
sandbox's level-2 card works once per player and errors on every rescan,
which is not what a page headed INFINITE promises.

---

## 2. A failed scan flashes red and says nothing

**Report.** "The general flash of red when you scan a QR code with a failure
is very unhelpful and not very informative. We need to make it clear why a
thing is not being scanned."

**Diagnosis.** `collect_item` writes a plain-English `detail` for every one
of its refusals — withdrawn batch, switched-off code, already collected,
wrong state, armour no better than you have, weapon you already hold — and
`QRParser` read it off the response and discarded it. The flash is also
obstructive rather than merely uninformative: `BlankScreen` is an opaque
full-screen overlay at `z-index: 100` for about four seconds, so a message
added naively would sit underneath it.

Three further cases produced no reaction whatsoever: a card opened with the
phone's own camera (logged to a console nobody on a phone can see, then
navigated home either way); a URL carrying no `d` parameter, which raised
`KeyError` out of `ItemModel.from_base64` and so was a 500; and a team card
pointed at the in-game camera, which never got past decoding.

**Status.** Addressed in **PR #298** (`claude/med-kit-infinite-poster-e3c2gb`),
opened before the instruction to record rather than fix. CI green, not
merged, not deployed. Merging it is Charles's call, and nothing reaches the
players until someone runs the deploy workflow.

**Severity.** Medium — no state is lost, but it is the difference between a
player retrying usefully and concluding the app is broken.

---

## 3. Resolving duplicate players needs its own page

**Report.** "The interface for resolving duplicate players needs to be an
entire separate page and it needs to be easier to use. That was the majority
of the work that I had to do in the setup as the admin."

**Diagnosis.** There is no duplicate-resolution interface as such. Merging
is one control among seven on `PlayerRow`
(`react-ui/src/AdminMode.js:362–500`), a bare `<li>` in a flat `<ul>` under
the **Players** heading on the main admin page. Each row carries a rename
box and button, a team select, a slot select, "Put in team", "Delete", a
"(same person as…)" select, "Merge" and a team-leader toggle — all inline,
none of them at the touch sizes the admin house style asks for
(`ReferencePhotos.js` and its `.module.css`, per `CLAUDE.md`).

Four things make it slow in the hand, on a phone, at the door:

- **Nothing detects a duplicate.** The server has `merge_user` and
  `UserAlias` (`backend/admin_interface.py:1668`) but offers no candidate
  pairs, so finding the duplicate is the admin's own eyeballing job across
  the whole roster.
- **The merge target is an unfiltered `<select>` of every user in the
  database**, labelled by `playerLabel` — name, or `unnamed (first 8 hex of
  the uuid)`. With thirty-odd players plus strays, picking the right one
  means scrolling a long native picker, and the nameless strays that are
  *precisely* what needs merging are told apart only by a uuid prefix.
- **The list is one flat column with a single filter** — a "Show unnamed
  players" checkbox. No search, no sort, no grouping by likely-same-person,
  and the rows most likely to need work are the ones hidden by default.
- **Confirmation is `window.confirm`**, so the decision is taken against a
  one-line sentence rather than the two players' details side by side; there
  is no undo, and `merge_user` deletes the stray's row.

**Fix direction.** A route of its own (`admin/duplicates`, alongside
`admin/reference`, `admin/codes` and the rest in `react-ui/src/index.js`),
built to the `ReferencePhotos.js` exemplar: one column of large targets,
state said in words, ordered the way the job is actually done. Worth
considering there — none of it decided — a server-side candidate list that
proposes likely pairs (a nameless session with no team against a named
player, same team, same identity slot, close in time), a side-by-side card
showing what each of the two holds so the survivor is an informed choice
rather than a dropdown entry, and a confirmation that names what moves.
`urlState.js` applies: which pair is being worked on belongs in the path, so
a reload on a phone does not lose the admin's place.

**Severity.** High. Charles reports this as the majority of the admin work
during setup, which makes it the largest single cost in getting a game
started — worse than anything it competes with on the roadmap for the next
night.

---

## Ground rules for anything on this list

- The live database is real again the moment new join links go out
  (`CLAUDE.md`, "The game is live"). The dated exception of 15 September has
  expired.
- Merging to master deploys nothing. `live` and `staging` are both moved by
  hand, and live is never deployed on an agent's own initiative.
- If a change here alters something an admin presses on the night, change
  `docs/game_day_runbook_2026-09-19.md` with it.
