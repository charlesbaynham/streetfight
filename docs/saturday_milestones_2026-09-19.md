# Milestones for Saturday 19 September 2026

The triage of `docs/saturday_plan_2026-09-19.md` (Charles's plan, kept
verbatim) into work that can be handed to parallel sessions. This file is the
record: every session working on the game before the 19th takes its scope from
a milestone here and reports back into it. When something ships, say so on its
line.

Written 16 Sept, three days out. **Printing happens on Thursday 17 Sept**, so
the first milestone is "everything paper depends on", and it has a
tomorrow-morning deadline that nothing else has.

---

## Ground rules for every session

1. **The live database is real.** Players are signing up now. No `resetdb`,
   no `RESET_DATABASE`, no **Fire demo game** on the live box, and no schema
   change that is not additive. The identity scheme is frozen.
2. **Additive schema changes are safe, and cheap.** `database.load()` runs
   `create_all()` (new tables) and then `add_missing_columns()` (new columns,
   rendering a scalar default as `DEFAULT`) on every startup. So a new table,
   or a new nullable column, or a new column with a plain scalar default,
   deploys itself. A rename, a drop, a type change, or a `NOT NULL` column
   with no scalar default does not — don't write one. (`CLAUDE.md`'s "needs a
   hand-written `ALTER TABLE`" predates `add_missing_columns`; it is
   corrected there in this PR.) An `Enum` column is a `VARCHAR` with no check
   constraint, so a new `ItemType` member needs nothing at all.
3. **Staging is where things are tried on a phone.** `scripts/deploy.sh
   staging pr/NNN` (or the **Deploy to staging** workflow). Live is deployed
   by Charles, deliberately, never by a session.
4. **A QR code is an HMAC over its payload with the live `SECRET_KEY`**
   (`backend/qr_signing.py`, `items.ItemModel.get_signature`), stateless and
   deterministic. That decouples the print run from the deploy: a card minted
   tomorrow validates on Saturday provided the *encoding* it was minted with
   is what the server then understands. So every field a printed code carries
   is frozen the moment the printer runs — the handler behind it is not. M0
   is that freeze.
5. **Adding a field to the item payload must not break the codes already
   printed** (the pub posters and drop cards from #8 are being reprinted, but
   the team cards and any code in a WhatsApp are not). New fields are
   optional, default off, and **left out of the signature when at their
   default**, so an old payload signs exactly as before.
6. **Tests, TDD for bugs, `pre-commit run --all-files`, no fix-me markers (the CI gate)**, as
   `CLAUDE.md` says. Run the tests that cover the change; CI does the sweep.
7. **Prose a player sees goes in `react-ui/src/prose.js`.** Admin pages keep
   their strings inline. New per-game admin controls go in `AdminMode.js`'s
   `GamePanel`, in the `ReferencePhotos.js` house style (big buttons, state in
   words, colour means certainty).
8. **Announce state changes beside the state change**, not in the route
   (`announce_after_commit` / `trigger_update_event`) — the demo drip and the
   CLIs bypass routes.
9. One PR per milestone item unless two are inseparable. Name the milestone in
   the PR title (`M1.1: server-side cooldown`). Update the status line here in
   the same PR.

### What the plan assumed that the code says otherwise

Recorded so nobody builds against the plan's numbers.

- **The cooldowns are 6 s and 1 s today, not "~8 s" and "~4 s".** A weapon is
  the pair `(shot_damage, shot_timeout)` on the player
  (`backend/model.py:318-321`), named by `item_actions.WEAPON_NAME_LOOKUP`:
  `(1,1)` Eat-a-bullet is the fast weapon, `(1,6)` Pewster the basic one,
  `(0,6)` no weapon. The frontend mirrors it in `react-ui/src/weapons.js`.
  **A weapon card carries the pair in its signed payload** (`ItemDataWeapon`),
  so the new table has to be in before any weapon card is minted (M0.1).
- **Armour is hit points above one.** There is no armour column: level *n*
  armour sets `hit_points` to `n + 1` and refuses if you already have that
  much (`item_actions._handle_armour`). "Starting armour 1" therefore means a
  starting `hit_points` of 2.
- **A medpack only works on a knocked-out player** and revives to 1 HP
  (`item_actions._handle_medpack`). Knocked out lasts `TIME_KNOCKED_OUT` (10
  min) and then becomes dead, which no item cures. Fine for the sandbox's
  "revive yourself immediately"; the reset (M2.1) covers the rest.
- **The pub poster says "2x bullets" in Charles's handwriting**, inside the
  artwork PNG (`backend/image_templates/reusable bullets.png`), with two
  bullets drawn. The constant is `generate_pub_pages.BULLETS_PER_TEAM_MEMBER`
  and three tests hard-code the literal 2. Changing the number is an image
  edit as well as a code change.
- **The cooldown is enforced nowhere on the server.** `submit_shot` checks
  team, HP and bullets only (`backend/user_interface.py:607-616`); the only
  timer is `FireButton.js`'s `setTimeout`. Three back-to-back POSTs all
  return 200 (`docs/r9_walkthrough/A4.md`). `MyWebcam.js` never checks
  `response.ok`, so a server refusal would be silent today.
- **Players cannot see anybody on the map**, teammates included. `MapViewSelf`
  draws the own dot only; `admin_get_locations` is admin-authenticated and
  polled every 5 s by `MapViewAdmin`. `set_location` deliberately fires no
  SSE event. Radar (M6.1) and the courier (M4) are the first player-facing
  positions of anyone else.
- **Nothing is timed.** `Game` has no future timestamp; circles move only
  when an admin presses a button; there is no "promote next circle to
  exclusion" — `CircleTypes.BOTH` writes both triplets to admin-supplied
  coordinates, which is the nearest thing. `asyncio_triggers.schedule_update_event`
  is a ready-made sleep-then-trigger helper that nothing calls.
- **`reset_game` already exists** (`admin_interface.py:1918`) and does most of
  §4.5 — but it also **clears the reference photos** and `keep_weapons=False`
  hands out a Pewster (damage 1) where a fresh player has none (damage 0).
  §4.5 needs its own action, not that button.
- **Revocation is greenfield.** No deny-list, no expiry, no batch, and
  `Item.game_id` is assigned at first scan, so nothing server-side exists for
  a code before somebody scans it. Rotating `SECRET_KEY` kills the team cards
  too. Note that `reset_game` deleting `Item` rows *re-arms* a once-only code,
  since the duplicate check is row existence.
- **No team leader concept exists** on `User` or `Team`.
- **`Game` has no venue**; `ACTIVE_VENUE` is a module global and
  `main.py` builds the `Landmark` enum from it at import time.

---

## Two things that are not code, and must not be forgotten

- **Resize the droplet before Saturday.** Live runs on a very small
  DigitalOcean droplet, sized for sign-ups, not for thirty phones posting a
  fix every five seconds, the vision pipeline draining a queue, and the
  spectator screen. Resize it on **Friday 18 Sept**: take a DO snapshot
  first, power off, resize (CPU and RAM only — a disk resize cannot be
  undone), power on, and check `/api/get_version` and the admin page come
  back. `/data` is on the root disk and survives a resize. It is in the
  runbook (M9) as a Friday step, and it is here so it is not lost when M9 is
  written.
- **Back up `/data` before every live deploy** (`docs/deployment_droplet.md`,
  "State and backups"): thirty seconds, and it makes everything below
  reversible.

---

## M0.0 — The schema compatibility gate *(top priority; before any code PR lands)*

The live database cannot be migrated by hand in the time available, and
`database.add_missing_columns()` only migrates one shape of change (rule 2).
Nothing today catches a PR that writes the other shape — a rename, a drop, a
type change, a `NOT NULL` column with no scalar default — before it is
deployed and crash-loops the service. So make CI the gate:

1. **Snapshot the live schema.** Live runs revision `b50fe89`
   (`/api/get_version`, 16 Sept), and its database was created by
   `create_all()` from that revision's models after the R15 wipe, so the
   schema is reproducible here: build a sqlite file from `b50fe89`'s
   `backend/model.py`, dump `.schema` (no data) to
   `tests/live_schema/2026-09-16_b50fe89.sql`, and commit it.
2. **Test the upgrade.** A test in `tests/test_database.py` that creates a
   database from that snapshot, runs `create_all()` and
   `add_missing_columns()` against the *current* models, then inserts and
   reads back a row through every ORM class. A rename, a drop, or an
   undefaulted `NOT NULL` column fails this test on the pull request.
3. **Refresh the snapshot when live moves**, in the deploy PR or straight
   after: the file name carries the revision, so a stale snapshot is visible.

Lands in: `tests/live_schema/`, `tests/test_database.py`. Status: open.

---

## M0 — The print freeze *(deadline: Thursday 17 Sept, morning)*

Everything that has to be true before the printer runs. Merge these first;
they are all small. **Then deploy live** — not because the paper needs it
(rule 4) but because the Printables page mints with the live secret by
construction, and the weapon table has to be live by Saturday anyway.

Print-day procedure, once M0 is merged and deployed: mint everything from
`/admin/printables` on the **live** deployment (or the CLIs with the live
`SECRET_KEY` and `WEBSITE_URL` exported and `DATABASE_URL` pointed at a
throwaway sqlite file). Print at actual size, never "fit to page". A second
press mints a second set.

### M0.1 — The new weapon table *(status: open)*

Default cooldown 25 s, fast weapon 5 s. One PR:

- One `DEFAULT_SHOT_TIMEOUT = 25` — converge `model.py:27` (int) and
  `user_interface.py:53` (float) on the model's; keep `DEFAULT_SHOT_DAMAGE = 0`
  (a fresh sign-up has no weapon).
- Add `BASIC_WEAPON = (1, DEFAULT_SHOT_TIMEOUT)` — the Pewster — as the thing
  §4.5's reset hands out (M2.1 uses it) and `STARTING_HIT_POINTS = 2` beside
  it (M1.2 uses it; defining both now keeps M1 and M2 from colliding).
- `WEAPON_NAME_LOOKUP` (`item_actions.py:13-19`): `(1,5)` Eat-a-bullet,
  `(0,25)` No weapon, `(1,25)` Pewster, `(2,25)` Tracka-Tracka, `(3,25)` OMG.
  Mirror in `react-ui/src/weapons.js`, the gun art map in `utils.js:92-96`,
  and the admin's weapon select (`main.py:629-639` derives it, so check).
- Generator defaults: `generate_qr_items.py --timeout`, `printables.py`
  `timeout: float = 6`, the `/admin_item_sheets_pdf` route default, and
  `AdminPrintables.js`'s item-sheet controls.
- `FireButton.test.js` and any test naming 6 or 1.
- **Do not** touch `Shot.shot_timeout`'s history; old shots keep their value.

Lands in: `backend/model.py`, `backend/user_interface.py`,
`backend/item_actions.py`, `backend/generate_qr_items.py`,
`backend/printables.py`, `backend/main.py`, `react-ui/src/weapons.js`,
`react-ui/src/utils.js`, `react-ui/src/AdminPrintables.js`.

### M0.2 — Pub poster: five bullets *(status: open)*

- `BULLETS_PER_TEAM_MEMBER = 5` (`generate_pub_pages.py:52`), the module
  docstring, `AdminPrintables.js:196`'s `useState(2)`, the three literal 2s in
  `tests/test_generate_pub_pages.py:98-105`, `tests/test_printables.py:53`,
  `AdminPrintables.test.js:48-55`.
- **The artwork.** Paint over the "2x" in `reusable bullets.png` and write
  "5x" — legible from a bar, in purple, in something as close to the hand as
  a session can manage; Charles can redraw it in his own hand tomorrow if he
  has time, and this is the fallback that prints either way. Do not touch the
  QR pocket (`QR_POCKET`, re-measured by `test_qr_pocket_is_free_of_artwork`).
  Optionally add three more bullets to the drawing; optional.
- Count to print: 19 pubs are on the venue and The Speaker is one of them
  (its poster is handed to the bar to keep hidden until 16:00). Print 22.

Lands in: `backend/generate_pub_pages.py`, `backend/image_templates/`,
`react-ui/src/AdminPrintables.js`, tests.

### M0.3 — Freeze the QR item encoding *(status: open)*

The one PR that decides what the cards printed tomorrow *say*. Three
additions to `items.ItemModel`, all optional, all excluded from the
signature at their default (rule 5), with a test that an old payload still
validates byte-for-byte:

1. **`batch: Optional[str] = None`** — a label minted into the payload so a
   set of codes can be withdrawn together (M2.2). The sandbox posters are
   minted `batch="sandbox"`; the real drop cards, envelopes and pub posters
   `batch="game"`. Plumb it through `make_new_item`, both generators, both
   Printables endpoints (a text field on each panel, defaulting to `game`)
   and the `qr_codes.csv` line.
2. **`unlimited: bool = False`** — scannable any number of times by the same
   player. Today `collected_only_once=False, collected_as_team=False` still
   blocks a player's second scan of the same code
   (`user_interface.collect_item:881-896`), so a sandbox poster of "unlimited
   ammunition" is impossible without it. `collect_item` skips the duplicate
   check when set. Real codes never set it.
3. **Two new `ItemType` members, `RADAR` and `CIRCLE_WARNING`**, with their
   data schemas (`ITEM_TYPE_VALIDATORS`): `{"minutes": int}` for both,
   defaults 5 and 10. Their **handlers are M6** and may land after the print;
   until then `do_item_actions` raises `NotImplementedError` → 403, which is
   the existing behaviour for an unmapped type. The generators and the
   Printables item-sheet panel must be able to mint them (a card template is
   needed: `image_templates/radar_1.png` and `circle_warning_1.png` — reuse
   a drawn template with a text label if no artwork arrives from Charles).

Lands in: `backend/items.py`, `backend/model.py` (`ItemType`),
`backend/user_interface.py`, `backend/admin_interface.py`
(`make_new_item`), `backend/generate_qr_items.py`, `backend/printables.py`,
`backend/main.py`, `react-ui/src/AdminPrintables.js`, `NewItems.js`,
`tests/test_items.py`.

### M0.4 — The sandbox posters *(status: open; after M0.3)*

What the warm-up room's walls carry, and a way to mint them in one press:

- A **"Sandbox sheet"** in the Printables page (or a `--sandbox` mode of the
  drop-card generator): ammo ×20 `unlimited`, armour level 2 `unlimited`
  (re-scannable after losing it), Pewster + Eat-a-bullet + Tracka-Tracka
  weapons `unlimited`, medpack `unlimited` — all `batch="sandbox"`, on the
  existing 8-per-sheet A4 landscape cards so they are big enough to read
  across a room. Several copies of each.
- Note in the runbook (M9) that these are revoked at 16:00 (M2.2).

### M0.5 — The drop-card contact line *(status: open; small)*

Roadmap #7's mitigation, never built: every drop card and envelope carries
"This is part of a game — ring <number>" so a stranger who finds one gets an
answer rather than a fright. Drawn text on the card in `generate_qr_items.py`
(the artwork is a PNG with a QR pocket, same shape as the pub page); the
number is a module constant Charles fills in. Verify the sheets still pass
`tests/test_generate_qr_items.py`.

### M0.6 — Redraw the map against the nineteen pubs *(status: references and prompt ready 17 Sept, PR #PRNUM; the drawing itself still needs Charles's Gemini round-trip)*

Roadmap #12, reopened 12 Sept: eleven of the nineteen pubs have no marker.
Now print-critical, because the poster (M0.7) is this image. Rerun the
`draw-venue-map` skill's pipeline with the same 1300 × 1300 m frame centred
on House Absolute — the reference points are the crop corners, so a new
image drops in with no georeferencing work. **Trace, do not illustrate**, and
do not ask the good result for small corrections (see #12 for both lessons).

Sequence: a session regenerates the skeleton and `prompt.md` for the new
list tonight → Charles runs the prompt at Gemini → the session checks the
result with `scripts/check_venue_map.py` and wires it in
(`react-ui/src/images/map_westminster.jpg`, `tests/test_venues.py`). Fixing
the two known label errors ("Great Peter Street" for Great Smith Street; The
Speaker's own street unlabelled) is welcome if the trace gives it for free.

**The first half is done.** `docs/venue_map_westminster/` holds the bundle —
the prompt with all nineteen pubs in it, the four reference images, and a
`README.md` saying exactly what to attach and what to look at when the
drawing comes back. The pubs were passed to the builder by hand
(`build.sh`, the new `--pub` flag) rather than searched for, so the skeleton
marks Charles's nineteen and not the nineteen nearest. Both known label
errors come out right on the new skeleton, so the trace gets them for free.
**Outstanding: run `prompt.md` at Gemini and hand back the image.**

### M0.7 — A printable map poster *(status: open; new)*

A PDF of the map to pin up in The Speaker: the venue image at A3 (and A4)
with a numbered legend of the nineteen pubs and House Absolute, the game's
name and date, and **no circles, no drop locations, no courier** — it is on a
wall players read. Same toolchain as `team_cards.py` (Pillow, `make_qr`'s
`DPI` and `_mm`, `UbuntuMono-R.ttf`), built from `ACTIVE_VENUE` so the legend
cannot drift from `venues.py`. `GET /admin_map_poster_pdf` (GET, since it
mints nothing) and a panel on the Printables page; a CLI entry too
(`npm run mapgen`). Reads the image from `react-ui/src/images/` via
`mapImages.js`'s key — on a deployment the source tree is a read-only Nix
store path, which is readable. Test: one page, A3 portrait or landscape to
suit the square, legend names match the venue's landmark keys.

---

## M1 — Balance and the server-side cooldown *(by Thursday night; on staging Friday)*

### M1.1 — Enforce the cooldown on the server *(status: open; the plan's one "assume they will try to break it")*

- `User.last_shot_at: Float, nullable` (additive) written in `submit_shot`
  beside the bullet decrement — not derived from `Shot.time_created`, which
  is a `DateTime` with 1 s resolution and is deleted by resets.
- `submit_shot` refuses a shot earlier than `shot_timeout` after it with a
  403 whose `detail` says how long is left. Enforced **before** the photo is
  stored and the bullet spent. Small tolerance (0.5 s) for clock skew is fine;
  a refresh must not help.
- `UserModel` carries `next_shot_at` (derived, epoch seconds) so the frontend
  derives the cooldown from the server: `FireButton.js` counts down to it
  rather than its own `setTimeout`, so a reload comes back still cooling.
- `MyWebcam.js` checks `response.ok` and surfaces the refusal (the r9 A4
  finding) — a silent 403 would look like the app eating shots.
- Tests: TDD in `tests/test_shots.py` (three back-to-back shots → 200, 403,
  403; after the timeout → 200; the fast weapon's 5 s) and `FireButton.test.js`.

### M1.2 — Starting armour *(status: open; small, after M0.1)*

`STARTING_HIT_POINTS` (2) in `_make_user`, the reset (M2.1), and
`demo_game`'s arming (which deliberately gives one HP so a hit kills — keep
that, it is the demo's own decision). Players already signed up on live have
`hit_points = 1`; the reset at 16:00 sets everyone to 2, so no data fix is
needed. Check `BulletCount.js`'s armour pips render two.

---

## M2 — The 16:00 transition *(by Friday)*

### M2.1 — Reset to start state *(status: open)*

One `AdminInterface.reset_to_start_state(game_id)` and one big button in
`GamePanel`, **refusing unless the game is paused** (say so in the code: the
friction is deliberate). For every player with that `game_id` — team-less
sign-ups included, which `reset_game`'s team walk misses:

- `num_bullets = 0`, `hit_points = STARTING_HIT_POINTS`, `time_of_death =
  None`, weapon = `BASIC_WEAPON`, `appeals_remaining = APPEALS_PER_GAME`,
  `last_shot_at = None`;
- delete their shots (and so the queue), the game's ticker, and the game's
  `Item` rows (the sandbox batch is withdrawn separately, so re-arming is
  harmless; the real codes have not been scanned yet);
- clear all three circles and any cued event (M3);
- **keep** reference photos, identity, teams, locations, leaders.

Existing `reset_game` stays for dev. Tests in `tests/test_admin_mode.py`.
Two-tap confirm on the button, like the demo button.

### M2.2 — Withdraw a batch of codes *(status: open; after M0.3)*

- New table `revoked_batches(batch TEXT PK, revoked_at)` — a new table, so it
  creates itself on deploy (rule 2).
- `collect_item` checks it right after the signature and returns 403 "This
  code has been withdrawn" (the scanner already plays `error.mp3` and flashes
  red on a 403).
- Admin: on the Printables page, a "Withdraw codes" panel: text field
  (default `sandbox`), the list of withdrawn batches, and an un-withdraw.
- Tests: a withdrawn code 403s, an unbatched legacy code is unaffected.

---

## M3 — Countdown and announcements *(by Friday; the biggest player-facing change)*

### M3.1 — "What happens next" on every phone *(status: open)*

- `Game.next_event_kind` (`"circle"` / `"drop"`), `next_event_at` (epoch
  float), `next_event_note` (the drop's contents, admin-typed) — three
  nullable columns (rule 2). Carried on `UserModel` via `user_info` so the
  existing `"user"` SSE refetch picks it up; changing them fans out
  `trigger_update_event("user", …)` to the game's players exactly as
  `set_game_active` does.
- A persistent strip at the top of `UserMode.js` above `monitorsContainer`,
  reusing `GuideImages.js`'s `CountdownTimer`: "Circle closes in 07:12" /
  "Drop in 04:30 — 2× level 2 armour, a Tracka-Tracka, a medpack". Prose in
  `prose.js`. Shown on the waiting page too. Nothing when nothing is cued.
- Spectator screen shows the same (nice-to-have).

### M3.2 — Cue the next circle *(status: open)*

- Admin places the NEXT circle as today (`CircleControl.js`), then **"Close
  the circle in N minutes"** (default 10) → sets `next_event_*`, ticker
  announces, countdown appears. A "Cancel" clears it.
- At zero: **`promote_next_circle(game_id)`** copies `next_*` into
  `exclusion_*`, clears `next_*` and the cue, announces in the ticker, fires
  the circle event. New `AdminInterface` method with its own test.
- The timer is an in-process asyncio task (the `schedule_update_event` shape,
  or `demo_game`'s task pattern) **and** a startup sweep that re-arms every
  game with a `next_event_at` in the future and fires any already past — a
  restart mid-countdown must not lose the close. Guard against double-firing.

### M3.3 — Cue a drop *(status: open)*

**"Drop in N minutes"** (default 5) with a contents field → `next_event_*`
with the note. At zero: ticker "The courier has set off", cue cleared, and
the courier phase (M4) begins. Nothing on the map until the courier
broadcasts.

---

## M4 — Live drops: the courier *(by Friday; after M3.1's columns)*

### M4.1 — The courier page *(status: open)*

`/admin/courier` (`AdminPage`, nav link), phone-first, three things on it:

- **Broadcast my location** — `watchPosition` at `MapViewSelf`'s EXPANDED
  tier (1 s, high accuracy) posting to `POST /admin_set_courier_location
  (game_id, lat, long, accuracy)` → `Game.courier_lat/long/timestamp`
  (nullable, additive). Throttle the SSE fan-out to ~5 s; a courier fix is
  not a shot.
- **Place drop here** — sets the DROP circle at the current fix through the
  existing `set_circles` (so the ticker and circle event fire as today),
  clears the courier position, and stops broadcasting. Two-tap confirm.
- **Stop broadcasting** without placing.
- Status in words: "Broadcasting — last fix 2 s ago, ±8 m" / "Not
  broadcasting". Holds the wake lock (`useWakeLock.js`).

### M4.2 — The courier and the crate on every map *(status: open)*

- `/get_circles` grows `courier: {lat, long, timestamp} | null`; the
  `"circle"` SSE event is fired (throttled) when the courier moves, so
  `MapCirclesFromAPI`'s existing listener refetches.
- `Dot.js` takes an optional `src`; the courier is drawn with a new image
  (**input needed from Charles/Gaby: her face in an aeroplane**, else a drawn
  placeholder in `images/art/`), and the drop circle gets a **crate icon** at
  its centre alongside the existing blue ping (`MapView.module.css`
  `.dropCircle`). Fade the courier dot with fix age like the admin map does.
- Same on `MapViewAdmin` and the spectator screen.

---

## M5 — Sounds *(any time before Friday; independent)*

- **Replace `bang.mp3`** with a sci-fi "pew" (synthesise with numpy → `wave`
  like the `.wav`s were; the file is dropped over the old one, no code).
- **Knocked out** (target): a new sound in `UserMode.js` when `user.state`
  becomes `"knocked out"` — seeded silently on mount so a reload replays
  nothing, same discipline as `useShotOutcomeSounds`.
- **You knocked someone out** (shooter): `get_own_shots` carries
  `target_knocked_out: bool` on a checked hit; `useShotOutcomeSounds` plays a
  distinct sound for it.
- **"You have been shot" must cut through a pocket**: make `hit_received.wav`
  longer and louder (2–3 s, full scale), keep the vibration pattern.
- **Unlock audio on first tap.** Howler auto-unlocks on the first gesture but
  only if a sound *object* exists by then; add a one-line `Howler.ctx`
  resume on the first `pointerdown` in `UserMode.js` (or preload every sound
  on mount) and test on an iPhone on staging. The onboarding page's
  permission steps are the natural place to say "sound on".
- Sounds already present and kept: fire, hit received, your hit, your miss.

---

## M6 — The two experimental items *(Friday; after M0.3; drop if not working)*

### M6.1 — Radar *(status: open)*

- Handler: `User.radar_until = now + minutes*60` (nullable column). Refuses
  if already active.
- `GET /radar` (player-authenticated): while active, every other player in
  the game as `{name, team, lat, long, seconds_ago, accuracy, state}`;
  otherwise 403. Reuse `AdminInterface.get_locations`.
- Map: dots for everyone with a **"last seen 3 min ago"** label — the plan is
  explicit that this is last-seen, never live — greyed as the fix ages, and a
  strip "Radar: 4:12 left". Polls every 5 s while active (the admin map's
  pattern); no SSE needed.

### M6.2 — Early circle warning *(status: open)*

Reveals the next circle to the holder before it is announced. That needs a
circle that exists but is not public: add `Game.next_circle_public: Boolean
default False`. Placing NEXT no longer announces or draws it for players
until the admin **cues** it (M3.2), which sets it public; a holder with
`User.circle_warning_until` in the future sees it before that (filtered in
`get_circles`). Ticker says only "somebody knows where the next circle is".
The admin map always shows it.

---

## M7 — Team leader view *(Thursday/Friday; small, independent)*

- `User.is_team_leader: Boolean default False` (additive). A toggle on the
  admin roster row (`AdminMode.js` `PlayerRow`).
- A "Team leader" panel on the waiting page (`OnboardingView.js`) and, once
  running, behind a button in user mode: the checklist of what "properly
  equipped" means, from `prose.js`. **Input needed from Charles:** the
  checklist itself; a first draft — everyone on the team has the app open
  with camera and location allowed; everyone has scanned the team card; hat
  and armband on and matching the app; reference photo taken; knows the
  cooldown and the pub rule.
- `UserModel.is_team_leader`.

---

## M8 — The annotated admin map *(needs Charles's annotated map)*

Charles and Gaby's marked-up map gives approximate circle centres and rough
drop areas. Add them to the Westminster venue as landmarks — `CIRCLE1`…`4`
and `DROP_*`, exactly as Kingston has (`venues.py:135-145`) — so
`CircleControl.js`'s landmark dropdown offers them and the radius hint at its
foot reads Westminster's radii rather than Kingston's. The repo is public and
this publishes them; that trade was accepted in the roadmap's decisions.
Admin-only in the UI; the drop landmarks are *areas Gaby aims for*, not
where she will stand.

---

## M9 — The game-day runbook and the paper trail *(Friday)*

`docs/game_day_runbook_2026-09-19.md`: the plan's §5 as a checklist with the
button behind each step named — pause, **Reset to start state**, **Withdraw
`sandbox`**, ten minutes, WhatsApp, start; the circle and drop cues; the
courier page; what to do when a countdown fires while the server is
restarting. Plus the Thursday print list with counts, and the **Friday
droplet resize** (snapshot, power off, resize CPU/RAM, power on, verify) —
see the reminder at the top of this file. Update `docs/roadmap.md`
(#12 shipped, #8's print run) and `CLAUDE.md` for anything that moved.

---

## Order and parallelism

| Session | Scope | Blocks |
| --- | --- | --- |
| 0 | M0.0 schema gate, first and alone | every code PR |
| A | M0.1 then M1.1, M1.2 (same files) | M2.1 (constants) |
| B | M0.2 | — |
| C | M0.3 then M0.4, M2.2, M0.5 | M6 |
| D | M0.6 skeleton + prompt tonight; M0.7 poster meanwhile; wire the drawing when it comes back | print |
| E | M3.1, M3.2, M3.3 then M4.1, M4.2 | — |
| F | M5 | — |
| G | M2.1 (after A's constants merge), then M7 | — |
| H | M6.1, M6.2 (after C's M0.3 merges) | — |
| — | M8 and M9 once the inputs arrive | — |

**Inputs needed from Charles**, none of which block the code: the Gemini
round-trip for the map (M0.6); the phone number for the cards (M0.5); Gaby's
aeroplane image (M4.2, placeholder otherwise); the leader checklist (M7); the
annotated map (M8).

## Deliberately not built

- **Scheduling circles and drops in advance.** The plan keeps timing under
  admin control; a cue is a countdown from *now*, not a timetable.
- **Anything that moves a player's identity or team.** Frozen.
- **Push notifications** (roadmap R4). The countdown strip and the sounds are
  the in-app substitute; a backgrounded phone still gets nothing, and that is
  accepted for this run.
