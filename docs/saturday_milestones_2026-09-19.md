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

**This is the code as it stood on 16 September, and most of it has since been
fixed — it is kept as the record of what each milestone was answering, not as
a description of the code.** Superseded by: M0.1 (the cooldown numbers and the
weapon table), M0.2 (the pub poster's "2x"), M1.1 (nothing enforced the
cooldown server-side; `MyWebcam.js` ignoring `response.ok`), M1.2 (starting
armour), M2.1 (`reset_game` was the only reset), M2.2 (revocation was
greenfield), M3 (nothing was timed), M4 (players could see nobody on the map —
the courier is the first player-facing position of anybody else), M7 (no team
leader concept). Still true as written: `Game` has no venue.

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
  starting `hit_points` of 2 — which since M1.2 is what everybody has, so a
  **level-1 armour card is now a no-op for anybody who has not been hit**.
  Mint level 2 or better.
- **A medpack only works on a knocked-out player** and revives to 1 HP
  (`item_actions._handle_medpack`). Knocked out lasts `TIME_KNOCKED_OUT` (10
  min) and then becomes dead, which no item cures. Fine for the sandbox's
  "revive yourself immediately"; the reset (M2.1) covers the rest.
- **The pub poster says "2x bullets" in Charles's handwriting**, inside the
  artwork PNG (`backend/image_templates/reusable bullets.png`), with two
  bullets drawn. The constant is `generate_pub_pages.BULLETS_PER_TEAM_MEMBER`
  and three tests hard-code the literal 2. Changing the number is an image
  edit as well as a code change.
- **The cooldown was enforced nowhere on the server** — fixed by M1.1.
  `submit_shot` checked team, HP and bullets only; the only timer was
  `FireButton.js`'s `setTimeout`, so three back-to-back POSTs all returned 200
  (`docs/r9_walkthrough/A4.md`), and `MyWebcam.js` never checked `response.ok`,
  so a server refusal would have been silent.
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

## Three things that are not code, and must not be forgotten

- **Put the circle and drop coordinates in the live env file, before the
  game.** *Critical: without it the circle plan has nothing to arm, and the
  early-warning cards are worth nothing.* The numbers off Charles and Gaby's
  marked-up map are deliberately not in this repository, which is public:
  they go in `/data/secrets/streetfight.env` on the droplet as
  `LANDMARK_CIRCLE0=51.4958,-0.1309` and so on, one line each, and the
  service is restarted (the file is read at startup). **All four of
  `CIRCLE0`…`CIRCLE3` are needed** — they are what `circles.CIRCLE_PLAN`
  arms in turn, which is what stops an admin having to remember to place
  NEXT (M8). The `DROP_*` ones go in the same way and are optional: they only
  fill the landmark dropdown. **Each circle's radius goes in the same file**,
  as `CIRCLE_RADIUS_CIRCLE0=0.70` and so on (0.42, 0.18, 0.05 km) - how big
  the last circle is gives away as much as where it is, so neither half is in
  the repository. Check it took: the admin page's **Circles**
  panel should say `Plan: CIRCLE0 (0.7 km)` with coordinates, not "no
  coordinates — place it by hand" or "no radius — place it by hand". Do it **before Saturday afternoon**, and
  ideally on staging first.
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

Lands in: `tests/live_schema/`, `tests/test_database.py`.
*(status: shipped 2026-09-17, PR #255)*

Shipped as `TestLiveSchemaUpgrade` in `tests/test_database.py`, with two
tests rather than one. The second is the specified insert-and-read-back
through every mapped class (and it fails by name if a new ORM class has no
row, so the coverage cannot quietly rot). The first is the one that does most
of the work: it compares the upgraded database against a database built fresh
from the current models, column by column, which is what actually catches a
rename or a drop — a dropped *nullable* column leaves the ORM perfectly able
to write a row, so writing one proves nothing. It catches a type change too,
which the write does not, since sqlite barely has types. An undefaulted `NOT
NULL` column fails earlier still, inside `add_missing_columns`. All four
shapes were confirmed by throwaway edits to `model.py`, and both permitted
shapes (a nullable column, a scalar-defaulted `NOT NULL` one) confirmed to
pass.

Refreshing the snapshot is a script rather than a recipe:
`python tests/live_schema/refresh.py <rev>` loads that revision's
`backend/model.py` on its own, runs `create_all()` into a throwaway sqlite
file and writes `tests/live_schema/<today>_<rev7>.sql`. Delete the file it
replaces and point `TestLiveSchemaUpgrade.SNAPSHOT` at the new one.

Knowingly not covered: an index added to an existing table, which
`create_all()` also fails to apply to live. It costs speed rather than
correctness, and nothing here could tell an intended new index from an
accident.

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

### M0.1 — The new weapon table *(status: shipped 2026-09-17, PR #257)*

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

Shipped as specified. `WEAPON_NAME_LOOKUP`'s pairs stayed written out as
literals rather than built from `DEFAULT_SHOT_TIMEOUT`, because
`react-ui/src/weapons.test.js` reads them straight out of the file to catch
the frontend mirror drifting; `tests/test_items.py` now pins `BASIC_WEAPON`
to the Pewster instead, so the two cannot separate silently.

Lands in: `backend/model.py`, `backend/user_interface.py`,
`backend/item_actions.py`, `backend/generate_qr_items.py`,
`backend/printables.py`, `backend/main.py`, `react-ui/src/weapons.js`,
`react-ui/src/utils.js`, `react-ui/src/AdminPrintables.js`.

### M0.2 — Pub poster: five bullets *(status: shipped 17 Sept, PR #254)*

The artwork's "2x" was erased and "5x" redrawn with Pillow in the same
purple (`#8103D0`) and pen weight; the bullets are still drawn twice, since
adding three more convincingly is more than a Pillow paint-over. Charles can
redraw the line in his own hand over the top of this.

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

### M0.3 — Freeze the QR item encoding *(status: shipped 2026-09-17, PR #259)*

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

### M0.4 — The sandbox posters *(status: shipped 2026-09-17, PR #263; re-shaped as one-per-page INFINITE posters 2026-09-17)*

What the warm-up room's walls carry, and a way to mint them in one press:

- A **"Sandbox sheet"** in the Printables page (or a `--sandbox` mode of the
  drop-card generator): ammo ×20 `unlimited`, armour level 2 `unlimited`
  (re-scannable after losing it), Pewster + Eat-a-bullet + Tracka-Tracka
  weapons `unlimited`, medpack `unlimited` — all `batch="sandbox"`, on the
  existing 8-per-sheet A4 landscape cards so they are big enough to read
  across a room. Several copies of each.
- Note in the runbook (M9) that these are revoked at 16:00 (M2.2).

Shipped as a **Sandbox posters** panel on the Printables page
(`printables.SANDBOX_CARDS`, `POST /admin_sandbox_sheets_pdf`): one portrait
A4 page per kind, `copies` of each, every code `unlimited` and
`batch="sandbox"`. It printed a sheet of eight per kind to begin with, which
was eight copies of one unlimited code and, carrying the drop cards' own
artwork, indistinguishable from a sheet to be cut up and hidden — so it is now
one page per code, headed **INFINITE** (`printables.infinite_poster`).
Two deviations from the list above, both because a card's drawing is chosen by
what it awards and a poster read across a room has to say what it is:

- **Ammunition is 5 bullets, not 20** — there is an `ammo_5.png` and no
  `ammo_20.png`, and being unlimited, five a scan is no less than twenty.
- **Eat-a-bullet had no drawing of its own.** It shared `weapon_1.png` with
  Pewster, so its poster read "Pewster / Damage: 1"; keying the artwork on the
  (damage, delay) pair fixed the wrong name but left it printing as a bare QR
  code. It has `weapon_1_5.png` now, composited from what the pack already
  held — the card frame every other card shares, recoloured teal; the gun the
  player's HUD draws for (1, 5), which carries the name in its own lettering;
  and Pewster's "Damage: 1", which is true of this weapon too. Plus the one
  thing that is genuinely new: a **RAPID FIRE** flash in the bottom-right
  corner, since the 5 s cooldown is the whole difference between this weapon
  and Pewster and nothing else on the card says it. The frame is teal rather
  than the red the gun's own crest suggests, because the flash is hot pink.

**For M9's runbook:** the sandbox posters are withdrawn by withdrawing the
`sandbox` batch at 16:00.

### M0.5 — The drop-card contact line *(status: shipped 2026-09-17, PR #262; **removed again 2026-09-17** at Charles's request)*

Roadmap #7's mitigation, never built: every drop card and envelope carries
"This is part of a game — ring <number>" so a stranger who finds one gets an
answer rather than a fright. Drawn text on the card in `generate_qr_items.py`
(the artwork is a PNG with a QR pocket, same shape as the pub page); the
number is a module constant Charles fills in. Verify the sheets still pass
`tests/test_generate_qr_items.py`.

Shipped: the line is `CONTACT_LINE` in `generate_qr_items.py`, drawn by
`build_qr_grid` so the CLI and the Printables page both get it. It goes in a
strip below the artwork, not on it - the artwork gives up 70 px of height -
and keeps the full gutter between itself and the box edge, because the
bottom row of a sheet is against the edge of the paper. The envelopes need
nothing of their own: what is in them is these same cards.
`tests/test_generate_qr_items.py` did not exist and does now.

**Removed.** Charles asked for the line off the cards; the cards are the
artwork, the code and the run label again, and `tests/test_generate_qr_items.py`
has gone with it. The failure mode #7 named is unmitigated on paper: a stranger
who finds a card taped under a bench has nothing to read and nobody to ring.

### M0.6 — Redraw the map against the nineteen pubs *(status: shipped 17 Sept; rendered rather than generated, after every image model failed)*

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
**Re-cropped 17 Sept at Charles's request.** The crop was pinned to House
Absolute, which forced 1300 x 1300 m because Big Ben is 537 m north of it.
Nothing needs it centred, so the crop is now sized to the markers: centre at
the middle of the nineteen pubs and four landmarks, half-span 575 m, giving
1150 x 1150 m - a quarter less ground on the same paper, and within 3 m of
Kingston's 1153 m. House Absolute becomes an ordinary landmark and the centre
is an unlabelled crosshair (`--centre-label ""`, new in the skill's builder).
**`backend/venues.py`'s reference points move with the image**: 51.502881,
-0.139506 and 51.492481, -0.122912, to be applied only when the drawing lands,
along with a fresh look at `corner_width_km`.

**Shipped 17 Sept — by rendering it, not generating it.** Charles went round
every Gemini model and every image-output model on OpenRouter; each one got
either the roads or the scale wrong, because image models resynthesise rather
than trace and nothing in them preserves metric geometry. The geometry was
always in the OSM data the bundle already fetched, and a hand-drawn look is a
rendering style rather than a creative act, so
`.claude/skills/draw-venue-map/scripts/render_venue_map.py` now draws it:
wobbly two-edge road corridors, a handwriting font, curved arrows to each
name, outlined block capitals for the title. All nineteen pubs are labelled
because it labels whatever is in the venue's `landmarks`, so the map cannot
fall behind the list again. `venues.py` moved to the new image and crop
(2000 px, corners 51.502881/-0.139506 and 51.492481/-0.122912,
`corner_width_km` 0.13), and `tests/test_map_poster.py` was updated: it
asserted House Absolute was dead centre, which the re-crop deliberately ended.
**The map poster is unblocked.**

**Doodles, 18 Sept.** The rendered map was accurate and dull: none of the
little drawings that make the Kingston map. Those are the one thing an image
model *can* do — a doodle carries no geometry to get wrong — so
`doodle_venue_map.py` asks Gemini Flash for one small pen sketch per pub
(subjects in `docs/venue_map_westminster/doodles.json`: an oak for the Royal
Oak, a boar for the Blue Boar, a sedan chair for the Two Chairmen, a pelican
on the park, an eight on the river), converts black-on-white to transparent
sepia ink, and the renderer places each beside its pub in the emptiest paper,
never over a name. The model never sees the map.

### M0.7 — A printable map poster *(status: shipped 17 Sept, PR #272; unblocked 17 Sept when M0.6's map landed)*

A PDF of the map to pin up in The Speaker: the venue image at A3 (and A4)
with a numbered legend of the nineteen pubs and House Absolute, the game's
name and date, and **no circles, no drop locations, no courier** — it is on a
wall players read. Same toolchain as `team_cards.py` (Pillow, `make_qr`'s
`DPI` and `_mm`, `UbuntuMono-R.ttf`), built from `ACTIVE_VENUE` so the legend
cannot drift from `venues.py`. `GET /admin_map_poster_pdf` (GET, since it
mints nothing) and a panel on the Printables page; a CLI entry too
(`npm run mapgen`). Test: one page, A3 portrait or landscape to
suit the square, legend names match the venue's landmark keys.

**Shipped, and it differs from the spec in two places.**

- A3 *portrait* with the legend under the map, and A4 as the same design
  scaled — the two sizes share an aspect ratio, so there is one layout, not
  two. The paper is a query parameter, A3 by default.
- The poster **draws its own numbered markers** on the map. A numbered legend
  is unusable without numbers on the map, and the current drawing labels the
  ten pubs it was traced from rather than the nineteen in play. The numbering
  is the venue's own order, which is also the order M0.6's skeleton numbers
  them in, so when the redraw lands the poster's numbers and the drawing's
  agree.
- **Where the image comes from is not what this milestone assumed.** The
  deployed wheel is built from `backend*` alone (checked — there is no
  `react-ui` in it), so reading `react-ui/src/images/` would have worked in a
  checkout and failed on the droplet. `backend/map_images/<venue key>.<ext>`
  are symlinks to the one real file webpack bundles, shipped as package data.

**Held from printing** until M0.6's redrawn map is in: the poster is only as
good as the image, and eleven of the nineteen pubs are still unlabelled on
the drawing. Nothing has to change here when it lands — drop the new file
over `react-ui/src/images/map_westminster.jpg` and reprint.

---

## M1 — Balance and the server-side cooldown *(by Thursday night; on staging Friday)*

### M1.1 — Enforce the cooldown on the server *(status: shipped 2026-09-17, PR #266; the plan's one "assume they will try to break it")*

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

Shipped as specified, with two decisions worth knowing. A shot carrying its
own `time_created` is **exempt** from the cooldown: that argument is only ever
passed by the replay and the demo drip (`/api/submit_shot` passes neither, and
must not), which deal out a simulated hour's shots in whatever order suits
them. And the refusal reaches the player through a new
`shotRefusedStore` + `ShotRefusedNotice` rather than a callback threaded
through `WebcamView`, because the admin's reference-photo page mounts the same
camera and has no business showing a fire-cooldown message.

### M1.2 — Starting armour *(status: shipped 2026-09-17, PR #267)*

`STARTING_HIT_POINTS` (2) in `_make_user`, the reset (M2.1), and
`demo_game`'s arming (which deliberately gives one HP so a hit kills — keep
that, it is the demo's own decision). Players already signed up on live have
`hit_points = 1`; the reset at 16:00 sets everyone to 2, so no data fix is
needed. Check `BulletCount.js`'s armour pips render two.

Shipped in `_make_user` (the only place a `User` row is built) and in the
existing `reset_game`; `demo_game` sets its one HP explicitly, so it was
untouched. M2.1's new `reset_to_start_state` should use the same constant.

Two things the spec did not anticipate:

- **The pips render *one*, not two, and that is correct.** Armour is hit
  points above one, so `STARTING_HIT_POINTS = 2` is armour level 1 and
  `BulletCount.js`'s existing `hit_points - 1` draws one helmet. The visible
  change is that a fresh player sees a helmet where they used to see a cross.
- **A level-1 armour card is now worthless to anybody who has not been hit**
  (`item_actions._handle_armour` refuses armour no better than what you have).
  Everything being printed is level 2 (`printables.SANDBOX_CARDS`, and M3.1's
  drop copy), so no reprint is needed — but do not mint level-1 armour.
  `tests/test_items.py` pins this.

---

## M2 — The 16:00 transition *(by Friday)*

### M2.1 — Reset to start state *(status: shipped 2026-09-17, PR #268)*

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

Shipped as specified. `reset_to_start_state` sits directly before
`reset_game`, behind `POST /admin_reset_to_start_state`; the button is
`react-ui/src/ResetToStartButton.js`, mounted in `GamePanel` under the join
QR codes. Two notes on what shipped:

- **The two-tap is built as a self-arming button**, not copied from the demo
  button — that button turned out to have no confirm at all, just a plain
  press and a server-side refusal. The first tap arms it and makes it say
  "Tap again to wipe the sandbox"; it disarms itself after six seconds.
- Shots are deleted **by `game_id` rather than by shooter**, so a shot
  outlives the team its shooter was in and the queue empties whoever is left
  in it. The circles are nulled straight onto the columns rather than through
  `set_circles`, which would announce three changes to a ticker this is about
  to delete anyway.

### M2.2 — Withdraw a batch of codes *(status: shipped 2026-09-17, PR #265)*

- New table `revoked_batches(batch TEXT PK, revoked_at)` — a new table, so it
  creates itself on deploy (rule 2).
- `collect_item` checks it right after the signature and returns 403 "This
  code has been withdrawn" (the scanner already plays `error.mp3` and flashes
  red on a 403).
- Admin: on the Printables page, a "Withdraw codes" panel: text field
  (default `sandbox`), the list of withdrawn batches, and an un-withdraw.
- Tests: a withdrawn code 403s, an unbatched legacy code is unaffected.

Shipped as specified. Two things worth knowing at 16:00: the check sits
*before* anything about the player is looked at, so a withdrawn card is dead
for everybody and the answer never depends on who scanned it; and the panel's
button names the batch it is about to withdraw ("Withdraw \"sandbox\""), with a
red warning for any batch that is not the sandbox, because mistyping `game`
there would turn off every card in the town. One press rather than two, since
**Allow again** is in the list directly beneath it.

### M2.3 — Switch off one code *(status: shipped 2026-09-18)*

The infinite sandbox posters work, and a batch is the wrong granularity for
the one that walks out of the warm-up room in somebody's pocket. New table
`known_codes(id PK, first_seen, enabled, item_type, data, batch, unlimited,
collected_as_team)` — a new table, so it creates itself on deploy (rule 2).

The shape follows from the cryptography rather than from taste: a code is an
HMAC over its payload and nothing else, so the server cannot enumerate what
was printed, there is no list to pick from, and **absence has to mean
collectable**. A code therefore has to be *scanned back in* before it can be
switched off, which is what the new **Item codes** admin page
(`/admin/codes`) is for — the player's own scan loop (`useQRScanLoop.js`,
lifted out of `QRParser.js`) pointed at a different sink, plus a paste field
for a code copied out of `qr_codes.csv`. Registering a code does not collect
it. `collect_item` asks the same question it asks of batches, in the same
place and for the same reason.

---

## M3 — Countdown and announcements *(by Friday; the biggest player-facing change)*

### M3.1 — "What happens next" on every phone *(status: shipped 2026-09-17, PR #258)*

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

Shipped as the carriage only: the columns, the ride out on `UserModel`, the
strip and the spectator screen's pill. Nothing sets the columns yet, so the
`trigger_update_event("user", …)` fan-out lands with the setter that needs it
(`cue_next_event`, M3.2) rather than here. The kind strings live in a new
`backend/next_event.py`, which is where M3.2's timer goes. The strip sits above
the waiting page too, and reads the cue off `User.game` rather than the team's,
so a signed-up player with no team still sees it.

### M3.2 — Cue the next circle *(status: shipped 2026-09-17, PR #269)*

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

Shipped with the cue setter generic over both kinds (`cue_next_event(game_id,
kind, seconds, note)`), so M3.3 is the drop's *behaviour at zero* and its bit
of UI rather than a second setter. The drop branch of `fire_next_event`
currently only clears the cue. Double-firing is guarded twice: arming cancels
the game's pending task, and `fire_next_event` re-reads the deadline and
refuses one it does not recognise — the half that survives a restart. The
timer tests live in `tests/test_next_event.py` rather than
`tests/test_asyncio_triggers.py`, since the timer is in `next_event.py` and
not in the trigger registry. **Decision worth revisiting:**
`promote_next_circle` changes nothing but the cue when NEXT is empty, rather
than blanking the exclusion circle.

### M3.3 — Cue a drop *(status: shipped 2026-09-17, PR #271)*

**"Drop in N minutes"** (default 5) with a contents field → `next_event_*`
with the note. At zero: ticker "The courier has set off", cue cleared, and
the courier phase (M4) begins. Nothing on the map until the courier
broadcasts.

Most of this arrived with M3.2, whose cue setter is generic over both kinds,
so what shipped here is the drop's behaviour at zero: the ticker line, and
nothing else placed. The cue announcement also carries the contents when the
admin typed any (`CUE_DROP_WITH_CONTENTS`), since the ticker is read by people
who are not looking at the strip. One line lands outside the item:
`reset_to_start_state` (M2.1) now disarms the pending timer along with the cue
columns it already cleared.

---

## M4 — Live drops: the courier *(by Friday; after M3.1's columns)*

### M4.1 — The courier page *(status: shipped 2026-09-17, PR #273)*

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

Shipped as specified. `backend/admin_interface.py` gains
`set_courier_location` / `clear_courier` directly before `set_circles`, with
`POST /admin_set_courier_location` and `/admin_clear_courier` before the
`admin_set_circle` route; the page is `react-ui/src/AdminCourier.js`. Three
notes:

- **A fourth column, `courier_accuracy`.** The route's signature in this
  section takes `accuracy`, and accepting a parameter and dropping it on the
  floor is worse than a nullable column. Captured, consumed by nothing yet -
  the same standing as `User.location_accuracy` and `Shot.heading`. M4.2 is
  free to size the dot by it or ignore it.
- **The throttle is leading-edge and server-side.** Every fix is written;
  only the fan-out is rationed, so a player's map is at most five seconds
  stale while the courier walks - about seven metres, inside the accuracy of
  the fix itself. `clear_courier` ignores it deliberately.
- **The drop circle is placed at a 20 m radius** (`DROP_RADIUS_KM`), since it
  marks where the crate is rather than an area to search. Nothing in the
  spec fixed a number; change the constant if it reads too tight on the map.

### M4.2 — The courier and the crate on every map *(status: shipped 2026-09-17, PR #274)*

- `/get_circles` grows `courier: {lat, long, timestamp} | null`; the
  `"circle"` SSE event is fired (throttled) when the courier moves, so
  `MapCirclesFromAPI`'s existing listener refetches.
- `Dot.js` takes an optional `src`; the courier is drawn with a new image
  (**input needed from Charles/Gaby: her face in an aeroplane**, else a drawn
  placeholder in `images/art/`), and the drop circle gets a **crate icon** at
  its centre alongside the existing blue ping (`MapView.module.css`
  `.dropCircle`). Fade the courier dot with fix age like the admin map does.
- Same on `MapViewAdmin` and the spectator screen.

Drawn in `MapCircles` rather than in the dot layer, so all three maps get it
from one place. The spectator screen needed one extra thing the item did not
name: it passes the `GameModel` straight to the map instead of using
`/get_circles`, so it now listens for `"circle"` itself, or the aeroplane
would never move there. The courier image is a placeholder
(`images/art/courier.svg`) until Gaby's arrives — replacing the file is the
whole change.

### M4.3 — Clearing a crate once it has been claimed *(status: shipped 2026-09-17)*

Nothing in the app can see somebody pick a crate up, so taking it off the map
is a button somebody presses — and until this item there was no such button
and no way to have two crates out at once.

- A **`drops` table** (`backend/model.py`'s `Drop`), one row per crate, so a
  second drop no longer takes the first off every map the way the single
  `drop_circle_*` triplet did. The row *is* the crate: clearing one deletes
  it, and the ticker line announcing the claim is the record.
- `AdminInterface.place_drop` / `clear_drop` / `get_drops`, behind
  `admin_place_drop`, `admin_clear_drop` and `admin_list_drops`. Both
  announcements are the lines placing and clearing a DROP circle already
  fired — to a player it is the same event.
- `/get_circles` and `GameModel` grow `drops: [...]`, and `MapCircles` draws
  each one exactly as it draws the admin's own map-placed drop, which is
  unchanged and still works — except that the **blue ping is on the newest
  crate only**. The older ones keep their icon until they are collected, so
  the flashing circle goes on meaning "this one has just landed" rather than
  becoming three simultaneous alarms about crates half an hour old.
- The courier page grows the list: each crate with the time it went down and
  a two-tap **Collected** button, from the server rather than from what that
  tab placed, so a reload keeps it.

---

## M5 — Sounds *(status: shipped 2026-09-17, PR #270)*

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

Shipped, with four departures from the spec worth knowing:

- **The generator is kept**, as `scripts/make_sounds.py`. The first batch of
  `.wav`s had none, which made "louder" a guess; every sound in the game is now
  a function in that file, re-runnable and byte-identical when nothing changed.
  22050 Hz mono, matching the files that were already there.
- **`bang.mp3` is now `bang.wav`** (one import line in `FireButton.js`). There
  is no mp3 encoder in the dev shell, so "dropped over the old one, no code"
  was not available; the `.mp3` is deleted.
- **`hit_received.wav` is 2.5 s at 5.4x the average level of the one it
  replaces** (RMS 0.74 against 0.14), and moved out of the bass: the old one
  was a 130 Hz thump, and bass is the part of a sound a coat pocket eats. It is
  a two-tone klaxon now, 56% of its energy above 800 Hz.
- **`target_knocked_out` is derived, not stored.** Nothing on a `Shot` records
  the blow that took somebody out, and this milestone did not seem worth a
  column, so `get_own_shots` reads the target's hit points at the moment the
  shooter's client first sees the verdict. A hit on somebody already down
  reads the same way; nothing re-reads it for a shot already checked, so the
  sound never re-fires. If it is ever wanted as a fact rather than a cue, that
  needs a nullable column set in `AdminInterface.hit_user`.
- **The "sound on" line is a tappable test**, not a sentence
  (`useSoundCheck.js`): a phone on silent is silent and nothing in the browser
  can find that out, so the player runs the test. It doubles as the gesture
  that unlocks audio.

M1.2 lands on this one: now that everybody starts with their armour on
(`STARTING_HIT_POINTS = 2`), a single hit from the basic weapon no longer
knocks anybody out, so `shot_knockout.wav` is the sound of a *killing* blow
rather than of any confirmed hit. That is the better outcome - it is rare, so
it means something - but it does mean the ordinary evening is mostly
`shot_confirmed.wav`, which is still one of the two original placeholder tones.

---

## M6 — The two experimental items *(Friday; after M0.3; drop if not working)*

### M6.1 — Radar *(status: shipped 17 Sept, PR #275)*

- Handler: `User.radar_until = now + minutes*60` (nullable column). Refuses
  if already active.
- `GET /radar` (player-authenticated): while active, every other player in
  the game as `{name, team, lat, long, seconds_ago, accuracy, state}`;
  otherwise 403. Reuse `AdminInterface.get_locations`.
- Map: dots for everyone with a **"last seen 3 min ago"** label — the plan is
  explicit that this is last-seen, never live — greyed as the fix ages, and a
  strip "Radar: 4:12 left". Polls every 5 s while active (the admin map's
  pattern); no SSE needed.

Shipped as specified. Three things worth knowing beyond the spec:

- The two halves of the frontend are one file, `react-ui/src/RadarLayer.js`.
  The strip is mounted in `UserMode.js` (it has `/user_info`, so the countdown
  needs no poll of its own) and the dots inside `MapView.js`'s zoomable
  content; the strip tells the layer there is a radar to draw through a
  module-level store, the same shape as `shotRefusalStore.js`. That is what
  keeps the admin map and the spectator screen — which mount the same
  `MapView` — from polling a player's radar.
- A contact with no fix at all is left out, and anybody not on their feet is
  drawn grey and labelled "out" rather than with an age. A teammate is green
  and an opponent red: since R15 nobody can tell teams apart by eye, so the
  radar is the only place it gets said.
- The scan is announced publicly ("*X* has radar for the next 5 minutes -
  keep moving!"), like every other collection. Half the card's value is that
  everybody else starts moving.
- Both resets clear `radar_until`, so a radar lit in the sandbox hour does
  not survive the 16:00 button.

### M6.2 — Early circle warning *(status: shipped 17 Sept, PR #277)*

Reveals the next circle to the holder before it is announced. That needs a
circle that exists but is not public: add `Game.next_circle_public: Boolean
default False`. Placing NEXT no longer announces or draws it for players
until the admin **cues** it (M3.2), which sets it public; a holder with
`User.circle_warning_until` in the future sees it before that (filtered in
`get_circles`). Ticker says only "somebody knows where the next circle is".
The admin map always shows it.

Shipped as specified, backend only — the circle simply appears on the
holder's map, so there is no new screen furniture. Five things beyond the
spec that were needed to make it true:

- **Placing NEXT now says nothing at all.** `ADMIN_SET_CIRCLE_NEXT` is
  retired and left in `ticker_message_dispatcher.py` with a comment, because
  announcing a circle nobody can see is worse than silence. `CircleTypes.BOTH`
  *is* public: it puts the next circle exactly where the exclusion circle
  everybody can already see is. Re-placing or clearing NEXT makes it private
  again, so moving it mid-countdown takes the old one off every phone.
- **Cueing the circle fires a `"circle"` event** as well as setting the flag,
  or the newly-public circle would not reach an open map until something else
  happened to move a circle.
- **The admin map now reads the game's own circles** (`AdminMode.js`,
  `<MapViewAdmin circles={games[0]} />`) instead of `/get_circles`, which is
  the player endpoint doing the filtering. It stays current the same way the
  rest of the page does: a circle change wakes the `"admin"` stream, which
  refetches `admin_list_games`. The spectator screen already passed a
  `GameModel`, so it was unaffected.
- **The warning has to expire on the holder's map too.** Nothing else would
  fire at that moment, so `start_circle_warning` schedules a `"circle"` event
  for when it runs out — the first real caller of
  `asyncio_triggers.schedule_update_event`, which now no-ops without a running
  event loop (the guard `next_event.arm` already had) rather than failing the
  write that asked for it.
- **Both resets clear `circle_warning_until`**, as they do `radar_until`.

**Amended 18 Sept: the warning lasts until the circle is announced.** Ten
minutes was a duration with nothing behind it, and a card that ran out while
the circle was still private bought the holder nothing. `circle_warning_until`
now holds `CIRCLE_WARNING_UNTIL_ANNOUNCED` (infinity) and is cleared for every
player in the game when the cue makes the circle public - which is the moment
the head start ends anyway. The printed cards' `minutes` is read by nothing.
A card scanned with no private circle to show (none placed, or one already
announced) is *refused*, so it rolls back and stays in the player's pocket.

Not done, deliberately: the admin has no on-screen indicator of whether the
next circle is public yet. They can see the circle on their own map, and
`EventCue` sits directly under the circle controls, so cueing it is the next
thing in front of them. `GameModel.next_circle_public` is on the wire if that
turns out to want saying.

---

## M7 — Team leader view *(status: shipped 17 Sept, PR #261)*

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

Shipped as specified, with the first-draft checklist above (Charles's own
wording had not arrived; it is one array in `prose.teamLeader.checklist`).
The panel is `react-ui/src/TeamLeaderPanel.js`, which also exports the
`TeamLeaderButton` mounted beside the scoreboard in `BulletCount.js` and, for
a player who is out, in `UserMode.js`. Both render nothing for a player who
is not a leader. The admin toggle posts `/admin_set_team_leader`, which fans
out a `"user"` event to the player and a `"ticker"` one to their game so the
roster refreshes — the same pair `set_user_name` uses, since there is no
`"admin"` event of its own.

---

## M8 — The annotated admin map *(mechanism shipped 18 Sept; needs Charles's numbers)*

Charles and Gaby's marked-up map gives approximate circle centres and rough
drop areas. The repo is public, so rather than committing them the way
Kingston's are, they arrive from the environment: any
`LANDMARK_<NAME>="<lat>,<long>"` in `/data/secrets/streetfight.env` is merged
into the active venue at startup (`venues.landmarks_from_env`), so it shows up
in `CircleControl.js`'s landmark dropdown like any other place and needs no
code. The drop landmarks will travel the same way.

Four of those names are special: `CIRCLE0`…`CIRCLE3` are what
`circles.CIRCLE_PLAN` orders the night by. Their radii travel the same way,
as `CIRCLE_RADIUS_CIRCLE0=0.70` and so on (0.42, 0.18, 0.05 km). The game arms each in turn - at **Reset to start
state**, at **Start game** when nothing is placed, and the instant a circle
closes - so an admin who forgets to place NEXT cannot neuter the
early-warning card, and the act of running a circle is the countdown alone.
An entry missing either half is simply left for the admin to place by
hand. **Still outstanding: the numbers themselves.**

---

## M9 — The game-day runbook and the paper trail *(status: shipped 2026-09-17, PR #276)*

`docs/game_day_runbook_2026-09-19.md`: the plan's §5 as a checklist with the
button behind each step named — pause, **Reset to start state**, **Withdraw
`sandbox`**, ten minutes, WhatsApp, start; the circle and drop cues; the
courier page; what to do when a countdown fires while the server is
restarting. Plus the Thursday print list with counts, and the **Friday
droplet resize** (snapshot, power off, resize CPU/RAM, power on, verify) —
see the reminder at the top of this file. Update `docs/roadmap.md`
(#12 shipped, #8's print run) and `CLAUDE.md` for anything that moved.

Shipped as `docs/game_day_runbook_2026-09-19.md`, written against the merged
code rather than the specs. Three things in it that the item did not ask for
and that are worth knowing separately:

- A **"Decisions taken by the sessions"** section gathering every judgement
  call from PRs #254–#275 in one place, each naming its PR, so Charles can
  overrule them without reading twenty PR bodies.
- A **"When things go wrong"** section: the startup sweep, the cooldown
  refusal a player will report as "the app is eating my shots", a second
  phone, and the additive-only rule for a hotfix on the night.
- The print list carries the **level-1 armour trap** (M1.2's consequence) as a
  rule rather than a note, since it is the one way to print a stack of cards
  that does nothing.

`docs/roadmap.md`'s #12 and #8 were updated, and the "What the plan assumed"
section above now says which milestone superseded each of its bullets.

Both experimental items (M6.1, M6.2) are written up as shipped. M6.2 changed
the shape of the runbook's "Cue a circle" section rather than just adding to
it: placing NEXT is now private working-out and the **cue** is the
announcement, which is the one procedural change on the night that a reader of
the old plan would get wrong.

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
