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

## 4. The nav-bar queue count ignores the contested queue

**Report.** "The shot queue in the menu of the admin page has a number in
brackets which shows the number of outstanding shots, but it only shows the
number in the queue — it doesn't show the number in the contested queue,
which is actually the most important one. So the number should be the sum of
those two."

**Diagnosis.** Confirmed, and the two counts really are disjoint rather than
overlapping, so the sum is the right answer and cannot double-count.

`ShotQueueLink` (`react-ui/src/AdminCommon.js:153`) fetches
`admin_get_shots_info` alone and renders `shot_ids.length`. That endpoint is
`get_shots_ids(include_checked=False)`, which filters on `Shot.checked ==
False`. The contested queue is `get_contested_shot_ids()`
(`backend/admin_interface.py:1334`), which filters on `appeal_state ==
APPEAL_OPEN` — and an appeal can only be raised against a shot that is
already `checked` (`user_interface`'s appeal guard, "This shot hasn't been
adjudicated yet"), which appealing does not clear. So every contested shot
is invisible to that number, permanently, by construction. The endpoint's
own docstring says as much: "these are checked shots and so are not in the
live queue at all".

The page itself is not blind to them — `ShotQueue.js` switches lists on
`?mode=contested` — so this is the nav count alone, which is exactly the
thing an admin glances at to decide whether to go and look.

**Fix direction.** Fetch both in `ShotQueueLink` and add the lengths. Two
details make it smaller than it sounds: raising an appeal already fires
`trigger_update_event("shots", …)` (`user_interface.py:950`), so the
`UpdateListener update_type="shots"` that component already mounts wakes on
a new complaint with no new stream; and there is no ordering or de-duping to
do, since the sets cannot intersect. Worth deciding separately whether the
count should *say* it is two things — `(3 + 1)`, or a second badge — given
Charles's point that the contested one matters more, and that a single
summed number hides which kind of work is waiting.

**Severity.** Medium-high. Nothing is lost, but the one indicator an admin
navigates by under-reports the queue that most needs attention, and silently
— an admin reading `(0)` has been told there is nothing to do.

---

## 5. The circle workflow is confusing to drive

**Report.** "The circle workflow from the admin side needs some serious work.
I keep fucking it up. It's a little bit confusing how I should be doing it, so
we'll make it much smoother later."

**Diagnosis.** The machinery is sound — the plan arms the next circle by
itself, which is what removed the one mistake that would neuter the
early-warning card. What has not been designed is the *panel*. Six specific
things, each checkable in the code:

*One job, two panels, no shared state.* Closing a circle is "place it" and
"say when", and those are two separate headings in `GamePanel` — **Circles**
(`react-ui/src/CircleControl.js`) and **Countdown**
(`react-ui/src/EventCue.js`, `AdminMode.js:317–322`). Neither one alone tells
you whether the next press will do what you want, and the sentence that ties
them together is a paragraph of explanatory prose at the foot of `EventCue`.

*Five pieces of state, three of them shown.* What actually decides the
outcome is `circle_plan_index` (the plan pointer), whether NEXT is placed
(`next_circle_lat`), whether NEXT is **public** (`next_circle_public`),
whether the exclusion circle is placed, and whether a cue is running.
`CircleControl` shows the first two, `EventCue` the last. The exclusion
circle's state is said nowhere in words — only as a shape on the map.

*The panel tells a lie once a circle is cued.* `CircleControl` computes
`placed = game.next_circle_lat !== null` and then renders "on the map and
**private** until you cue it" unconditionally — it never reads
`next_circle_public`. That field is on `GameModel` (`backend/model.py:759`)
and reaches the client, but **no production frontend file reads it**: the
only references outside the backend are in `testUtils.js`. So after cueing,
the panel still says the circle is private when every player can see it; and
placing `BOTH` makes it public immediately (`admin_interface.py:641`) while
the panel says private from the first moment.

*Placing by hand silently desyncs the pointer.* `set_circles` writes the
coordinates and never touches `circle_plan_index`, so "Set at landmark" with
NEXT — the natural move when a plan entry has no coordinates, which is
exactly when the panel tells you to "place it by hand" — leaves the pointer
still aimed at the entry you just placed. Only `arm_planned_circle` moves it.
Nothing on screen says which of those two you just did.

*The vocabulary is the enum's, not the admin's.* The circle selector offers
`EXCLUSION` / `NEXT` / `BOTH` / `DROP` in capitals — `CircleTypes` member
names. `BOTH` in particular says nothing about what it does (place the next
circle on top of the exclusion circle, and make it public because there is
then nothing left to hide).

*The three pointer buttons are unlabelled as to consequence.* "Place planned
circle", "Skip to the next one" and "Step back one" sit in one line. The
third moves **two** things — the pointer *and* the exclusion circle, restored
from the entry before — and announces itself in the ticker, unlike everything
else the plan does. None of that is on the page.

**Also worth deciding: cueing a circle is irreversible in one tap.** A single
form submit sets `next_circle_public = True` and wipes `circle_warning_until`
for every player in the game (`admin_interface.py:846–854`) — every
early-warning card spent at once, which "Cancel countdown" cannot give back.
Compare the deliberate two-tap friction on the courier's **Place drop here**
and **Collected**, and the shot queue's two-tap ruling: this is a bigger,
less reversible act than either and has less friction than both.

**Smaller, while in there.** The radius reminders are a hardcoded sentence at
the foot of `CircleControl` ("circle 1: 0.70, circle 2: 0.42, …") rather than
read from the plan, so they can drift from the `CIRCLE_RADIUS_*` the server
is actually holding; and both "set" forms make the admin type a radius by
hand every time, including when the plan already knows it.

**Fix direction.** Not decided — but the shape the complaint points at is one
panel that says, in words, what the game is about to do next and what the one
button in front of you will change, with the plan, the map state and the
countdown read as a single sequence rather than three independent forms.
Worth handing to the **`nudge-ux` agent** (`.claude/agents/nudge-ux.md`)
rather than redesigning from scratch: this is a flow that loses its user
mid-task, which is what that consultant and `docs/nudge/` are for. Two things
should be fixed regardless of what it says, because they are wrong rather
than merely awkward: reading `next_circle_public` so the panel stops claiming
a public circle is private, and saying on screen whether the pointer moved.
Whatever comes out of it, `docs/game_day_runbook_2026-09-19.md` describes
these buttons step by step and has to change with them.

**Severity.** High. Charles reports repeatedly getting it wrong on the night,
and the acts involved are public and hard to undo: a circle closing on the
players, and every early-warning card in the game.

---

## 6. A private next circle and an announced one are drawn identically

**Report.** "Part of the confusion here comes from the fact that the admin
interface can't show the difference between a circle that is private and a
circle that is announced but not yet in force. We need a new colour for ones
which are going to be next but which haven't yet been shown publicly."

**Diagnosis.** Confirmed, and the reason is one line. `MapCirclesFromData`
(`react-ui/src/MapView.js:169`) turns the server's fields into three triplets
through `circleTriplet`, which reads **lat, long and radius only**.
`next_circle_public` is dropped at that boundary and never reaches the
drawing code, so `.nextCircle` — one class, red dotted, pulsing
(`MapView.module.css:78`) — is all four states' single appearance. This is
the map-side half of item 5's text-side problem, where `CircleControl` says
"private until you cue it" without reading the same field.

The admin has four states to tell apart and two paints to do it with:

| State | Now drawn as |
| --- | --- |
| Exclusion circle, in force | dark red shadow fill (`.exclusionCircle`) |
| NEXT, placed, **private** | red dotted pulse (`.nextCircle`) |
| NEXT, placed, **cued and public** | red dotted pulse — *identical* |
| DROP | blue (`.dropCircle`) |

Two consequences beyond the admin's own confusion, both worth a decision
rather than a default:

*The early-warning card holder has the same blind spot.* A player holding a
live card sees NEXT before it is announced (`get_circles`'s `show_next =
next_circle_public or self._circle_warning_is_live()`), and the card's whole
value is that nobody else can. Their map cannot say "only you can see this",
because `/get_circles` does not send `next_circle_public` at all — it only
nulls the coordinates for everybody else. Telling that player which state
they are looking at needs the flag added to that payload too.

*The spectator screen draws private circles on a television.*
`SpectatorView` renders `MapViewAdmin` with a `GameModel`
(`SpectatorView.js:833`), which carries NEXT whatever its publicity. So a
circle the game is deliberately keeping private is on a screen left running
in a room, in the same red as an announced one — which hands the
early-warning card's advantage to anyone who walks past it. Whether the
spectator screen *should* show it is a fair question; that it currently does
so indistinguishably is not a choice anybody made.

**Fix direction.** Carry `next_circle_public` through to the drawing code — a
fourth element on the triplet or a separate prop alongside it — and give
private-NEXT its own class. Which colour means which is Charles's call; the
constraint worth respecting is the admin house style's rule that **colour
means certainty** (`CLAUDE.md`), so the natural reading is amber for the
provisional state (placed, not yet announced, still freely movable) and the
existing red for the announced one that players are already running from.
Also send the flag on `/get_circles` so the card holder's map can mark what
only they can see. `SpectatorView` is exempt from the house style's shapes
but keeps its colour rule, so the same class serves it.

**Severity.** Medium on its own; it compounds item 5, and it is the cheapest
of that cluster to fix — one field threaded through one function, plus a CSS
class.

---

## 7. Destructive admin buttons should all take two presses

**Report.** "The admin interface contains a lot of quite destructive buttons,
which you shouldn't accidentally press. We should make all of the destructive
buttons require two presses to avoid accidental triggering."

**Diagnosis.** The pattern already exists and is already written down as
deliberate — it has simply never been applied past the three places it was
written for. `ResetToStartButton.js` is the canonical implementation: a first
tap arms the button and makes it *say what it is about to do*, a second does
it, and it disarms itself after `ARMED_MS` (6 s) so a button armed in a
pocket is safe by the time the phone comes out. Its comment is explicit that
this must not be collapsed "into one tap or into a `window.confirm`, which is
dismissed without being read". `AdminCourier.js` copies it by hand for
**Place drop here** and **Collected**, saying "Two-tap confirm, as on the
reset button". The shot queue's ruling is two taps by construction.

So there are already **two hand-written copies of the same pattern**, which
makes this a case of `CLAUDE.md`'s "generalise and reuse rather than mint a
new, different version" rather than a new idea.

Everything else divides into two tiers, and the second is the surprising one:

*Guarded by `window.confirm` only* — which the reset button's own comment
calls insufficient: delete team (`AdminMode.js:135`, deletes its players
too), reset game (245), **delete game** (277, "any join links already sent
out will stop working"), delete user (443), merge user (472, deletes a row
with no undo — see item 3), create a second game (661), and clear a player's
outfit (`AdminIdentity.js:445`).

*Guarded by nothing at all:*

| Button | One tap does |
| --- | --- |
| **Fire demo game** (`AdminMode.js:605`) | **drops every table in the database** |
| **Withdraw codes** (`AdminPrintables.js:570`) | kills a whole print run, for every player at once |
| Restore batch (`AdminPrintables.js:610`) | un-kills it |
| Switch a code off / Forget a code (`AdminCodes.js:194,199`) | kills or un-kills one card |
| **Start countdown** (`EventCue.js`) | makes the circle public and spends every early-warning card in the game — "Cancel countdown" cannot give them back |
| Step back one (`CircleControl.js`) | moves the play area and announces the mistake to every player |
| Clear circle (`CircleControl.js`) | takes a circle off every map |
| Pause / start the game (`AdminMode.js:169`) | stops or starts play for everybody |
| Delete reference photo (`ReferencePhotos.js:491`) | throws away the door kit check |
| Hit / set HP / set weapon / give ammo (`AdminMode.js`) | changes a player's state mid-game |

**Fire demo game is the sharp one.** It is a single unguarded tap on the
admin home page that wipes the database, and its only protection is
server-side (`demo_game.refuse_if_live`, which `CLAUDE.md` already calls
load-bearing). That guard does defend a real evening — it refuses if any
player in a team, or any game, is not the demo's own — but the button itself
offers the admin no pause at all, and it sits among ordinary buttons.

**Fix direction.** Lift `ResetToStartButton`'s arm/disarm into one shared
thing — a `useArmedAction` hook or a `<TwoTapButton>` — and apply it to
everything in both tiers above, replacing the `window.confirm`s rather than
adding to them. Three properties are the ones worth carrying over, because
they are what make the friction serve the admin rather than merely obstruct:
the armed button **says what it is about to do** rather than repeating its
own label, it **disarms on a timer**, and only **one** button is armed at a
time (`AdminCourier` already does this per row with `armedClear`). Worth
deciding as part of it: whether the tier-two list above is the right
boundary — pausing the game and giving a player ammo are recoverable, and
friction on a control an admin uses forty times an evening is a cost, not a
free win (`docs/nudge/`: friction is a tool, and the test is whose interest
it serves).

**Severity.** Medium-high. Nothing here was reported as actually having gone
wrong on the night, so this is prevention rather than repair — but the worst
case (**Fire demo game** on a box whose guard happened to pass) is
unrecoverable, and several others are public and instant.

---

## Ground rules for anything on this list

- The live database is real again the moment new join links go out
  (`CLAUDE.md`, "The game is live"). The dated exception of 15 September has
  expired.
- Merging to master deploys nothing. `live` and `staging` are both moved by
  hand, and live is never deployed on an agent's own initiative.
- If a change here alters something an admin presses on the night, change
  `docs/game_day_runbook_2026-09-19.md` with it.
