# R9 — agent walkthrough of every feature shipped this year

**Run:** 28–29 August 2026, against `6cf5608`, on branch
`claude/feature-walkthrough-tests-hiqow6`.
**What this is:** the agent pass R9 asks for — *"Agents can and should run
through the player- and admin-facing flows first, in a browser at a mobile
viewport, to catch anything broken before a human's time is spent on it."*

**What this is not:** the gate. R9 is explicit that the gate is Charles doing
the same pass by hand on his own phone, "because an agent cannot judge 'does
this make sense to someone who has never seen it before' or 'is this button
reachable one-handed with a box of armbands in the other.'" Nothing below
changes that. This is the sweep that goes first so the manual pass is spent on
judgement rather than on finding 500s.

**No code was changed.** This report and its appendices are the only commit.
Every finding is written down, none is fixed.

---

## How it was run

Thirteen agents, one per group of checklist lines, each driving a real
Chromium at **390×844, DPR 3, touch**, against the actual app: FastAPI on
`:8000`, the CRA dev server on `:3000`, SQLite. Each agent was told to look at
its own screenshots rather than assert on `innerText`, to distinguish a
product bug from a container artefact, and not to pad the report with things
that work.

Agents mostly worked in **their own game** (`admin_create_game`) to keep
circles, tickers and toggles from colliding. The shot queue is global, so
queue-heavy agents were serialised.

### Three limitations, stated up front

**1. CharlesBot was stubbed.** There is no `OPENROUTER_API_KEY` in this
container. A local stand-in (`stub_openrouter.py`) served schema-conforming
replies, with `backend.vision_client.OPENROUTER_URL` rebound *in the launching
process only* — no repository file was touched. So everything **downstream** of
the model is genuinely exercised: queue annotation, the ranked candidate list,
the zoom indicator, auto-actions, escalation, the confidence gate, appeals and
the replay workbench. What is **not** exercised is whether a real model reads a
real photograph correctly. That is still what #4 and R1/R2 are for, and
nothing here should be read as evidence about model accuracy.

**2. The camera is Chromium's fake device** — a green test pattern. No shot
photo in this pass contains a person. One agent worked around this properly
for the loot flow: it rendered the admin's own item QR, converted it to a Y4M
and fed it to Chromium as the camera, so the real `QRParser` scanner path was
exercised rather than just URL navigation.

**3. Headless.** The phone's own lock button, real GPS drift, real cameras and
real thumbs are all out of reach. Where that mattered, the agent said so
rather than guessing — the wake-lock agent, for instance, established that
headless Chromium 141 *does* implement the Screen Wake Lock API and tested it
for real, then reported the "power button still works" half as untestable.

---

## Coverage

All **28** checklist lines were driven. No line was skipped.

### Player-facing

| # | Checklist line | Verdict |
|---|---|---|
| 1 | Join via QR/link and pick an outfit at `/pick` (#10) | works, with caveats |
| 2 | "recommended" vs "not ideal" badges and the reveal link | **works** |
| 3 | The name-then-confirm flow and lock-in | works, with caveats |
| 4 | An admin clearing a player's outfit so they can pick again | works, with caveats |
| 5 | Scanning a loot QR and using it (weapon/armour/ammo/medpack) | works, with caveats |
| 6 | Taking a shot photo, including the crosshair overlay | works, with caveats |
| 7 | The shot status bubble — every state, and that it stays | works, with caveats |
| 8 | Screen stays awake (R3) | works, with caveats; lock-button half untestable |
| 9 | Appealing a resolved shot as either party (R8) | works, with caveats |
| 10 | The map view and circles on the Westminster venue (#12) | works, with caveats |
| 11 | The ticker feed | **works** |
| 12 | Copy says "CharlesBot", never "AI" (#1, #2) | works, with caveats |

### Admin-facing

| # | Checklist line | Verdict |
|---|---|---|
| 13 | Reference-photo kit check at `/admin/reference` (R7) | works, with caveats |
| 14 | Shot review queue: ranking (#3), verdict, zoom tag, approve/reject | works, with caveats |
| 15 | The four `ai_*` toggles actually changing queue behaviour | **works** |
| 16 | Not re-reviewing an already-reviewed shot | **works** |
| 17 | Running an escalated review by hand (#11) | works, with caveats |
| 18 | The contested-shots list an appeal reopens (R8) | **works** |
| 19 | Recording a "hit a bystander" outcome | **works** |
| 20 | The per-shot map (R5): GPS accuracy and heading | **works** |
| 21 | Admin shot history and notes on a player | notes work; **history does not exist** |
| 22 | The identity workbench and overrides | works, with caveats |
| 23 | Renaming a team | **works** |
| 24 | Downloading all shot images as a zip | works, with caveats |
| 25 | The admin nav on a real phone screen | works, with caveats |
| 26 | The running app version on admin pages | works, with caveats |
| 27 | The replay workbench at `/admin/replay` (R1) | **works** |
| 28 | Reset (`resetdb`) and replay from a clean state | *see the reset section* |

**109 findings** so far: 1 blocker, 28 major, 42 minor, 26 cosmetic, 12 questions. (Line 28 —
the reset pass — was still running when this was written; its section is below.)

---

## What went right

Worth recording, because several of these are items the roadmap flagged as
risky and they came back clean:

- **R1's replay bug is demonstrably fixed.** Changing `zoom_mode` genuinely
  changes the wire traffic — `screened` = 2 calls (`n_messages` 1, 3),
  screened-with-zoom = 3 (1, 3, 5), `upfront` = 1 call of 2 messages, `single`
  = 1 of 1 — and the prompt reseeds per shape. Nine replays stored nothing:
  `admin_get_shot_ai_review` was identical before and after, and
  `admin_get_shot` byte-identical with `checked:false`.
- **The appeal refund inference is correct**, including the trap. Miss→bystander
  *and* bystander→miss both **reject** (both rulings say the shot hit nobody);
  miss→hit, hit-on-X→hit-on-Y and miss→refund all **uphold** and refund. Seven
  cases, all right.
- **The contested list is genuinely separate and correctly ordered** — creation
  order A1,A2,A3,A6 produced contested order A3,A1,A2,A6, and a second
  appellant does not move `appealed_at`.
- **R5's capture works end to end.** `alpha:90` stored `heading = 270`;
  no-compass stored `null`. The per-shot map draws accuracy to scale (8 m →
  17.6 px, 60 m → 132 px, against 1.1 px/m) and the heading cone points true
  north-up at 0/90/180/270 — no 90° error.
- **The four `ai_*` toggles each change real behaviour**, proven by stub call
  counts and models, not by reading the toggle back. Escalation defaults on
  and calls `stub/vision-pro`, not `stub/vision-flash`.
- **R7 handles the case R9 called out.** An unreadable photo gives
  `readable_channels: 0`, no ranking, and an amber *"No garment could be read
  in this photo… Retake it"* — no name, no confident-looking wrong answer.
  Reference photos store on the `User` and create no `Shot` (verified against
  all 29 queue entries individually).
- **The "CharlesBot, never AI" convention holds** in rendered copy: zero "AI"
  across eight screens including `alt`, `aria-label`, `placeholder` and
  `title`.

### One worry investigated and dismissed

The shot queue is global across games while every CharlesBot toggle is
per-game, which looked like it meant *one game's undecidable shot blocks
auto-adjudication for every other game*. **It does not.**
`process_queue_head` reads `get_queue_head(game_id)`, which filters
`filter_by(game_id=…, checked=False)` (`backend/admin_interface.py:212-237`).
Proved live: the global head was another agent's undecidable shot and the
test game's shot still auto-resolved. Only the admin's *view* is global —
which is its own (lesser) finding, below.

---

## The blocker

### B1 — every cookieless client shares one player identity

`backend/user_id.py:13` keys its `no_cookie_clients` dict on
`request.client.host`, the TCP peer IP. Ten independent browser contexts, each
with an empty cookie jar, hitting the app at once were all assigned **the same
player UUID**:

```
ctx0..ctx9  ->  b0234858-a04a-4bd3-8747-8cb012e9e4ba   (distinct: 1 of 10)
```

They are not ten players; they are one player with ten screens — sharing ammo,
HP, appeals and shot history, with whoever's `set_name` lands last winning.

The mechanism is right and the comment in `assign_new_ID` explains the intent
(hold one UUID across concurrent cookieless requests *from one client*). The
**key** is wrong.

**This is worse in production, not better.** Every deployment puts Caddy in
front and proxies `/api/*` to `127.0.0.1:<port>` (`Caddyfile:8`,
`nix/streetfight.nix:45`), and uvicorn is started **without**
`--proxy-headers` / `--forwarded-allow-ips` in all three launch paths
(`flake.nix:165`, `nix/streetfight.nix:211`, `package.json:7`). There is no
`ProxyHeadersMiddleware` in `backend/main.py`. So `client.host` is the literal
string `127.0.0.1` for *every* player on the night, and the dict has one key
for the whole game.

Every player's first request is cookieless, and the window lasts until that
client comes back carrying its cookie — which at kick-off is exactly when
everybody loads the app at once. Two players who overlap in that window become
the same player, silently.

**Note for the dry run:** with a handful of people arriving at slightly
different moments this may well *not* reproduce on 30 August. That is what
makes it worth fixing rather than watching for.

---

## Major findings

Grouped by where they bite. Full reproduction detail for each is in the
appendix named in brackets.

### Adjudicating a shot — the admin's core loop

The queue is where the night is won or lost, and it has the densest cluster.

- **The shot photograph is 134×71 CSS pixels on a phone.** `<Row><Col>` with no
  responsive breakpoint keeps two columns side by side at 390 px; the map next
  to it gets ~520. The whole queue exists so a human can look at the picture,
  and on the phone the admin will be holding, they cannot. [A9]
- **Every adjudication control in the queue is 24 px tall; radios are 13 px.**
  Roughly half the 44 px touch minimum, and the two 31×24 buttons most likely
  to be mis-hit are the ones that damage a player. `ReferencePhotos.module.css`
  already has the pattern to copy. [A9, corroborated by A12]
- **CharlesBot's overall confidence is never displayed.** A 0.55-confidence hit
  and a 0.95-confidence hit are the same green "HIT" pill. This is half of what
  checklist line 14 asks for, and the half that tells a rushed admin whether to
  look at the photo at all. (`escalationVerdictTag` does show a %; `outcomeTag`
  does not.) [A9]
- **The ranked list is read-only.** Acting on #3's ranking means re-finding the
  same name in a separate, unranked roster. That is where the wrong player gets
  shot at 3 a.m. [A9]
- **An adjudication gives no confirmation** — the panel silently becomes a
  different shot. Resolutions are terminal, so an admin who cannot see what
  they just did cannot notice a fat-fingered ruling. Combined with the 24 px
  buttons, they will make some. [A9]
- **One unrenderable image 500s `admin_get_shot` and takes the page down.**
  `draw_cross_on_image` (`backend/image_processing.py:254`) hardcodes an RGB
  fill and hands it to PIL, which rejects it on a single-channel image
  (`TypeError: color must be int or single-element tuple`). `ShotQueue.js`
  preloads the *whole global queue* with no `.catch`, so one bad shot floods
  the page with uncaught rejections and the dev overlay swallows every click.
  614 tracebacks in this run. The same function captions the zip, so it breaks
  that too. Reproduced deterministically against the repo's own functions:
  `L` fails, `RGB` and `CMYK` pass. Three sibling functions in the same file
  already branch on `image.mode not in ("RGB", "L")` — these two did not get
  the same treatment. *The trigger here was a synthetic image; phones shoot
  colour JPEG, so this is a robustness gap rather than a certainty.* [A0, A9, A10]
- **There is no per-player shot history.** Only a 40-deep Next/Previous pager
  over every shot in every game; no endpoint keyed by user. The moment a player
  says "I've been shot three times and only lost one HP", the admin has to find
  that player's shots under time pressure at one shot per tap with a ~1 s image
  load between taps. [A11]
- **The adjudicated-shot history never says when a shot was fired**, though
  `time_created` is already in the payload and the players' own history shows
  it. Adjudication arguments are almost always about ordering. [A11]
- **The admin queue is global while every toggle is per-game** — 36 shots
  listed with no game column. Harmless to the auto-action logic (see above),
  but the admin cannot tell whose game a shot belongs to. [A10, A9]

### Taking a shot

- **The crosshair is not in the stored photo, and is nearly invisible in the
  copy the model sees.** `MyWebcam.js` captures only the video; the marker is
  added server-side as a 1 px line *before* the downscale, measuring R=53 on
  G=129 after `prepare_for_vision`. The docstring at `image_processing.py:120`
  says the full-frame line was chosen so "the marker survives downsizing and
  JPEG compression" — measured, it does not survive well. **This bears
  directly on #4**, the item the roadmap marks as the one worth rushing: the
  model is being asked whether the cross *centre* lands on a person, from an
  image where the cross barely reads. [A4]
- **The shot cooldown is enforced only in the browser, and a reload clears
  it.** A reload re-armed the button 1.6 s into a 6 s timeout, and three
  back-to-back `submit_shot` calls all returned 200 — `submit_shot` checks
  team, HP and ammo and nothing else. Weapons are differentiated almost
  entirely by `shot_timeout`, so an unenforced cooldown makes the weapon table
  advisory. No malice needed: a PWA that reloads after a crash hands out a free
  shot. [A4]

### Joining and picking an outfit — the door, on the night

- **`pick_outfit` will place a nameless player.** The name requirement is
  client-side only (`react-ui/src/PickOutfit.js:310`); the API returns 200,
  burns one of the 7 slots a hat colour affords, and leaves someone invisible
  in the roster and unmatchable by the door staff or by `ReferencePhotos`.
  `join_options` goes to real trouble not to create a `User` row for
  link-preview bots, and then this creates one for anybody. [A1]
- **A name typed but not submitted leaves "Lock in my choice" dead.** The name
  sits visibly in the box, the button is greyed, and the message says to enter
  a name. `NameEntry` commits only on Enter or the arrow button; phone keyboards
  show "return"/"go" but plenty of people tap Done or tap away. Most likely
  place for the door queue to stall. [A1]
- **Scanning the wrong team's QR after locking in shows you the wrong team and
  the wrong hat colour** — `join_options` resolves `you` across `game_users`
  rather than the team's roster. On the night there will be one printed card
  per team on a table and people will scan the nearest one; the page then tells
  them, confidently and finally, that they are in the wrong team wearing the
  wrong hat, and invites them to screenshot it. [A1]
- **Pressing Save after "Clear outfit" silently un-clears the player.**
  `PlayerEditor`'s initialising `useEffect` is keyed on `[player.user_id]`
  only, so re-loading the report for the *same* player never re-seeds the
  editor. This is exactly the door-desk sequence — clear the guest in the wrong
  shirt, then poke at the same panel — and the undo is invisible: the row says
  `none`, the panel says `2`, and the panel wins. [A2]
- **The pagination controls are unstyled default browser buttons, 41×24 and
  63×24 px** — the only way to reach 37 of the 49 outfits, operated one-handed
  in a pub doorway, directly against the house style. [A1]

### Loot

- **A knocked-out player cannot collect a medpack from a link.**
  `CollectItemFromQueryParam` lives inside `BulletCount`, which `UserMode`
  renders only while alive. The knocked-out screen says "Get a medkit quick!"
  and the link is inert. The dry-run plan is "QR codes go out on WhatsApp,
  players follow links", and a medpack is exactly the item you need while
  knocked out. The in-game camera path still works. [A3]
- **Every failure on the link path is completely silent.** Already-collected,
  dead, wrong weapon, bad signature and 500 all look identical — the app blinks
  back to `/` and says nothing. The camera path flashes red and beeps; the link
  path does neither. "I scanned it and nothing happened" is the support call.
  [A3]
- **`collected_as_team` is offered for all four item types but implemented only
  for ammo.** A team armour/medpack/weapon QR mints and prints fine, then
  serves the player a raw Python repr:
  `Item collection for (<ItemType.ARMOUR: 'armour'>, True) has not been
  implemented`. Drops are minted from this form and **printed** (#8). [A3]

### Appeals

- **HP is not restored when an appeal is upheld**, and nothing reminds the
  admin. An upheld appeal that leaves the player exactly as wounded as before
  is not a correction from the player's point of view, and this is the most
  distracted moment the admin will have. [A6]
- **An upheld appeal by the target deletes the shot from their history.**
  `_settle_appeal` clears `target_user_id`, `get_shots_received` filters on it,
  and the bubble is `shotList[0]` — so it reverts to an unrelated older shot
  and `appealUpheld` is never visible to the winner. This is the one case where
  the checklist's "stays on screen rather than disappearing" claim fails: the
  player who was hit, spent one of three appeals and was proved right watches
  their own evidence vanish. [A4, A6]

### Circles and announcements

- **`admin_clear_circle` announces the circle as if it had just been set.**
  Clearing the supply drop removes it from the map *and* tells everyone "A
  supply drop has appeared! It's marked in blue" — `set_circles` always sends
  the ticker message regardless of whether it set or cleared. Same for NEXT and
  EXCLUSION. A whole team runs to a drop the admin just removed, and there is
  no way to clear a circle quietly. (Note also two functions in `main.py` both
  named `admin_set_circle`, at :951 and :991, the second shadowing the first.)
  [A5]

### Post-game artefacts

- **One player with `/` in their name makes the whole zip download 500 for
  everyone** — confirmed live with a traceback. `filename = f"{name}_{time.time()}.png"`
  with no validation on the player-supplied name. A leading `../` is the
  quieter variant: it silently drops the image and writes outside the temp dir.
  Players type their own names; one `Rob/Bob` kills the post-game image dump.
  [A11]
- **Zip filenames cannot identify a shot** — the timestamp is the moment of the
  zip, not of the shot (all 40 files stamped within one 2-second window). This
  dump is the artefact you go through afterwards to settle arguments and to
  feed the replay harness; `shot_model.id` and `time_created` are both to hand.
  [A11]

### Admin pages on a phone

- **Four of the seven admin pages scroll horizontally at 390 px.**
  `/admin/reference` and `/admin/identity-overrides` both reach **778 px**,
  from the same copy-pasted `GameSelector` `<select>` with no `max-width`,
  which sizes itself to its longest option (10 team names = 769 px). Swiping
  right gives a blank page with no nav. `/admin/identity` 610 px, `/admin`
  408 px, `/admin/shots` 401 px. The door kit-check page is used standing up
  with a queue of players in front of you. One CSS line, in two files. [A12,
  A2, A8]

### Sessions

- **An in-flight request silently logs the admin back out.** The session is a
  signed cookie and is last-writer-wins: a request already in flight when
  `admin_authenticate` succeeds carries the pre-login session and writes it
  back over the cookie. `admin_authenticate` returns `true`, the `Set-Cookie`
  carries `admin_authed`, and the next `admin_is_authed` returns `false`.
  Logging in on a bare page with no polling is reliably fine — that is the
  workaround the harness used. Same last-writer-wins mechanism as B1. [A0]

---

## Three themes that cut across everything

These were found independently by several agents, which is why they are worth
pulling out rather than leaving as a scatter of separate lines.

### 1. `* { font-size: 12px }` quietly shrinks the entire house style

`react-ui/src/index.css:14-17` sets a 12 px font size on every element, so
every `em`-based dimension in the codebase resolves to something smaller than
it reads. Measured with `getBoundingClientRect()`:

| Intended | Resolves to | Where |
|---|---|---|
| nav `min-height: 3em` | **36 px** | all 8 nav links, all 7 admin pages |
| `ReferencePhotos` primary `3.5em` | **42 px** (`.bigButton` 46.2 px) | the house-style exemplar |
| `ReferencePhotos` button row `3em` | **36 px** | — |
| "← Roster" | **31.2 px** | the exemplar again |
| queue Missed/Bystander/Refund | **24 px** (radios 13 px) | `ShotQueue.js` |
| `/pick` option rows | **40 px** | — |
| shot-history popup targets | **30–36 px** | — |

`CLAUDE.md` records the house style as "comfortably past the 44px touch
minimum, because this is driven one-handed on a phone with a box of armbands
in the other hand". Almost nothing in the app currently clears 44 px — only
the reference-photo roster row (50 px). The exemplar does not meet its own
stated bar, and the numbers in the CSS are not wrong so much as measured
against a root that was changed underneath them.

### 2. Failures are silent almost everywhere

Distinct agents found the same shape in five unrelated places: the loot link
path (every failure identical and wordless), a shot the server refuses
(bang, vibration, full cooldown, no shot, nothing said), an adjudication
(panel silently becomes another shot), a cleared outfit (silently un-cleared),
and an unsaved note (discarded on navigation). On the night, every one of
these becomes "I did the thing and nothing happened", which costs the admin's
attention at exactly the wrong moment.

### 3. Pages are built for a desktop and then used on a phone

The horizontal scroll on four admin pages, the 134×71 px shot photo, the
155 px notes box, the queue's Hit buttons overlapping player names, the
unlabelled swatches whose only labelling is a `title` tooltip that does not
exist on touch — all the same root cause. The game is mobile-only and
`CLAUDE.md` says so; several admin pages have not been looked at that way.

---

## Everything else

Full reproduction detail for each is in the appendix in the last column.


### Minor

| Finding | Where | Appendix |
|---|---|---|
| The primary tap targets on the page are all under 44px tall | `react-ui/src/PickOutfit.module.css:203` | A1 |
| The no-outfits empty state hides below the whole wardrobe form | `react-ui/src/PickOutfit.js:545-552` | A1 |
| The error popup is unreadable on this page — it sits translucent over the page text | `react-ui/src/Popup.module.css:10-17` | A1 |
| "Run escalated review" reports its one foreseeable failure as a raw browser alert() | `react-ui/src/ShotQueue.js:827-829` | A10 |
| On a 390px phone the queue's error banner overflows off-screen, and the Hit buttons sit on top of the player names | `react-ui/src/ShotQueue.js` | A10 |
| A shot fired outside the venue crop shows a blank white box with no explanation | `react-ui/src/ShotMap.js:62` | A11 |
| An unsaved note is discarded silently when you page to another shot | `react-ui/src/ShotQueue.js:363` | A11 |
| The notes textarea is ~155 px wide in the queue's left column at 390 px | `react-ui/src/ShotQueue.js:800-830` | A11 |
| The download button gives no feedback at all while the zip builds | `react-ui/src/AdminMode.js:530-539` | A11 |
| Every nav button is 36px tall, not the ">44px" the CSS says | `react-ui/src/index.css:14-17` | A12 |
| The footer identifies the backend only — nothing says which frontend you are looking at | — | A12 |
| The git fallback hides a dirty tree | `backend/main.py:144-150` | A12 |
| The whole page scrolls sideways on a phone because of the game selector | `react-ui/src/AdminIdentity.js:657` | A2 |
| The four swatches are unlabelled, and the only labelling is a hover tooltip | — | A2 |
| The page departs from the ReferencePhotos house style throughout | `react-ui/src/AdminIdentity.module.css` | A2 |
| A player's own HUD never shows their team name, so the rename is only visible in the scoreboard | — | A2 |
| A weapon whose damage/timeout pair is not in the lookup shows as nothing at all | `backend/item_actions.py:124` | A3 |
| The "new item" pickup overlay does not actually appear | `react-ui/src/TemporaryOverlay.js:41-72` | A3 |
| `collect_item` 500s on QR payloads that are not items | `backend/main.py:382-390` | A3 |
| The fire button says "NO AMMO!" to a player who has ammo but no weapon | `react-ui/src/FireButton.js:14-17` | A3 |
| A shot the server refuses is swallowed silently | `react-ui/src/MyWebcam.js:96-105` | A4 |
| The received-`unreviewed` bubble state ("Shot at you") cannot occur | `react-ui/src/ShotHistory.js:80-91` | A4 |
| At real phone size the bubble is colour-only — the glyph does not read | `react-ui/src/ShotHistory.module.css:290-320` | A4 |
| Every tap target in the shot-history popup is under the 44px minimum | `react-ui/src/ShotHistory.module.css:205-260` | A4 |
| The wake lock is held on the onboarding screen, before the game starts | `react-ui/src/UserMode.js:30` | A5 |
| The lock is still held after the player dies, and re-acquired on every return to foreground | `react-ui/src/useWakeLock.js:7-35` | A5 |
| The drop circle is invisible for ~70% of its animation and never shows its real radius | `react-ui/src/MapView.module.css:97-120` | A5 |
| Ticker text is locked to 12px regardless of the phone's text-size setting | `react-ui/src/index.css:14-17` | A5 |
| An upheld target appeal erases the shot from the winner's own history | `backend/admin_interface.py:1186` | A6 |
| The backend accepts an appeal reason belonging to the other party | `backend/user_interface.py:633` | A6 |
| The public overturn line misattributes the call, and says nothing when the hit only moves | `backend/ticker_message_dispatcher.py:127` | A6 |
| Nothing anywhere tells the admin an appeal is waiting | `react-ui/src/AdminMode.js` | A6 |
| An admin error dialog says "AI" twice, and points at a button that no longer has that name | `backend/main.py:726-729` | A7 |
| The public ticker blames CharlesBot for rulings CharlesBot never made | `backend/ticker_message_dispatcher.py:127-130` | A7 |
| A reading that fits nobody still headlines "Probably `<the player you photographed>`" | `react-ui/src/ReferencePhotos.js:104-149` | A8 |
| When the player has not picked an outfit, the page hides the one candidate that matters | `react-ui/src/ReferencePhotos.js:122` | A8 |
| The review's loading state claims the vision model is not configured | `react-ui/src/ReferencePhotos.js:168-173` | A8 |
| The game picker forces the page to scroll sideways on a phone | `react-ui/src/ReferencePhotos.js:376-397` | A8 |
| `* { font-size: 12px }` shrinks the exemplar's own touch targets | `react-ui/src/index.css:14-17` | A8 |
| Every runner-up prints `p=0.00` | `react-ui/src/ShotQueue.js:565-572` | A9 |
| The queue is global across games, and its two counters disagree | `backend/main.py:526-528` | A9 |
| "Missed", "Bystander" and "Refund" are three identical grey bars | `react-ui/src/ShotQueue.js:861-884` | A9 |

### Cosmetic

| Finding | Where | Appendix |
|---|---|---|
| `body` is white behind a black page | `react-ui/src/PickOutfit.module.css:6` | A1 |
| No way back to the curated view once "Show more outfits" is tapped | `react-ui/src/PickOutfit.js:385-388` | A1 |
| Accuracy of exactly 0 draws no circle at all | `react-ui/src/ShotMap.js:133` | A11 |
| The save button reads "Notes saved" on a shot that has never had a note | `react-ui/src/ShotQueue.js:394` | A11 |
| "Player view" is a one-way trip | — | A12 |
| The replay error text is a double-escaped JSON blob | `react-ui/src/ShotReplay.js` | A12 |
| The nav's "Identity workbench" is the sandbox, not this page | `react-ui/src/AdminIdentity.module.css:189` | A2 |
| Historical ticker lines keep the old team name | — | A2 |
| The rename form is fine but small, and there is no feedback that it worked | `react-ui/src/AdminMode.js:119-164` | A2 |
| Ticker text is white-on-white when the camera is pointed at anything bright | `react-ui/src/TickerView.module.css:1-5` | A3 |
| On the knocked-out screen the headline is the smallest text | `react-ui/src/GuideImages.module.css:1-13` | A3 |
| The cooldown and no-ammo refusals are pictures, not words | `react-ui/src/FireButton.js:71-84` | A4 |
| The popup is 70%-opaque over a live camera feed, and the ticker bleeds through | `react-ui/src/Popup.module.css:12-18` | A4 |
| The public "appeal upheld" ticker line always blames CharlesBot | `backend/ticker_message_dispatcher.py:127-130` | A4 |
| A re-acquired sentinel replaces the old one without releasing it | `react-ui/src/useWakeLock.js:15-21` | A5 |
| The popped-out map wastes more than half the panel on blank white | `react-ui/src/MapView.js:265-268` | A5 |
| The corner mini-map is flush against the top and right edges of the screen | `react-ui/src/UserMode.module.css:1-8` | A5 |
| The confirmation's scroll chevron sits on top of the appeal count | `react-ui/src/Popup.js:90` | A6 |
| `admin_give_appeals` announces the raw number, including negatives | `backend/admin_interface.py:1127` | A6 |
| The queue calls the escalation "the stronger model", one line under a sentence that calls it CharlesBot | `react-ui/src/ShotQueue.js:215` | A7 |
| The reference-photo page shows a CharlesBot reading but never names it, and has no boundary comment | `react-ui/src/ReferencePhotos.js:169-173` | A7 |
| The shooter's own history prints raw enum words where the admin gets a sentence | `react-ui/src/ShotHistory.js:125-140` | A7 |
| A raw OpenRouter error is shown to the admin verbatim | `react-ui/src/ShotQueue.js:95-99` | A7 |
| "Review failed" is red, where the page's own rule says amber | `react-ui/src/ReferencePhotos.js:47` | A8 |
| A green "HIT" tag on a kit check | `react-ui/src/ReferencePhotos.js:197` | A8 |
| The human verdict is plain black text, not a status pill | `react-ui/src/ShotQueue.js:813-815` | A9 |

### Open questions (for Charles to decide, not bugs)

| Finding | Where | Appendix |
|---|---|---|
| Nothing on the page says what "not ideal" means | `react-ui/src/PickOutfit.js:188-212` | A1 |
| The "You're set" screen is a dead end, and never names the armband colour | `react-ui/src/PickOutfit.js:327-355` | A1 |
| The zero-shots case is not reachable on the shared container | `backend/postprocess_shot_images.py:52-68` | A11 |
| The version is invisible to players, and to a logged-out admin | — | A12 |
| In "screened" mode the schema box does not apply to turn 1, and the follow-up wording is fixed | `backend/shot_vision.py:945` | A12 |
| Nothing in the clear flow frees the *wardrobe* back in a useful way | `backend/identity_admin.py:301` | A2 |
| Only a distance-0 override is gated; distance-1 is written silently | `backend/identity_admin.py:268-270` | A2 |
| Outside the exclusion circle, the corner map is a featureless red square | `react-ui/src/MapView.module.css:58-64` | A5 |
| Geolocation watch errors spam the console when the fix changes | — | A5 |
| A player newly convicted by someone else's upheld appeal has no recourse | `backend/user_interface.py:175` | A6 |
| The roster gives no sense of how much of the door queue is done | `react-ui/src/ReferencePhotos.js:69-95` | A8 |
| The zoom tag says a zoom was spent but the admin cannot see what the model was shown | — | A9 |

---

## Resetting and replaying from a clean state

*(Checklist line 28. This pass was still running when the rest of the report
was committed; this section is filled in below.)*

<!-- A13 -->

---

## Suggested order of attention

Not a plan, and not prescriptive — this is the reporter's read of what the
19th actually depends on. Charles decides what blocks and what is accepted.

1. **B1, the shared player identity.** It is the only finding that can make the
   game incoherent for a player rather than merely annoying, it is invisible
   when it happens, and the dry run may not reproduce it.
2. **The crosshair contrast**, because #4 is already the item being rushed and
   this is an input to it. Worth measuring before spending more on the prompt.
3. **The queue's touch targets and the 134×71 px photo.** These are what the
   admin does all night, and the fixes are CSS.
4. **The three "printed artefact" findings** — team QRs resolving the wrong
   team, `collected_as_team` unimplemented for three item types, and whatever
   the reset pass says about QR survival — because #8 is a print run and
   reprinting is not free.
5. **The server-side gaps** — nameless `pick_outfit`, unenforced shot cooldown,
   unvalidated player names reaching a filename.
6. Everything else, in severity order, as time allows.

## What this pass could not tell you

- Whether CharlesBot is *right*. Every verdict here came from a stub.
- Whether any of it is usable one-handed with a box of armbands in the other
  hand. Measured pixels are not thumbs.
- Whether the flows make sense to someone who has not read the roadmap.
- How any of it behaves on real GPS, a real camera, real phones, or a pub's
  mobile signal.

Those are R9's actual gate, and they are still outstanding.
