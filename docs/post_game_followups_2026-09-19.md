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

## 8. The spectator screen's knockout countdown says the opposite of what it means

**Report.** "The spectator view currently says that people will be back in XXX
minutes when someone is knocked out, but actually it should say that they will
be dead in XXX minutes."

**Diagnosis.** Confirmed, and it is not merely loose wording — the sentence
asserts the opposite of what the clock is counting. `SpectatorView.js:573–575`
renders

```js
knockedOut && player.time_of_death
  ? `back in ${countdown(secondsUntil(player.time_of_death, now))}`
  : player.state
```

`time_of_death` is written as `now + TIME_KNOCKED_OUT` at the moment a player
drops to zero hit points (`user_interface.hit`), and `User.calculate_state`
reads it as the deadline **after which they are `DEAD`**. So the number is
time until they are permanently out, and reaching zero is the bad outcome,
not the recovery. What actually brings them back is a teammate finding them a
medpack *before* it expires — which is the one thing the row does not say.

The player's own screen already has this right: `KnockedOutView` shows
`prose.guideImages.medkitWarning`, "Get a medkit quick! You will die in:",
over the same deadline. So the two surfaces currently disagree about the
meaning of one number, and the big screen in the room is the one that is
wrong.

**Fix direction.** `dead in 7:23`, matching the player's own wording. One
string at `SpectatorView.js:574` — the spectator screen keeps its strings
inline rather than in `prose.js`, so there is nothing to thread. Worth a
thought while in there: the row is the one place a spectator could be told
that a medpack would save them, and the countdown is the moment that is worth
knowing. That is a copy decision, not a required change.

**Severity.** Low to fix, but it misinforms every person watching — the
screen is read from three metres by people who cannot ask anybody what it
means, and it tells them a knocked-out player is coming back when they are
running out of time.

---

## 9. A failing escalation blocks the queue even with "resolve everything" on

**Report.** "In the final showdown, the shots accumulated faster than the
pipeline could process them. We need to make sure it doesn't block, even if
the escalated call fails repeatedly. It should just 'refund' and continue if
I've got the 'always resolve shots' button ticked."

**Diagnosis.** Confirmed, and the hole is exact: with
`ai_resolve_everything_enabled` on, the one case it most needs to cover — the
escalation model failing — is precisely the case it declines to cover.

`_decide_escalated` (`backend/shot_auto_actions.py:426`) reads:

```python
state = head.ai_escalation_state
if state is None:
    return (_ESCALATE, None)
if state != AI_REVIEW_STATE_DONE or not head.ai_escalation:
    return None
```

An **errored** escalation falls into that second branch and returns `None`,
which sends `process_queue_head` straight back out — and `resolve_everything`
never gets a look in, because `_forced_fallback` is only reachable from the
`_ESCALATE` branch, where *nothing was started at all*. An escalation that
started and failed takes a different road. The docstring says this is
deliberate: "Errored -> the admin's … neither of those is ever forced, one
being a verdict still coming and the other a verdict that never came." The
state is also sticky — only a re-run of the weak review clears it
(`AdminInterface.store_shot_ai_review`) — so a model failing repeatedly parks
the head until a human intervenes.

**Why that stalls everything, not just one shot.** Reading is parallel:
reviews run at `AI_SHOT_REVIEW_CONCURRENCY`, and escalations start as soon as
a shot needs one (`escalate_early`) at `AI_SHOT_ESCALATION_CONCURRENCY`
(default 6). **Resolving is strictly serial and head-only** — by design, and
`process_queue_head` says so: "An ambiguous head blocks everything behind it:
that is the required ordering, not a missed opportunity." So one unresolvable
head stalls the whole queue however many shots behind it are read, scored and
ready. In a final showdown that is the difference between a queue that drains
and one that only grows.

**The remedy Charles asks for already exists as a verb.**
`AdminInterface.refund_shot` marks the shot checked with result `refunded`,
**gives the bullet back**, and announces it in the ticker. It fits the
existing design's own justification better than the current behaviour does:
"resolve everything" refuses to force a verdict with nothing to resolve from
because "with nobody to notify, nobody can appeal" — but a refund has nothing
*to* appeal. Nobody was hit, the shooter is not out of pocket, and the player
is told. (Note the consequence: `appeal_refusal` treats `refunded` as "there's
no verdict on this shot to appeal", so a refund is terminal. That is the
right bargain here, but it is a bargain.)

**Fix direction.** Under `ai_resolve_everything_enabled`, an errored
escalation should fall through to a resolution rather than returning `None`
— `_forced_fallback` first if the weak reading has anything to say, and a
**refund** when it does not, so the queue always advances. Two things worth
deciding at the same time rather than assuming:

- **Whether a deadline belongs here too.** The reported failure was
  throughput, not only this one stuck state: a head whose escalation is
  genuinely *pending* still blocks, and under load with
  `OPENROUTER_TIMEOUT_SECONDS` per call and reasoning effort `high` on the
  escalation path, "pending" can be a long time. A head that has waited more
  than N seconds could resolve on the weak reading, or refund, instead of
  waiting. That is a bigger change than the errored case and needs Charles's
  agreement about what the players see.
- **Whether strict ordering has to hold during a showdown at all.** It exists
  so that a knockout is not applied out of sequence. Whether that is worth a
  stalled queue when thirty shots are landing a minute is a game-design call,
  not a code one.

**Severity.** High. It is the failure that most degrades the game while it is
being played, it happened on the night, and the toggle Charles ticked to
prevent exactly this does not cover it.

---

## 10. Shot resolution is too slow to keep up with a showdown

**Report.** "We also need to make the shot resolution quicker in general. 10s
is fine in the early game, but not when shots are arriving every second."

**Diagnosis.** The sibling of item 9: that one is a head that never moves,
this one is a head that moves too slowly. The arithmetic is the whole
problem. Sustained throughput is **concurrency ÷ latency**, and the live path
is configured at:

| Knob | Value | Where |
| --- | --- | --- |
| `AI_SHOT_REVIEW_CONCURRENCY` | **2** | `ai_shot_review.DEFAULT_CONCURRENCY` |
| `AI_SHOT_ESCALATION_CONCURRENCY` | 6 | `shot_escalation.DEFAULT_CONCURRENCY` |
| `OPENROUTER_TIMEOUT_SECONDS` | 60 s per request | `vision_client.DEFAULT_TIMEOUT_SECONDS` |
| `REVIEW_ATTEMPTS` | 3 | `ai_shot_review` |

Two review slots at 10 s a review is **0.2 shots per second**. At one shot a
second the queue grows by 0.8 every second — which is what was seen. To keep
up at 1/s the pipeline needs `concurrency ÷ latency ≥ 1`: ten slots at 10 s,
or two slots at 2 s, or anything in between.

Three things make one review cost what it costs:

*The live path is multi-turn.* `ZOOM_SCREENED` — the mode the live pipeline
runs — sends a screening call and then loops: up to `MAX_ZOOMS` (2) zoom
follow-ups, then a final full-reading turn. So a review is **two to four
sequential round trips**, not one, and they are sequential by construction
because each turn is a reply to the last. `ZOOM_SINGLE` is one turn and
exists already (used by the workbench).

*Reviews are the narrowest pipe in the system, and arguably backwards.* Every
shot needs a cheap review; only some need an escalation. Yet escalations run
six at a time and reviews two. The escalation knob's own comment says it is
"a separate knob, since each call costs more than a review" — which is an
argument about money, not about throughput, and the throughput consequence
was never the point of that number.

*A failure is expensive.* Three attempts at up to 60 s each is a worst case
of three minutes for one shot. The semaphore is taken **per attempt** rather
than around the loop — deliberately, so a retry queues behind other shots
instead of holding a slot for all three — which is the right design and worth
keeping.

And downstream of all that, resolution is still serial and head-only (item
9), so the *queue* drains no faster than the head's own chain, however
parallel the reading is.

**Fix direction.** Not decided, and they are independent, so they can be
taken in any order:

- **Raise `AI_SHOT_REVIEW_CONCURRENCY`.** The cheapest lever by a distance —
  an environment variable, no code, no schema. These are network-bound calls,
  so the ceiling is the provider's rate limit and the bill, not the droplet.
  Worth measuring what the provider actually allows before picking a number.
- **Cut the turns.** Running `ZOOM_SINGLE`, or screening only when the target
  is genuinely small, removes one to three round trips from the critical
  path. That is a *recognition-quality* trade, so it wants the replay
  workbench (`/admin/replay`) against real shots from this game rather than a
  guess — and the whole contract (prompt, `zoom_mode`, schema) has to move
  together, per `CLAUDE.md`.
- **Adapt to the queue.** A pipeline that ran `ZOOM_SCREENED` with a long
  timeout when the queue was empty and `ZOOM_SINGLE` with a short one when
  forty shots were waiting would match what Charles actually asked for — 10 s
  is fine early and not in a showdown. More machinery than the other two, and
  worth doing only if the cheap levers fall short.
- **Shorten the timeout.** 60 s is far past useful for a shot somebody is
  waiting on; failing at 15 s and retrying would spend the same worst case
  more usefully.

**First, though: measure.** Nothing currently records how long a review takes,
so "10 s" is an impression from the night rather than a number, and every
choice above is a guess without it. Timing the review and the escalation into
the log (or onto the stored payload) is small, and makes the next game's
report a distribution instead of a feeling.

**Severity.** High, and it compounds item 9: at 30 players in a final
showdown this is the difference between a game that adjudicates itself and
one where the admin is the bottleneck for the rest of the night.

---

## Ground rules for anything on this list

- The live database is real again the moment new join links go out
  (`CLAUDE.md`, "The game is live"). The dated exception of 15 September has
  expired.
- Merging to master deploys nothing. `live` and `staging` are both moved by
  hand, and live is never deployed on an agent's own initiative.
- If a change here alters something an admin presses on the night, change
  `docs/game_day_runbook_2026-09-19.md` with it.
