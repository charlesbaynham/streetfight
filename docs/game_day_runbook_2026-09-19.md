# Game-day runbook — Saturday 19 September 2026

`docs/saturday_plan_2026-09-19.md` §5 as a checklist, with the button behind
every step named. Written against the code as it merged, not against the
specs: where a milestone's text and the shipped thing disagree, this file
follows the code.

Two people run the night (plan §6). **Charles** announces drops, triggers
circles and rules on whatever CharlesBot escalates. **Gaby** cycles out and
places every drop from the courier page, and runs the WhatsApp challenges.

Everything admin is at `streetfight.houseabsolute.co.uk/admin`. The pages
named below are the nav links across the top: **Admin home**, **Printables**,
**Courier**, **Shot queue**, **Reference photos**, **Spectator screen**.

---

## Thursday 17 September — the print run

Mint everything from **`/admin/printables` on the live deployment**. The codes
are signed with the `SECRET_KEY` of the box that mints them and carry that
box's `WEBSITE_URL`, so a sheet run off a laptop whose `.env` has drifted is a
stack of paper nobody at the party can scan — and you only find out when
somebody in a pub points a phone at it. Printing from live makes it right by
construction.

**Print at actual size, never "fit to page".** "Fit to page" shrinks the QR
below what a phone reads across a room.

Every panel that mints says above its button how many codes a press produces.
**A second press mints a second set** — it is not a re-download of the first.

| What | Panel | Count | Notes |
| --- | --- | --- | --- |
| Team cards | **Team cards** | one per team + a spare each | The door code. This is what turns a signed-up player into a team member. |
| Pub certificates | **Pub certificates** | **22** | 19 pubs are on the venue, The Speaker among them; 22 gives a few spares. 5 bullets to every member of the first team to scan, once per team, every team. |
| Drop cards | **Drop cards** | as many sheets as you have hiding places | 8 cards to a landscape A4 sheet, every card a distinct item. One press per item type — set **Item** and **Amount per card**, then mint. |
| Sandbox posters | **Sandbox posters** | 1–5 copies of each | Six kinds, one A4 page per kind per copy, headed **INFINITE**. Every code is unlimited and batched `sandbox`. |
| Map poster | **Map poster** | 1 (A3) | **Hold — see below.** |

### Drop cards: what to mint

Set the **Batch** field to `game` (the default) for everything in this
section. The batch is what lets the sandbox be switched off at 16:00 without
touching the real cards.

- **Armour: level 2 or higher. Never level 1.** Everybody now starts with
  their armour on (`STARTING_HIT_POINTS = 2`, PR #267), which *is* armour
  level 1 — so a level-1 card is refused for anybody who has not already been
  hit, and reads as a dud card rather than as a rule. Level 2 works on
  everybody.
- Ammunition, med packs and weapons as you like. The weapon table is
  Eat-a-bullet `(1 damage, 5 s)`, Pewster `(1, 25)`, Tracka-Tracka `(2, 25)`,
  OMG `(3, 25)`.
- **Radar** cards: **Item** = `radar`, then **Minutes it lasts** (defaults to
  5). Print a few — the card is worth as much to everybody else as to the
  holder, since the scan is announced.
- **Circle warning** cards: **Item** = `circle_warning`. No number to set: the
  card shows the next circle until that circle is announced to everybody,
  however long that takes. Worth hiding somewhere that takes effort to reach;
  it is the only card that buys information rather than equipment.

### The sandbox posters

Six kinds, minted in one press: ammunition ×5, level 2 armour, a med pack,
and three weapons (Pewster, Eat-a-bullet, Tracka-Tracka). Every one is
`unlimited` — the same player can scan the same poster over and over, which is
the whole point of a warm-up room — and every one is batched `sandbox`, which
is how they all die at 16:00.

Each is a **portrait A4 page of its own** with **INFINITE** across the top —
which is how you tell one from a drop card while sorting the print run. They
carry the same drawings, so anything without that word across the top belongs
in the box to be hidden round the town, not on a wall.

Two things about the drawings, so they are not a surprise on the wall: the
ammunition poster is **5 bullets, not 20** (there is no 20-bullet drawing, and
being unlimited, five a scan is no less than twenty), and the **Eat-a-bullet
poster's drawing reads "Pewster / Damage: 1"** — true of both weapons, since
only the delay differs. The corner tag and the log say which is which.

### The map poster

**No longer held** — the redrawn map landed on 17 September, so print it.
`Map poster` panel, A3 portrait by default; A4 is the same design scaled.

All nineteen pubs are named on the drawing now, each with a numbered badge
that matches the legend underneath. One thing to know if it ever looks wrong:
the map is *rendered* from `backend/venues.py`'s landmarks rather than drawn
by hand, so a pub missing from the poster is a pub missing from that dict, and
the fix is to add it there and re-run the renderer — not to edit the picture.

**The poster must be reprinted after any change to the pub list**, since the
map and the legend are both built from it.

### After the print run

**The log of what was minted is `/data/qr_codes.csv` on the live box** (PR
#279; before that deploy the backend could not write the file at all, so
anything printed earlier left no record), one row per code: id, tag, index, item type, number, damage, timeout, once-only,
as-team, batch. That is what the corner tag on a card is for - it names the row
rather than the item, so two weapon cards drawn the same are told apart by
reading it, not by scanning them.

**Deploy live.** Not because the paper needs it — a code is a signed payload
and the handler behind it can change afterwards — but because the weapon
table, the cooldown and the countdown all have to be on the box by Saturday
anyway. Back up `/data` first (below).

---

## Friday 18 September

### Resize the droplet

Live runs on a very small DigitalOcean droplet, sized for sign-ups: not for
thirty phones posting a fix every five seconds, the vision pipeline draining a
queue, and the spectator screen. In order:

1. **Take a DO snapshot.**
2. Power off.
3. Resize **CPU and RAM only**. A disk resize cannot be undone.
4. Power on.
5. Verify `/api/get_version` answers and the admin page loads.

`/data` is on the root disk and survives a resize.

### Try it on a phone, on staging

`scripts/deploy.sh staging <ref>` (or the **Deploy to staging** workflow), then
at `https://streetfight-staging.i.houseabsolute.co.uk`:

- **The countdown.** Place a NEXT circle, cue two minutes, watch the strip on
  a player's phone and the circle close.
- **The courier page.** Broadcast from a phone and watch the aeroplane move on
  another phone's map; place the drop and check the crate is legible under the
  expanding blue ping. This is the one thing in the week that is entirely a
  question of what it looks like, and nobody has seen it on a real screen.
- **The sounds**, on an iPhone. Tap the sound-check row on the waiting page
  first — that tap is also what unlocks audio in the browser.
- **A radar card**: scan one and check the dots and the countdown strip
  appear, and that the ticker announces it.
- **A circle-warning card**: with a NEXT circle placed and not cued, check it
  is invisible on an ordinary player's map, then scan the card and check it
  appears on the holder's — and disappears from a second scan's reach once you
  cue the countdown.
- **The circle plan.** Set `LANDMARK_CIRCLE0`…`3` in staging's env file, reset
  to start state, and check the **Circles** panel says CIRCLE0 is on the map
  and private. Close it and check CIRCLE1 arms itself.

Staging's database starts empty; press **Fire demo game** on the admin page to
fill it with the thirty-player sample cast.

### Back up `/data` before every live deploy

Thirty seconds, and it makes everything reversible
(`docs/deployment_droplet.md`, "State and backups"). Do it before the Thursday
deploy and before any Saturday hotfix.

---

## Saturday: setup from 14:00

Meet at The Speaker. A room is booked for two hours.

- Armbands and hats go in baskets for players to collect themselves. The app
  has already told each player what to wear and which hat and armband to pick
  up (the "At the door" row on their waiting page).
- **Team leaders** are responsible for their team being correctly equipped.
  Nominate them on the admin roster — the toggle is on each player's row on
  **Admin home** — and they get a checklist on their own phone.
- **The Speaker is a playable pub.** Hand the bar staff its 5-bullet poster
  and ask them to keep it out of sight until 16:00.
- Charles and Gaby's only setup job is the reference photos:
  **`/admin/reference`**, which shows what each player should be wearing,
  takes the photo, and reads it back garment by garment. A latecomer who never
  passes the desk can have a photo **uploaded** from the same page instead.

## The warm-up sandbox, 14:00–16:00

Posters on the walls of the room, free-for-all, everybody learns the
mechanics. The game is **running** during this (players need to be able to
shoot), and the vision pipeline handles the volume.

---

## The 16:00 transition

In this order. Steps 1–3 are on **Admin home**, in the game's panel.

1. **Pause.** The **Pause game** button. Every player's app goes dark.
2. **Reset to start state.** The button under the join QR codes. It is
   **two-tap**: the first tap arms it and it says "Tap again to wipe the
   sandbox"; it disarms itself after six seconds. It **refuses unless the game
   is paused**, which is why step 1 comes first.

   It wipes: ammunition, shots (and so the queue), the ticker, every scanned
   item, all three circles and any cued countdown. Everyone goes to 0 bullets,
   2 hit points (armour on), the basic Pewster and 3 appeals.

   It then **places CIRCLE0 straight back**, privately: the reset puts the
   game at the top of the circle plan and arms its first circle, so the real
   game starts with a circle already waiting for whoever finds an
   early-warning card.

   It keeps: reference photos, identities and outfits, teams, team leaders and
   last known locations. Nothing earned at the door is lost.
3. **Withdraw the sandbox codes.** On **Printables**, the **Withdraw codes**
   panel. The field defaults to `sandbox` and the button names what it is
   about to turn off — `Withdraw "sandbox"`. One press.

   **Read the button before you press it.** Any batch that is not `sandbox`
   gets a red warning first, because withdrawing `game` would turn off every
   card in the town. If you do it by mistake, **Allow again** is in the list
   directly underneath.
4. **Leave and get clear of the area.** About ten minutes.
5. **WhatsApp**: "the game has begun".
6. **Start.** The **Start game** button. Player apps come back live.

---

## Running the game

Circles roughly every 45 minutes, alternating with drops.

### Cue a circle

**One act, because the circle is already placed.** The game runs the four
circles off a plan (`CIRCLE0`…`CIRCLE3`, coordinates from the env file) and
arms the next one privately the instant the last one closes, so the only
thing left for you is:

1. **Cue it.** In **Countdown**: **Event** = "circle closes", minutes
   (default **10**), **Start countdown**.

The **Circles** panel above says which planned circle is up, its radius, and
whether it is on the map — read it before you press. If you want the circle
somewhere else, place NEXT by hand there first (landmark or coordinates, the
radius reminders are printed under it); the plan carries on afterwards
regardless. **Place planned circle** re-arms the one the game is on, and
**Skip to the next one** moves the plan along if a circle has to be dropped.

The cue is what makes the circle public. At that moment the ticker announces
it, the circle appears on every player's map, and their phones grow a strip at
the top counting down. At zero the next circle becomes the exclusion circle,
the old next circle is cleared, and the ticker says the circle has closed.

Four consequences of the circle being private until it is cued (M6.2):

- **Take your time.** Placing a circle used to be the announcement; it is now
  private working-out, which is why the plan can place them long in advance.
- **Moving or clearing NEXT makes it private again**, so changing your mind
  mid-countdown takes the old circle off every phone rather than leaving two
  stories on the map.
- **`BOTH` is public immediately** — it puts the next circle exactly where the
  exclusion circle everybody can already see is, so there is nothing to hide.
- **Cueing spends every early-warning card in the game**, which is the point
  of them: what they bought was the head start you have just ended.

**If NEXT is empty when the clock runs out, nothing is promoted** — the
countdown just clears. That is deliberate: the alternative is blanking the
play area under thirty players because somebody tidied up mid-countdown. It
should not arise now that the plan places NEXT for you, but the panel says
whether it is placed, and that line is worth a glance before each cue.

**Cancel countdown** calls the clock off and leaves the circles exactly as
they are.

**Your own map always shows the next circle**, cued or not. There is no
on-screen indicator of whether it has gone public yet — the countdown panel
sits directly under the circle controls, so cueing it is the next thing in
front of you.

### Cue a drop

Same panel: **Event** = "drop lands", minutes (default **5**), and a
**contents** box — what is in it, in your words. That text goes on every
player's strip and into the ticker announcement, which is the whole reason
anybody runs for a drop.

At zero the ticker says **"The courier has set off"**, the countdown clears,
and **nothing appears on any map**. The crate is not on the map until the
courier starts broadcasting — so have the courier page open.

### The courier page

**`/admin/courier`**, on the phone that is carrying the crate. Four things:

- **Broadcast my location.** Posts a fix about once a second. The page says
  where you are in words — "Broadcasting — last fix 2 s ago, ±8 m". Players
  see an aeroplane on their maps, at most five seconds behind you.
- **Place drop here.** Two-tap — the first tap arms it and it says "Tap again
  to put the crate here". Puts a crate at your current fix (20 m radius),
  announces it in the ticker, clears the courier and stops broadcasting. The
  crate icon appears at the centre of the blue ping. Each press is its own
  crate: putting out a second one leaves the first exactly where it is
  (M4.3). **The blue ping moves to the newest crate** — the older ones keep
  their icon on the map, without the ping, until they are collected, so the
  flashing circle always means "this is the one that has just landed".
- **Crates on the ground.** Every crate still out, with the time it went
  down, and a **Collected** button on each — also two-tap. Pressing it
  announces "The supply drop has been claimed!", takes the blue circle and
  the crate off every map, and drops the row off this list. Nothing else can
  do that: **the app never sees anybody pick a crate up**, so if nobody
  presses this the crate stays on the maps all night.
- **Stop broadcasting** without placing, if the run is abandoned.

The list comes from the server, so it survives a reload and shows a crate
somebody else placed — hand the phone over mid-evening and the list comes
with it.

The page holds a screen wake lock, so the phone will not lock itself
mid-walk. If broadcasting stops for any reason, the aeroplane fades and then
disappears from everyone's maps after a minute of silence — a dot left where
somebody used to be is worse than no dot.

### Radar

Shipped (M6.1). A player who scans a radar card gets five minutes of everyone
else's **last known** positions on their map — never live, and the labels say
so: "last seen 3 min ago", greying as a fix ages. A strip at the top counts
down the time left. Teammates are green and opponents red, which since R15 is
the only place anybody is told which is which by eye.

Two things to expect on the night:

- **The scan is announced publicly** — "*X* has radar for the next 5 minutes -
  keep moving!". That is deliberate: half the card's value is that everybody
  else starts moving, and a silent radar would be a surprise nobody could
  argue with.
- **A player who has reported no fix at all does not appear**, and anybody
  knocked out or dead is drawn grey and labelled "out" rather than given an
  age. So a thin-looking radar is usually a quiet phone, not a bug.

A second card while one is running is refused. Both resets clear it, so a
radar lit during the sandbox hour does not survive the 16:00 button.

### Early circle warning

Shipped (M6.2). A player who scans one sees the next circle on their map
**until it is cued** — the whole private stretch, not a fixed ten minutes.

- **The public ticker line is anonymous**: "Somebody knows where the next
  circle is...". Naming the holder would tell thirty people whose route to
  watch, which is exactly the advantage the card just bought.
- **The holder is told privately that it was them.** A card that appears to do
  nothing is a card somebody scans again.
- There is no strip and no countdown for it — the circle appearing on the map
  is the effect. **Cueing the circle spends every warning in the game**: at
  that moment everybody can see it anyway, and the next private circle belongs
  to whoever finds the next card.
- **A card scanned with nothing to show is refused, not wasted**: no circle
  placed, or one already announced, and the scan rolls back with the card
  still good. The plan below is what makes that rare.

So the sequence a warning card pays off against is: the plan places NEXT
(private, holders can see it), you cue it (public, everybody sees it), it
closes and the plan places the one after. The gap between placing and cueing
is the card's whole value — and it is now the game that keeps that gap open,
not your memory.

### Shots

**Check the two CharlesBot tick-boxes are on before the game starts.** They are
on **Admin home**, in the game's panel, and both default to **off**:

- "CharlesBot reviews shot photos automatically" — annotates the queue.
- "CharlesBot verdicts resolve shots automatically" — actually rules on them.

With both on, the queue drains itself: CharlesBot reads every shot, escalates
what it cannot settle to a stronger pass, and hands a shot to a human only
when even that came back unsure. With them off, every shot waits for an admin
— which is the safety valve, and a perfectly good way to run the night if
something looks wrong, but it is thirty players' worth of shots by hand.

**`/admin/shots`** is where the ones that need a human land. Ruling on a named
candidate is deliberately two taps: the row selects, a separate "Hit *name*"
button rules.

Either party to a resolved shot can appeal it once from a budget of three, and
an appeal re-opens the shot on its own list, oldest complaint first.

### The spectator screen

**`/admin/spectator`** on a laptop wired to a TV, left alone. Read-only. It
holds a wake lock and says in its headline when it has not got one. The
countdown, the courier and the crate all show there too.

---

## When things go wrong

### A countdown fires while the server is restarting

Nothing is lost. The deadline is a **column**, not an in-process timer: on
startup `next_event.sweep()` re-arms every cue that is still in the future and
fires at once any whose moment passed while the process was down. A circle
that should have closed while a deploy was going out closes as soon as the box
is back.

Double-firing is guarded twice — arming a cue cancels the game's pending
timer, and firing re-reads the deadline and refuses one it does not recognise
— so re-cueing during a restart is safe.

### A player says the app is eating their shots

It is the cooldown, and it is now enforced on the server: 25 s for the basic
weapon, 5 s for Eat-a-bullet. A refused shot says so on screen with the time
remaining. A reload does not help — the countdown comes back, because the
phone derives it from the server.

### A player has two phones, or cleared their cookies

That makes a second, empty player. Merge them from the admin roster; every row
naming the stray is re-pointed at the survivor.

### A hotfix on the night

Additive schema changes only: a new table, a nullable column, or a column with
a plain scalar default. Those deploy themselves. A rename, a drop, a type
change or a `NOT NULL` column with no default does **not**, and will
crash-loop the service against the live database.

`tests/test_database.py`'s `TestLiveSchemaUpgrade` is the gate and runs on
every pull request: it builds the live schema from the committed snapshot,
upgrades it with the current models, and fails on anything that will not
migrate itself. If it is green, the change deploys.

**Back up `/data` before deploying.** And never run `resetdb`,
`RESET_DATABASE` or **Fire demo game** against live — the demo button refuses
if the database holds anybody else's players or games, and that refusal is the
only thing between it and a real evening.

---

## Decisions taken by the sessions

Things decided while Charles was asleep, gathered so they can be overruled in
one place. Each names the PR that made it.

### Balance and rules

- **A level-1 armour card is worthless to an unhit player** (#267). Armour is
  hit points above one, so starting on 2 *is* level 1 and a level-1 card is
  refused. Everything printed is level 2. Related: a fresh player now sees one
  helmet pip where they used to see a cross, which is correct.
- **A single hit no longer knocks anybody out** (#267, #270), so the knockout
  sound is now the sound of a *killing* blow. Rarer, and it means more — but
  the ordinary evening is mostly the confirmed-hit tone, which is still one of
  the original placeholders.
- **Replayed and demo shots are exempt from the cooldown** (#266). Only the
  replay and the demo drip pass a shot its own `time_created`; judging them on
  the wall clock refused nine of the ten. No player can reach that branch.
- **The cooldown the phone shows is clamped to the player's own timeout**
  (#266), so a phone with a badly wrong clock loses at most one cooldown
  rather than being locked out.

### Paper

- **The pub poster says "5x" in a redrawn hand, and still draws two bullets**
  (#254). Copying the bullet sprites convincingly was more than a paint-over;
  the sentence says the number outright. Charles can redraw the line over the
  top — the original is one `git show` away.
- **Nothing printed carries a contact line.** The drop cards had one for a
  day (#262, "This is part of a game - ring 07955 686520"); Charles had it
  taken off on 17 September. So a card found by a stranger says nothing about
  what it is — worth knowing if somebody rings the police about a QR code
  taped under a bench.
- **The sandbox ammunition poster is 5 bullets, not 20, and Eat-a-bullet
  borrows Pewster's drawing** (#263). Both because a card's picture is chosen
  by what it awards, and a poster read across a room has to say what it is.
- **Radar and circle-warning cards use placeholder artwork** (#259) — an
  existing hand-drawn frame with the item's name written in place of the
  illustration. The number of minutes is deliberately not on the card, since
  it is chosen at mint time.
- **The map poster draws its own numbered markers** (#272), because a numbered
  legend is useless without numbers on the map. It excludes circle, drop and
  courier landmarks by prefix — it is the one printable players read.
- **All 23 map markers were kept** in the redraw prompt (#256), though a
  hand-drawn map holds about twenty before it smears. The Broadway/Tothill
  Street cluster is where to look first when the drawing comes back.

### The 16:00 transition

- **Reset to start state is a self-arming two-tap button** (#268). The brief
  said "like the demo button", but that button turns out to have no confirm at
  all — one press and a server-side refusal. This is more friction than a copy
  would have been; say if it is too much.
- **Withdrawing a batch is one press, not two** (#265), because **Allow
  again** sits directly beneath it: the undo is cheaper than the confirmation.
  A non-`sandbox` batch gets a red warning first.
- **A withdrawn code is dead for everybody** (#265) — the check sits before
  anything about the player is looked at, so the answer never depends on who
  scanned it.

### Countdown, courier and maps

- **`promote_next_circle` promotes nothing when NEXT is empty** (#269),
  clearing only the countdown. The alternative blanks the play area.
- **The courier's fan-out is throttled to 5 s server-side** (#273); every fix
  is written, only the announcement is rationed. At walking pace that is about
  seven metres — inside the accuracy of the fix itself.
- **A drop circle is placed at a 20 m radius** (#273, `DROP_RADIUS_KM`). It
  marks where the crate is, not an area to search. One constant to change.
- **The courier disappears after a minute of silence** (#274) rather than
  fading and staying. Fixes arrive about once a second, so a minute is
  somebody who has stopped broadcasting or gone indoors.
- **The courier's aeroplane is a placeholder** (`images/art/courier.svg`,
  #274) until Gaby's drawing arrives. Replacing the file is the whole change.
- **A fourth courier column, `courier_accuracy`** (#273), beyond the three the
  spec named: the route accepts an accuracy and dropping it on the floor would
  be worse. Captured, consumed by nothing.

### The experimental items

- **A radar scan is announced publicly** (#275), like every other collection.
  Half the card's value is that everybody else starts moving; a silent radar
  would also be a surprise nobody could argue with.
- **Radar ages travel as "seconds ago", not timestamps** (#275), so a phone
  with a wrong clock still shows the right age, and the label goes on ageing
  between polls instead of freezing for five seconds at a time.
- **Asking for a radar you do not have is an error, not an empty list**
  (#275): "you have no radar" and "there is nobody out there" must not look
  the same.
- **Placing the NEXT circle now says nothing at all** (#277). It used to post
  a ticker line; announcing a circle nobody can see is worse than silence, so
  that message is retired. The **cue** is the announcement now.
- **The circle-warning ticker line is anonymous** (#277) — "Somebody knows
  where the next circle is..." — unlike every other collection, which names
  the player. Naming them would give away the advantage the card just bought.
  The holder gets a private line saying it was them.
- **The admin's own map now reads the game's circles, not `/get_circles`**
  (#277), which is the player endpoint that does the hiding — otherwise the
  admin would have been blind to their own private circle.
- **The admin has no indicator of whether the next circle is public yet**
  (#277, deliberately). The countdown panel sits directly under the circle
  controls, so cueing it is the next thing in front of them.
- **A warning that expires during a restart costs one stale circle on one
  phone** (#277) until the next circle event. The expiry timer is in-process
  and not durable — judged the right price for an experimental card, unlike
  the countdown's, which is rebuilt from a column.

### People

- **The team-leader checklist is the milestones doc's first draft** (#261),
  verbatim, because Charles's own wording had not arrived. It is one array in
  `prose.teamLeader.checklist` — a five-line edit.
- **The leader flag grants nothing.** It decides what one player is shown, not
  what they may do.

### Under the hood

- **`target_knocked_out` is derived, not stored** (#270). A sound cue did not
  seem worth a column on the live schema. If it is ever wanted as a fact, it
  needs a nullable column set in `AdminInterface.hit_user`.
- **Defaulted fields are left out of a QR payload's encoding** (#259), not
  just out of its signature. Adding a batch pushed the pub certificate's code
  up a QR version and past what prints reliably; dropping defaults bought back
  more than the batch cost. An unbatched code encodes byte for byte as it did
  before batches existed.
- **The schema gate is two tests, not one** (#255): the insert-and-read-back
  the spec asked for, plus a schema comparison, because sqlite will happily
  write a row through a dropped nullable column. A new **index** on an
  existing table is knowingly not covered.
- **The map poster reads its image from `backend/map_images/`** (#272),
  symlinks shipped as package data. The deployed wheel packages `backend*`
  alone, so the obvious `react-ui/src/images/` would have worked in a checkout
  and 500'd on live.

---

## Still outstanding

- **M8 — the annotated admin map.** The mechanism is in: any
  `LANDMARK_<NAME>="<lat>,<long>"` in `/data/secrets/streetfight.env` joins
  the venue's landmarks, and `CIRCLE0`…`CIRCLE3` are the four the circle plan
  arms by itself. What is still needed is the numbers off Charles and Gaby's
  marked-up map, and the `DROP_*` ones alongside them.
- **Gaby's courier artwork**, whenever it arrives.
- **Charles's own team-leader checklist**, if the first draft is not right.
