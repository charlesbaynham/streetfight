# Roadmap

The planned work, re-ordered from the order it was thought of into the order it
wants doing. This file is the record of intent, not a changelog — each entry's
status line says what has actually shipped.

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
| **Now**        | Armbands and hats bought. Pub conversations started — a landlord agreeing to hold a code is a conversation with human latency, not a data problem. | #9, #6       |
| **~31 Aug**    | Westminster map drawn and active. Colour-picking page built. Drops scouted. **Map and picking page both in; drops now unblocked.**         | #12, #10, #7 |
| **~7 Sept**    | Picking page live; players choosing outfits and finding the clothes.                                                                       | #10          |
| **~12 Sept**   | Picks closed. Everything printed.                                                                                                          | #8           |
| **Before setup** | Accuracy and heading capture in, so the schema change rides the game's own `resetdb` and the night's telemetry is recorded. **Shipped.**  | R5           |
| **~7–17 Sept** | Manual human pass through every feature shipped this year, on a real phone. Bugs found either fixed or written down as accepted.           | R9           |
| **15–19 Sept** | Drops placed, pub packs delivered, go/no-go on auto-actions.                                                                               | #7, #8       |
| **After**      | Everything in tracks A and C that did not fit.                                                                                             | the rest     |

The tightest link in that chain is **#10 → #8**: nobody can be handed an
appearance card until they have chosen an appearance, and nobody can choose one
until the page exists. That makes the colour-picking page the single piece of
software with a real deadline, which is not where it started on the list.

### The dry run: Sunday 30 August

A casual test game with ~10 people, two days before the ~31 Aug row above -
the first time real players touch any of this, and so the first pass at R9's
checklist with someone other than an agent driving. Decisions taken for it:

- **Played in Westminster**, on the live venue - no venue work needed.
- **Deployed on a cloud VM (DigitalOcean droplet), not the home server** -
  capacity is guaranteed and nothing on the home network needs exposing.
  The droplet is a **NixOS host** (`nixosConfigurations.streetfight-cloud`,
  shipped 28 Aug): installed with `nixos-anywhere`, updated with
  `nixos-rebuild --target-host`, reusing the same service module as the LXC
  with Caddy doing ACME itself (`services.streetfight.hostname`). Runbook:
  `docs/deployment_droplet.md`. It **replaces** the home LXC deployment
  behind traefik: its secrets are escrowed across, DNS for
  `streetfight.houseabsolute.co.uk` moves to the droplet, and the
  hypervisor's pull-based auto-redeploy is disabled - the cutover section
  of the runbook is the procedure. **Installed onto the live droplet
  28 Aug; cutover in progress** - DNS repointing and the home LXC's
  stand-down (hold file in place, `services.yaml` removal pending merge)
  still await verification. Updates are an explicit `nixos-rebuild`
  push, not a master-push auto-deploy. (The docker-compose path with
  `SITE_ADDRESS`/`compose.ghcr.yml`/watchtower, also fixed up 28 Aug,
  remains as the fallback.)
- **QR codes go out on WhatsApp**, not paper - #8's print run is not pulled
  forward, players follow links.
- **Pubs stay placeholders**: ammo is handed out directly, so #6's landlord
  conversations are not on this critical path. The pub landmarks already on
  the venue are enough.
- **The whole CharlesBot stack runs live** - review, auto-actions,
  escalation, resolve-everything. The admin flow is already proven from
  previous games; the AI adjudication path is the thing this test exists to
  exercise, so it does not hide behind the safety valve on the day.
- **Kit**: the armbands and hats have arrived and their colours are measured
  into `config.py` (R6, 29 Aug), so all four channels are live for the test.
- **Pre-Sunday QA, in two passes**: first an agent click-through of the
  player and admin flows at a mobile viewport (the `run-mobile-app` skill),
  run against the merged deployment code; then Charles's own end-to-end pass
  on his phone - planned, not yet done. Bugs found are the *point*, and
  anything broken is fixed or written down rather than worked around
  silently. Findings land on the R9 checklist.

### R10 — Auto-deploy for the droplet *(shipped 2026-08-29)*

**Shipped** as `nix/auto-deploy.nix`, imported by `streetfight-cloud`, with
the closure pre-built into Cachix by `build_images.yml`. The spec below is
what was built, bar three corrections found on the live droplet:

- **`git` is not optional and not only for `ls-remote`.** The flake takes
  `cattle` as a `git+https` input, and nix cannot fetch it without a git
  binary — even evaluating the cloud configuration, which never uses it. The
  droplet had no `git` at all, so any on-box flake rebuild failed at
  evaluation.
- **Flakes were not enabled on the droplet** (`experimental-features` unset),
  because nixos-anywhere builds elsewhere and pushes a closure — nothing had
  ever needed them there. `nixos-rebuild --flake` fails immediately without
  them.
- **The health-check URL was wrong.** With `services.streetfight.hostname`
  set, Caddy serves exactly one vhost, for that name, so
  `http://127.0.0.1/api/get_version` matches nothing. It checks the backend
  port directly.

Worth recording alongside: `/api/get_version` read `unknown` on the live box
because the install-time evaluation saw a source with no git revision.
Deploying from a `github:` ref, as this does, stamps it correctly.

---

**The decision.** Auto-deploy on master pushes is a property every
deployment of this game has had (watchtower on compose, the pull-based
cattle redeploy on the LXC) and the droplet keeps it. The NixOS path
shipped with explicit `nixos-rebuild` pushes only; this item closes that
gap. Nice-to-have by the dry run, not a blocker for it - the manual deploy
loop works meanwhile.

**The shape: pull, not push.** A systemd **timer + oneshot service** pair
on the droplet (`nix/auto-deploy.nix`, imported only by
`streetfight-cloud` - the LXC is unaffected), keeping the trust model the
LXC established: the host reaches out; nothing on the internet holds
credentials into it. Each tick:

1. `git ls-remote https://github.com/charlesbaynham/streetfight
   refs/heads/master` → target rev. This is the cheap gate that makes a
   short interval (~2 min, randomized) affordable - nothing else runs when
   nothing changed.
2. Compare against a state file under `/var/lib/streetfight-autodeploy/`
   recording the last **success** and last **failure** rev. Target equal to
   either → exit 0. The failure memo is what stops a broken commit
   crash-looping the deployer; the next commit retries naturally.
3. `nixos-rebuild switch --flake
   github:charlesbaynham/streetfight/<rev>#streetfight-cloud` - pinned to
   the rev just observed, so there is no gap between deciding and
   fetching.
4. Health check `curl -fsS http://127.0.0.1/api/get_version`, confirm it
   reports the new rev, record the outcome in the state file and the
   journal.

**Make the rebuild cheap: CI builds the system closure.** A job in
`build_images.yml` building
`.#nixosConfigurations.streetfight-cloud.config.system.build.toplevel` on
master, pushed to `streetfight.cachix.org` by the existing cachix action.
The droplet then *substitutes* the new system rather than building it;
only evaluation happens on-box (the reason `nix/cloud-host.nix` carries a
swapfile - and a 2 GB droplet is the comfortable size). Note this job can
only pass once the real deploy key has replaced the placeholder in
`nix/cloud-host.nix`: the assertion fails evaluation until then, which is
correct.

**Prerequisite that is easy to miss:** the droplet must trust the cachix
substituter *non-interactively*. The flake's `nixConfig` only takes effect
when accepted at a prompt, which a systemd service never sees - so bake
`nix.settings.substituters` / `trusted-public-keys` for
`streetfight.cachix.org` into the system configuration itself.

**Guardrails.**

- An `enable` option on the module as the kill switch.
- `Nice`/`IOSchedulingClass=idle` and a `MemoryHigh` on the service, so a
  deploy landing mid-game degrades the deploy, not the backend.
- No auto-rollback in v1: `nixos-rebuild` keeps the previous generation,
  `nixos-rebuild switch --rollback` is the manual recovery, documented in
  the runbook. A failed health check logs loudly and stops retrying; it
  does not thrash.
- `switch` only restarts units whose definition changed, so a
  frontend-only change never touches the backend; when the backend does
  restart, SSE clients reconnect on their own.

**Not chosen, and why.** `system.autoUpgrade`: re-evaluates the whole
flake every tick whether or not anything changed - the ls-remote gate is
the entire point on a small box. CI-push over SSH (`nixos-rebuild
--target-host` from Actions): puts a root-capable private key in GitHub
secrets and gives CI a route into the host; pull inverts that, and the
LXC already proved the pattern.

**Lands in:** `nix/auto-deploy.nix` (new), `flake.nix` (import it in
`streetfight-cloud`), `nix/cloud-host.nix` (`nix.settings` trust),
`.github/workflows/build_images.yml` (cloud-system job),
`docs/deployment_droplet.md` + `CLAUDE.md` (update the "explicit push"
wording).

**Done when** a push to master is serving at
`streetfight.houseabsolute.co.uk` within ~5 minutes with
`/api/get_version` reporting the new rev, and a deliberately broken
commit deploys once, fails its health check, and does not retry until the
next commit lands.

## Priority order

| Order | Item                                        | Deadline                     | Why here                                                                                                       |
| ----- | ------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1     | **#9** Buy armbands and hats                | Bought                       | Longest lead time; #10 and #8 both waited on it. Bought.                                                       |
| 1b    | **R6** Check the kit hexes on arrival       | Shipped 29 Aug               | Delivered, photographed and measured. The hat and armband palettes in `config.py` are now the real colours, not the simulated ones. |
| 2     | **#6** Find the pubs                        | Now → 7 Sept                 | Needs other people to say yes. Start the conversations first, collect the data second.                         |
| 3     | **#12** Redraw the Westminster map          | Shipped 28 Aug               | Play area fixed, drawn map active, resort venue retired. #7 unblocked. A hand-drawn replacement is still wanted but no longer blocks anything. |
| 4     | **#10** Colour-picking page                 | Shipped 26 Aug; live to players ~7 Sept | Built ahead of schedule — was the only software on the critical path, and the mitigation for bring-your-own garments (see #9). |
| 5     | **#7** Find the drop locations              | ~7 Sept                      | Needs #12 to place them; feeds #8.                                                                             |
| 6     | **#8** Print the run                        | ~12 Sept                     | Everything above becomes paper here.                                                                           |
| 6b    | **#5** Score candidates, not codewords       | **Before the 19th**          | Promoted from 13. Auto-actions are required, and they cannot work while identification decodes against the code. |
| 7     | **#4** False hits                           | Before the 19th *if it fits* | The one recognition item worth rushing; if it slips, run with auto-actions off.                                |
| 8     | **R1** Offline replay harness               | With #4                      | What makes #4 tractable in the time available rather than guesswork.                                           |
| 9     | **R5** Capture GPS accuracy and heading      | Shipped                      | Telemetry not recorded on the night is lost forever. The only post-game item with a real deadline. Both halves in, plus a map of each shot in the review queue. |
| 10    | **R3** Screen Wake Lock                     | Shipped 28 Aug               | Mounted unconditionally in user mode, no toggle — the phone's own button is the off switch.                    |
| 10b   | **R7** Reference photo as a kit check       | Shipped 27 Aug               | The manual gate needs no software; the vision dry run does. Upside only — the door check happens either way.   |
| 10c   | **R9** Manual pass through every feature    | **~7–17 Sept**                | Everything above this line has agent tests, not a human's thumbs. Last gate before the print run and the night. |
| —     | *— the game —*                              | **19 Sept**                  |                                                                                                                |
| 11    | **#1** "CharlesBot", not "AI"               | Shipped 28 Aug               | Every user-facing string renamed; `ai_*` fields and columns kept, with a boundary comment at each site.        |
| 12    | **R2** Adjudication scorecard               | —                            | The full version of R1; the game itself generates the data it needs.                                           |
| 14    | **#3** Ranked candidates in the review UI   | Shipped 28 Aug               | The surface of #5, computed at read time so identity corrections need no rewrite of history.                   |
| 15    | **#2** "CharlesBot thinks: hit on *name*"   | Shipped 28 Aug               | Shipped alongside #3; the player-facing history names the target too (open question 1, answered).              |
| 15b   | **R8** Players appeal, admin sees only the contested | Shipped 28 Aug        | The structural fix rather than another accuracy point: makes auto-actions recoverable instead of a bet, and lifts the one-admin ceiling. Shipped off by default (`ai_resolve_everything_enabled`). |
| 16    | **#13** Higher-resolution capture           | —                            | Promoted: with #14 parked this is the *only* route to better photos, and #4, #5 and #11 all want them.         |
| 17    | **R4** Service worker and Web Push          | —                            | The notification half of what the native app was for, at no cost. Largest single win available to the web app. |
| 18    | **#11** Escalation to a stronger model      | Shipped                      | Shipped 2026-08-27; see the entry for the decisions taken on the open questions.                               |
| —     | **#14** Native app                          | **Parked**                   | Decided against: the Apple fee is unavoidable for iOS in any form. Analysis kept for whenever it is revisited. |

---

## Decisions taken

Recorded here so they are not re-litigated:

- **The game is on 19 September 2026, in Westminster.** House Absolute is in
  Westminster, so #6, #7 and #12 are all the same venue.
- **We provide the armbands and the hats** (#9); both have been bought. Only
  the t-shirt and trousers are the player's own. See #9 for what that costs
  and what to do about it.
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
  to the armbands. We now buy and supply each team's hats outright (#9), rather
  than leaving that to the team, so the armband stays the free per-player
  channel we set on the night — for a stronger reason than originally argued,
  since we control the hat colour directly instead of trusting a team's bulk
  order to get it right. See #9 and plan §12.6 — no code change, `TEAM_CHANNEL`
  is already `"hat"`.
- **Auto-actions must work on the night.** They are the point of the recognition
  work, not a bonus. This promotes **#5** onto the critical path, because the
  code-decode path in `slot_candidates_from_review` cannot see a player who is
  not wearing their exact codeword — which, with overrides or free choice, is
  most of them.
- **Players choose their own outfit from a ranked, paginated list** (#10),
  gated on Hamming distance (the scheme's nominal minimum, `d >= 3`, against
  everyone already placed in the whole game — relaxed to `d >= 2` only once
  the player confirms they have no more clothes) rather than auto-seated by
  the backend or restricted to a canonical slot. Canonical Reed–Solomon
  codewords rank at the top of the list, so most players land on one with no
  overrides at all. See plan §12.6's "as implemented" note and the #10 entry
  below for the ranking rule.
- **The trousers channel carries seven colours**, up from five, so the scheme
  offers 48 usable slots instead of 34. The guest list outgrew the 35 identities
  the restriction allowed, and widening it is the remedy plan §2.6 and §11.1
  both name. The seven are a **separately simulated set for legs** — black,
  grey, off-white, blue, red, olive, mustard — sharing only `black` with the
  main palette, hex and all. Three achromatics spread across the lightness range
  (L\* 11 / 54 / 94) and four chromatics spread around the hue circle, so the
  neutrals are told apart by lightness alone, which survives the colour cast
  that would wreck a hue judgement. See plan §9.1 for the table and the
  reasoning.
- **Three of the four channels carry a palette of their own** — trousers by
  design, hat and armbands because that kit was bought and measured (R6, plan
  §9.1a). Only the t-shirt still wears the main palette.
- **Colour definitions are per channel** (`COLOUR_BUCKETS`), because the
  vocabularies genuinely disagree: charcoal is `black` on the legs, where grey
  is two stops away, and explicitly not black on a top, where there is no grey
  to catch it. The picking page and the vision prompt both render each channel's
  own — the prompt inside that channel's question rather than in one shared
  list, which could not state both. Keep them reading the same source: the
  identification scores a player's answer against the model's, so the two have
  to mean the same thing by a colour name.
- **Pub and drop locations live in the repo** as venue landmarks (#6, #7). The
  repository is public, so this publishes every hiding place to anyone who
  thinks to look; accepted deliberately on the grounds that this is a game
  between friends and the alternative is a second place to keep things in sync.

---

## Track B — the critical path

### #9 — Buy armbands and hats *(bought)*

**The constraint.** The palettes in `backend/identity/config.py` were chosen by
optimising worst-case CIEDE2000 separation across three illuminants (daylight,
warm-white LED, sodium street lighting) — see plan §9.1 and §12.4. Substituting
"close enough" colours because that is what was in stock erodes the property the
whole scheme rests on. Buy against the hex values, and where a real product
misses, **record what was actually bought** so the palette can be re-checked
rather than silently drifting.

**Bought: 7 armband colours plus 7 hat colours.** The original plan here was to
supply the armbands only and leave hats to each team to bulk-buy; that changed
before ordering, and we bought the hats ourselves too. Only the t-shirt and
trousers remain the player's own.

**What arrived is not what was specified**, and the config now says so. Neither
set matches the simulated main palette: the hats are muted and earthy (black,
navy, green, burgundy, rust, tan, salmon — no purple, no yellow, no bright
primary red) and the armbands are a rainbow with a brown and a lime in it and
no black at all. Both are seven, which is what the arithmetic needs, so nothing
downstream had to change. The colours were measured off photographs of the kit
and written into `CHANNEL_PALETTES` / `PALETTE_HEX` on 29 Aug — see R6 and plan
§9.1a.

**Why the hat channel matters.** `backend/identity/allocation.py` spends the
hat channel (`TEAM_CHANNEL`) on telling teams apart by eye: every member of a
team gets the same hat colour and no two teams share one. That only works if
people turn up wearing a hat in the exact colour their team was allocated —
which is exactly why we now hand the hats out ourselves rather than leave it
to each team to buy correctly.

**`TEAM_CHANNEL` stays on the hat.** An earlier draft of this section had
argued for moving it to the armbands, on the grounds that the armbands are the
one garment we control; a later draft reversed that back onto the hat, with
each team bulk-buying its own hat colour to get there. Buying the hats
ourselves removes the weak link in that second plan — a team's bulk order can
no longer come out wrong — but the underlying argument for keeping
`TEAM_CHANNEL` on the hat is unchanged, and the numbers in plan §12.6 still
support it:

- **It does not buy more outfits.** The code is MDS with `k = 2`, so any two
  garments determine the other two. Pinning *any* channel to the team leaves
  exactly one bucket of seven slots (six for whichever colour is symbol 0, since
  slot 0 is never handed out) — identical for hat, t-shirt and armbands. The team-channel choice does not change capacity at all.
- **It decides which garments a player has to source.** With the team on the
  armbands, the slots in a team each need a *different* hat colour, and
  almost nobody owns a coloured hat. With the team on the hat, the hat is ours
  to hand out — one colour per team — and the player sources only a t-shirt and
  trousers, which are things people own.
- **It is the difference between having a free channel and not having one.**
  Teammates share the team colour, so if that colour is the armbands, then within
  a team we have *no* channel left that we control — nothing to turn at handout
  time to separate two players whose wardrobes collide. Putting the team on the
  hat keeps the armband as a per-player variable we set on the night. That is the
  real value of controlling the armbands: not more slots, but a knob that still
  turns after everyone has chosen.

Measured (§12.6): with the team on the armbands, a player can fully wear ~0.06 of
their team's free slots and 46% wear at most one of their three garments as
recorded. With the team on the hat, that becomes ~0.56 and 10%. Those figures
were modelled against a team *bulk-buying* its own hat colour; buying the hats
ourselves removes even the residual risk that model priced in — there is no
"wrong hat colour" outcome left to have.

**No code change is needed** — `TEAM_CHANNEL` is already `"hat"`. What changed
was the shopping list: seven armband colours and one hat colour per team, all
bought by us rather than left to the teams.

**Risk to name out loud:** two of the four channels remain bring-your-own —
t-shirt and trousers — and the hat and armbands are both ours now. The
scheme's accuracy on the night still depends on players owning and wearing the
t-shirt and trousers they picked. #10 is the mitigation, and R7 is the check
that it worked.

---

### R6 — Check the kit colours against the palette when they arrive *(done, 29 Aug)*

**Status: delivered, photographed, measured, and written into the config.** The
worry was right: the dye is nowhere near the hex values the kit was bought
against, and neither set is the main palette any more.

`hat` and `armbands` now have palettes of their own in `CHANNEL_PALETTES`,
alongside the trousers, with hexes measured off the objects — each photograph
white-balanced against the paper in its own frame, exposure-normalised per
object against the local paper luminance (the phone torch falls off by 1.5–2.4×
across a frame), and validated by laying each recorded swatch back over the
corrected photograph. Names were chosen for what a stranger would
call the thing, since a player and the vision model have to mean the same by
them, and `COLOUR_BUCKETS` gained an entry for each channel — the hat's earns
its keep, because burgundy, rust and salmon are three warm reds that a loose
definition would let collapse into one another.

**What is still uncertain.** Both photographs were lit by a phone torch, which
is a low-CRI LED: white-balancing on the paper removes the cast but not the
spectral distortion, which bites hardest on saturated dyes. The neutrals and
mid-tones are solid; **the burgundy cap especially, then rust, salmon and the
armband red, are good to a few ΔE rather than exact.** A daylight re-photograph
of both sets would settle it — worth doing before the 19th if the swatches on
`/pick` are going to be trusted at a glance, not worth blocking anything on.
(The other thing the analysis turned up: in the hats photograph the paper around
the pile carries measurable bounce from the warm caps — warmth tracks proximity
to a warm cap at r = −0.58 and paper brightness at r = 0.00 — so the white
reference is the median over all the paper in the frame, not the leaflet next to
the kit, which would have over-corrected the whole frame cyan. Plan §9.1a has
the numbers.)

**What it cost.** Minimum ΔE2000 within a channel under D65: t-shirt 31.4,
trousers 21.4, armbands 21.4, **hat 14.2** (burgundy/rust). The hat is now the
weakest channel in the scheme — half the margin the main palette was optimised
to, and roughly level with the trousers once a warm or sodium cast is applied.
`d = 3` corrects a single misread outright and the hat is the *team* channel, so
a confusion is between teams rather than within one; it is survivable, but it is
the first place to look if identification underperforms on the night.

**Landed in:** `backend/identity/config.py` (`HAT_PALETTE`, `ARMBANDS_PALETTE`,
`CHANNEL_PALETTES`, `PALETTE_HEX`, `COLOUR_BUCKETS`, `COLOUR_COMMONNESS`), plus
plan §9.1a, §11.1's codebook table, and the tests and frontend fixtures that
spelled an old colour name.

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

**The data half is done (28 Aug).** The Takeout export turned out not to
contain the list — custom Maps lists come under the separate "Saved" product,
and even then the Norbiton list was not among them; seven Westminster pubs sat
at the top of the default list instead. Rather than rely on that, everything
licensed within 1.5 km of House Absolute was pulled from OpenStreetMap and
ranked by distance: 98 pubs and 48 bars. The ten inside the #12 crop are now
landmarks on the Westminster venue.

**What is still open is the part that was always the gate:** no landlord has
been asked yet, and no opening hours are recorded. Getting a yes from four
pubs is still worth more than a longer list.

**Lands in:** `backend/venues.py` as landmarks on the Westminster venue.
**Feeds:** #8, #12.

---

### #12 — Redraw the map for Westminster *(shipped)*

**Shipped 28 Aug.** `ACTIVE_VENUE` is `VENUES["westminster"]`; the resort test
venue is retired to a commented-out line beside Kingston, and its `TODO` is
gone. **The game could be played on this.**

**The play area is now defined**, which was the part that mattered more than
the drawing. Three constraints fix it: House Absolute at the exact centre, the
crop symmetric about it, and Big Ben inside the frame. Big Ben is 537 m north
of the house, so symmetry forces a half-span of at least that; 650 m leaves
room to draw the tower. That gives **1300 × 1300 m**, close to the Kingston
map's 1153 × 1116 m, with corners at 51.501752, −0.140302 and 51.489995,
−0.121544. House Absolute lands on pixel (512, 512) of 1024.

**How the map was made.** OpenStreetMap tiles were stitched and cropped to that
box, then reduced to a road-and-river skeleton with the pubs marked, and an
image model was asked to redraw *that* in the Kingston style. The framing was
preserved, so the reference points are the crop's own corners — exact by
construction rather than measured off the drawing.

The thing that made it work was framing the request as **tracing rather than
illustration**. A first attempt that was asked to draw Westminster from the
same references composed a plausible-looking map instead: six of ten pubs were
wrong, three by 500–840 m, and the whole central street grid was shuffled. The
attempt that traced the skeleton put every pub within about 20 m. Worth
remembering if this is regenerated: *and* that asking the good result to fix
four small errors caused a full redraw that lost the accuracy again, so
corrections are not free.

**Known limitations**, none of which stop a game:

- 1.27 m/px against Kingston's 0.51, so `corner_width_km` is 0.2 rather than
  0.115 — a tighter window would just show blur.
- Westminster Abbey is drawn ~100 m south-west of where it belongs.
- One street label reads "Great Peter Street" where it should say "Great Smith
  Street"; The Speaker's own street is unlabelled.

**Still wanted: a hand-drawn map**, in Charles's own hand rather than a
model's. Now a nice-to-have rather than a blocker — it can drop straight into
the same venue if it keeps the framing, since the reference points are the
crop corners. **Lower priority than anything with a date on it.**

**Landmarks** are the ten surveyed pubs inside the crop, plus House Absolute,
Big Ben, Westminster Abbey and Parliament — everything actually drawn on the
map, so an admin cannot place a circle somewhere invisible.

A test now checks the other half of a venue that Python could not see for
itself: that `VenueMap.image` names a key `react-ui/src/mapImages.js` actually
bundles. Getting that wrong means no map at all, discovered at game time.

---

### #10 — Let players pick their own colours *(shipped)*

**Shipped** as `backend/identity/config.py` (`PROVIDED_CHANNEL`,
`COLOUR_COMMONNESS`, `commonness_for`), `backend/identity/allocation.py`
(`assign_team_colours`, `colour_capacity`), `backend/model.py`
(`Team.identity_colour`, `User.identity_wardrobe`), `backend/join_codes.py`
(`slot` now optional — `None` marks a *team* code — plus
`make_team_join_url`), `backend/identity_admin.py` (`build_join_codes`
rewritten, `outfit_options`, `join_options`, `outfit_options_page`,
`pick_outfit`, `clear_identity`), the new `GET /join_options` /
`POST /outfit_options` / `POST /pick_outfit` / `POST /admin_clear_identity`
endpoints in `backend/main.py`, and the player-facing page at
`react-ui/src/PickOutfit.js` (route `/pick`), sharing the extracted
`react-ui/src/Swatch.js` with `AdminIdentity.js`.

**How the design differs from what this entry used to say.** The rest of
this entry, kept below for the "before" picture, said the backend would
**auto-seat** a player "on the outfit that is as far as possible from
everyone already placed" — that is not what shipped, and the description is
corrected here rather than left standing. What actually happens: the player
is offered a **ranked, paginated list of outfits and picks one themselves**.
An option must be wearable from the colours the player ticked and clear a
**hard Hamming-distance gate** — the scheme's nominal minimum distance
against every other placed player in the *whole game*, not just the team
(inside a team this costs nothing; plan §12.6 shows the team partition
already caps a team at the code's own per-colour capacity), relaxed by one
once the player confirms "I'm sure I don't have any more clothes". Survivors
are then ranked **overrides needed from a canonical Reed–Solomon codeword
first (ascending), rarity second** (descending, summed `1 - commonness` over
the player's own t-shirt/trousers channels only — the hat is fixed and the
armband is ours). Distance from a canonical codeword beats rarity absolutely,
so most players land on an unclaimed codeword carrying no overrides at all,
and free choice is graceful degradation rather than the norm. See
`backend.identity_admin.outfit_options` for the implementation and plan
§12.6's "as implemented" note for the reasoning.

**The page only asks about what the player actually sources.** The hat and
armbands are ours (#9), not the player's choice, so the picking page shows and
ticks colours for the t-shirt and trousers only — the two garments a player
needs to go and find.

**Two risks worth naming that the rest of this entry doesn't:**

- **Slots remain the real ceiling.** 48 usable slots
  (`IdentityScheme.usable_slots`) — it was 34 until the guest list outgrew the
  five-colour trousers palette and that channel joined the main one (plan §2.6)
  — so the game caps there regardless of how generous anyone's wardrobe is.
- **The team join code is a shareable bearer token.** One link per team means
  one leaked link can burn every outfit in that team, not just one —
  `/join_game`'s older per-slot code had this property per outfit; pooling by
  team widens the blast radius.

**Current state, before this shipped.** `identity_admin.build_join_codes(game_id, slots_per_team)`
pre-allocated a block of slots per team (one team-channel colour each, via
`allocation.allocate_team_slots`) and minted one signed join URL **per
slot**; `claim_join_slot()` claimed whatever slot the scanned code carried.
So a player was handed an outfit; they did not choose one.

**What the page needed, and delivered:**

- the team's *unclaimed* outfits rendered with colour swatches — reusing
  `hex_for()` and the swatch rendering already proven in `AdminIdentity.js` /
  `IdentityDemo.js` (now the shared `Swatch.js`);
- an explanation that the hat and armbands are ours (see #9) and the choice is
  across the t-shirt and trousers;
- an **atomic** claim, guarded by `identity_admin.pick_outfit_lock` plus
  re-validation against freshly read state: several people pick at once on
  their phones, and two players must never end up wearing the same codeword;
- it works **before the night** and before anybody has a `User` row — plan
  §8.2 is explicit about this, and `join_options` deliberately creates no
  `User` row so a link-preview bot prefetching the URL can't burn an outfit.

**Self-selection is load-bearing, not a nicety.** With the hat and armbands
provided (#9), two channels still depend on players owning the right colours.
Letting someone choose the outfit whose t-shirt and trousers they *already
have* is the single best lever on how accurate the identification is on the
night. So the page is built around "which of these can you actually
wear on Saturday", not "which is prettiest".

**Depended on #5, now shipped.** Freely chosen outfits are not codewords, so
the code-decode path in `shot_vision.slot_candidates_from_review` cannot
identify their wearers — and can confidently identify the *wrong* one.
Auto-actions are required on the night, so #5 shipped first.

**Each player confirms they have the garments** before picking, via an "I
will wear this on the night" checkbox - moved, after a mobile walkthrough,
from gating "show me outfits" (committing before seeing what you're
committing to) to a dedicated confirm screen shown after tapping an option
and before it's claimed, with a "choose a different outfit" way back.
Players are **not** asked to photograph themselves: that is deliberately
deferred to R7, where the admin takes the photo at the door on the night. A
self-taken photo verifies nothing, because the person submitting it is the
person with a reason to fudge it.

**Post-ship UX revision (mobile walkthrough).** Four further fixes beyond
the confirm-step move above, all in `react-ui/src/PickOutfit.js` /
`backend/identity_admin.py`: (1) `outfit_options` now collapses to one
option per distinct tshirt+trousers combination - the armband varying
underneath was a choice the player has no stake in, since it's ours to
assign - keeping `outfit_options_page`'s `total`/pagination honest against
the smaller, deduplicated list; (2) option rows, the confirm screen and the
result screen now show only the wardrobe channels (`join_options`'
`wardrobe_channels`), dropping the hat/armband and the "yours"/"ours" tags
they needed; (3) the wardrobe form collapses to a one-line summary once
options are showing, so a phone screen reaches the options without first
scrolling past every colour swatch, with a "Change what I own" link back;
(4) the options list now shows **only the canonical options** (the ranking's
top tier), with the rest - and the pagination - behind a "Show more
outfits" link. Showing both tiers together invited a player to spend
identification accuracy on whichever colours they liked the look of; a
canonical outfit is still one tap away and the long tail takes a deliberate
one. Frontend-only: `outfit_options` still returns the full ranked list, and
a wardrobe supporting no canonical option at all falls back to showing
everything rather than an empty page.

**Badging revision.** The green "recommended" badge no longer marks every
canonical option - only the head of the first page, plus anything tying with
it on rarity (the ranking's tie-break within the canonical tier), so the
badge points at *the* best outfit rather than a dozen equally-badged ones.
The remaining canonical options go unbadged, and the non-canonical ones
revealed by "Show more outfits" carry an orange "not ideal" badge instead.

**A name is now required to claim an outfit.** The name box was on the page
from the start but gated nothing, and `NameEntry` posted `set_name` without
telling the page - so a player could lock in an outfit anonymously, leaving a
slot claimed that #8 has no card to print a name on. The name is now tracked
in `PickOutfitForm` (seeded from `join_options`' `you.name`, updated by
`NameEntry`'s new optional `onNameSet` callback), the box follows the player
onto the confirm screen, and "Lock in my choice" stays disabled until both it
and the checkbox are satisfied. `NameEntry` also no longer posts a
whitespace-only name, in `OnboardingView` as well as here.

**The box stays visible and editable, always - it no longer hides itself once
a name is known.** `join_options` only ever reports a name for a player an
admin has already added to the team ahead of picking (`team_id` and
`identity_slot` are otherwise set together, atomically, by `pick_outfit`
alone) - a real but uncommon case, and one worth showing correctly: the box
pre-fills from that name rather than reappearing blank and asking again, and
stays open to a correction the whole way through, including on the confirm
screen.

**Depends on:** #9 (both the kit and the `TEAM_CHANNEL` move, shipped).
**Feeds:** #8.

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

**Unblocked (28 Aug):** #12 has shipped, so the game area is now a definite
1300 x 1300 m square centred on House Absolute, and `VenueMap.bounds` will tell
you whether a candidate drop is inside it. Note how much of Westminster the
security-sensitive exclusion removes from that square: Parliament, the Abbey
and the Millbank government blocks are most of the eastern half.

**Lands in:** `backend/venues.py` as landmarks. **Depends on:** #12 *(done)*.
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
3. **Player appearance cards** (#10, shipped) — what to wear, per player, plus
   their join code. Each player already knows this, having picked it via
   `/pick`; the print step reads it off each player's picked
   `effective_appearance` (the same shape `admin_identity_report` returns),
   not from `build_join_codes` — that now mints one code per *team*, not one
   appearance per slot.

**If the schedule slips**, the drop codes are the ones with a hard dependency on
physical placement; the appearance cards can be sent digitally as a fallback,
since by then #10 has already told each player what they are wearing.

---

### R9 — Manual human pass through every feature shipped this year *(proposed)*

**Why this is its own item.** Everything above this line has been built,
reviewed and (mostly) covered by automated tests by agents working from a
diff, never by a person clicking through the app end to end. `pytest` and
`npm test` catch regressions in logic; they do not catch a button that is
unreachable on a real phone, a flow that makes sense to the person who wrote
it and nobody else, or a feature two people built against slightly different
assumptions about how it fits with a third. Agents can (and should) run
through this list first — see below — but a **manual pass by a human**,
ideally Charles on his own phone, is the pre-game gate this item tracks. It
is the last line of defence between "it works in CI" and "it works at
House Absolute."

**What "done" means.** Every feature below has been used, on a real mobile
viewport, by a human, at least once — not read, not diffed, used — and any
bug found either fixed or written down as a known issue with a decision
about whether it blocks the 19th.

**The list below is not final.** It is every player- or admin-facing feature
that shipped between **1 January 2026** and the day this item was written
(28 Aug 2026), grouped by area rather than by roadmap item number since
several roadmap items landed as a run of small commits rather than one
feature. **More will ship before the 19th** — most pressingly #7/#8 (drop
locations and the print run) and whatever #4/#5 follow-up work turns up —
so treat this as a checklist to extend, not a closed list to work through
once. Add a line here whenever something new lands, the same way the rest of
this file is kept current.

**Player-facing:**

- [ ] Join a team via QR/link and pick an outfit at `/pick` (#10): ranked
  outfit list, canonical-first ordering, colour swatches, pagination.
- [ ] The "recommended" vs "not ideal" outfit badges and the "show
  non-recommended outfits" reveal link.
- [ ] The name-then-confirm flow — entering a name, seeing the committed
  outfit, and the outfit becoming locked in.
- [ ] An admin clearing a player's outfit so they can pick again.
- [ ] Scanning a loot QR code to pick up an item, and using it (weapons,
  armour, ammo, medpacks).
- [ ] Taking a shot photo of another player, including the on-screen
  crosshair overlay.
- [ ] The shot status bubble after taking a shot — every visual state it can
  be in, and that it stays on screen rather than disappearing.
- [ ] The screen staying awake during play (R3 — Screen Wake Lock), and that
  the phone's own lock button still turns the screen off on request.
- [ ] Appealing a resolved shot as either shooter or target (R8), including
  seeing the appeal budget run out.
- [ ] The map view, including drop/circle locations on the live Westminster
  venue map (#12).
- [ ] The ticker feed for game announcements.
- [ ] User-facing copy says "CharlesBot", never "AI", anywhere a verdict or
  explanation is shown (#1, #2 — "CharlesBot thinks: hit on *name*").

**Admin-facing:**

- [ ] The reference-photo kit check at `/admin/reference` (R7): reading off the
  hat and armband colours to hand out, capturing a player's photo at the door
  and reading the resulting verdict — including the "unreadable photo
  identifies nobody" case and the expected-against-read comparison naming the
  garment that is wrong.
- [ ] The shot review queue: ranked candidate list per shot (#3), CharlesBot's
  verdict and confidence, the AI vision zoom usage indicator, and manually
  approving/rejecting a shot.
- [ ] Toggling `ai_shot_review_enabled`, `ai_auto_actions_enabled`,
  `ai_escalation_enabled` and `ai_resolve_everything_enabled`, and confirming
  each one actually changes queue behaviour (not just the toggle state).
- [ ] Not re-reviewing an already-reviewed shot when the AI toggle is
  switched on and off again.
- [ ] Running an escalated review by hand on a shot (#11 — "Run escalated
  review").
- [ ] The contested-shots list an appeal reopens (R8), separate from the main
  queue.
- [ ] Recording a "hit a bystander" outcome on a shot.
- [ ] The per-shot map (R5) showing GPS accuracy and the shooter's compass
  heading.
- [ ] Admin shot history and notes on a player.
- [ ] The identity workbench / `AdminIdentity.js`: viewing a player's
  effective appearance and any overrides, and recording an override for a
  misdressed player so they stay distinguishable from their teammates.
- [ ] Renaming a team from the admin dashboard.
- [ ] Downloading all shot images as a zip.
- [ ] The admin nav (finger-sized button row) on a real phone screen, not
  just a desktop browser.
- [ ] The running app version shown on admin pages, and that it matches what
  is actually deployed.
- [ ] The replay workbench at `/admin/replay` (R1) — trialling a prompt/zoom/
  schema change against real shots without it touching stored data.

**Cuts across both:** confirm the game can be reset (`resetdb`) and replayed
from a clean state without any of the above breaking, since that is exactly
what happens between the dry run and the night itself.

**Who does what.** Agents can and should run through the player- and
admin-facing flows first, in a browser at a mobile viewport (see the
`run-mobile-app` skill), to catch anything broken before a human's time is
spent on it. That is preparation, not a substitute: the actual gate is
Charles doing the same pass by hand on his own phone, because an agent
cannot judge "does this make sense to someone who has never seen it before"
or "is this button reachable one-handed with a box of armbands in the other."

**Lands in:** no code — this is a QA pass, tracked here so it does not get
silently skipped under the logistics deadlines above it.
**Depends on:** effectively everything shipped above; best done once #10 is
live to real players (~7 Sept) and again closer to the 19th if anything
changes.

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
question in the 2026-08-24 handover — answered since: #11 retired the
mapping), not a prompt problem.
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

**Reasoning-continuity bug fixed (2026-08-26):** surfacing the trace for
display exposed a real bug in the pipeline itself -- the screening -> zoom ->
full-reading loop re-sent only each turn's bare parsed JSON as the assistant's
prior turn, never the reasoning that produced it. Per OpenRouter's own
guidance, a "thinking" model needs its `reasoning_details` (its
provider-independent, pass-back-verbatim structured form -- some providers'
blocks are encrypted, so this is not the same as the human-readable
`reasoning` string above) fed back on the next turn's assistant message to
continue reasoning from where it left off; without it, every turn after the
first re-reasons from nothing but the previous turn's bare verdict, which
measurably degrades multi-turn (zoomed) cases. `VisionClient` gained
`last_reasoning_details`, `shot_vision.review_image` now threads it into
each follow-up turn via `_previous_answer_turn`, and `_as_message` passes it
through to OpenRouter unmodified.

**Reasoning-effort knob added, and measured (2026-08-26).** Looking at a real
production shot's transcript raised a further question: the displayed
reasoning read as if it decided the hit, then filled in colours with no
visible deliberation. Live calls through the real pipeline (screening-gated,
`google/gemini-3.7-flash-20260813`) confirmed this is genuine, unrelated to
the bug above -- Gemini's `reasoning` is a short **thought summary** (Google's
term: a synopsis, not the raw chain-of-thought), and its length tracked
`usage.completion_tokens_details.reasoning_tokens` exactly on every call, so
nothing was being truncated in flight. `OPENROUTER_REASONING_EFFORT`
(`none`/`minimal`/`low`/`medium`/`high`/`xhigh`/`max`) now requests a deeper
one via OpenRouter's `reasoning: {"effort": ...}` parameter -- unset by
default (identical behaviour to before), overridable per replay in the
workbench regardless of the env setting.

Measured on 3 fixture shots (one each of miss/hit/bystander ground truth),
gated flow, Gemini only, one run per effort level:

| effort | final-turn reasoning chars (3 shots) | verdict vs. `unset` |
| --- | --- | --- |
| unset | 219 / 355 / 259 | -- |
| low | 0 / 0 / 0 | same outcome every time |
| medium | 238 / 319 / 485 | same outcome every time |
| high | 485 / 1465 / 1855 | same outcome every time |

Two findings, both from real data, not the 3-shot sample size: **`low` is
worse than doing nothing** -- it suppressed the visible summary to zero chars
on every single call while still spending real `reasoning_tokens` (72-271)
computing it, so if transparency is the goal, never configure `low`. **`high`
gives the long, multi-paragraph, per-channel deliberation** the admin UI was
missing (2-6x `unset`'s length), at a modest cost increase (~$0.006-0.008 vs
~$0.005-0.008 per shot review, all three calls). None of the three shots'
*verdicts* changed across any effort level -- one (`697899ee`, a hit
misread as `hit_bystander`) stayed wrong at every level, so effort is a
narration-depth and transparency knob here, not a demonstrated accuracy fix;
that needs the full replay-set treatment (R1) to say anything at N > 3.

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

**The custom prompt was being overruled — fixed (2026-08-27).** The workbench
let you edit the prompt, and only the prompt: the schemas the model was asked
for and the follow-up turns between them stayed the pipeline's own. So a
prompt asking for something else — say, pixel coordinates for each garment —
was sent, and then answered against `build_screening_schema()`
(`{"person_fills_less_than_half": …}`), followed up with "answer in full with
the JSON described above", and finally forced into `build_schema()`'s four
channels. The transcript looked as if the custom prompt had never been sent,
because structurally it had not been: a model can only answer the question its
schema asks.

The contract is now three things that travel together —
`shot_vision.review_image` takes a `zoom_mode` (`ZOOM_SCREENED`, the live
shape, `ZOOM_UPFRONT`, both views in one call, or `ZOOM_SINGLE`, one turn with
no screening and no zoom) and a `schema` override alongside `prompt`, and
`build_prompt(zoom_mode=…)` writes the zoom wording that matches the shape
about to be run. `always_zoom: bool` is gone, replaced by `zoom_mode`
throughout (`PROMPT_VARIANTS["always_zoom"]` keeps its name, since that is
what the `replay_always_zoom_run*.jsonl` files record). The workbench gained a
schema box and a conversation-shape selector; changing the shape reseeds an
*untouched* prompt so it never describes an exchange that is not about to
happen, and leaves an edited one alone. Replays also stopped 502-ing on a
reply that is not a standard reading: `review_image(tolerate_unparsed=True)`
returns it as `raw_reply` + `parse_error` and the workbench renders it, since
under a contract of its own that is the answer rather than a failure. Live
reviews still raise — storing a meaningless verdict is worse than erroring.

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
in `backend/shot_auto_actions.py` rewired onto it. The admin-facing surface,
#3, has since shipped too (28 Aug): the queue UI now shows the ranking and
the runners-up, not just the old tags.

**Fixed 29 Aug — a lone candidate was the strictest case, not the loosest.**
`_rank` passes the candidates' *own* effective minimum distance as the
correction radius, because a freely-chosen outfit is not a codeword. With one
candidate there are no pairs, and it passed `None` — which `decode()` reads as
"flag anything that is not an exact match". So in a two-player test game a
single misread garment, exactly the error `d = 3` exists to correct, came back
`inconsistent`, the shot showed "The reading fits nobody cleanly", and the
auto-action gate refused it in both modes (an inconsistent reading is one of
the three "resolve everything" never forces). The empty minimum is now the
code's nominal `d`: with nobody to confuse the candidate with, that is the
radius that applies. Two misreads still read as inconsistent.


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
  candidate set is not the 48 usable slots, it is the handful of living players
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
today and both unrecoverable after the fact. Written up as **R5**, which had to
happen before the 19th for that reason — and has now shipped, so both are
being recorded (`User.location_accuracy`, `Shot.heading`) and are waiting here
for whoever builds this model.

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

### #3 — Show the ranked candidates in the admin review UI *(shipped)*

**Shipped 28 Aug** as `identification_payload` in
`backend/shot_identification.py`, attached at read time to
`admin_get_shot_ai_review` — never stored, so an identity correction is
reflected without rewriting history. Per-candidate code distance comes from
the decoder's own `_hamming_distance`, and a zero-readable-channels reading
gets the same guard R7's reference photos use. Frontend: `RankedCandidates`
in `react-ui/src/ShotQueue.js` replaces the GPS-only `NearestPlayers` list —
name, team, posterior, code distance and metres (the last still joined
client-side); ambiguous, inconsistent and unreadable readings each say so in
words, in amber, rather than leaving the admin to infer it from an empty
table.

The original brief follows.

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

### #2 — "CharlesBot thinks this is a hit on *Alice*" *(shipped)*

**Shipped 28 Aug**, alongside #3: `charlesBotVerdict` in
`react-ui/src/ShotQueue.js` implements this entry's wording ladder for the
admin, resolving the stored review's slot to a name server-side at read
time so a later identity correction is reflected without rewriting history.
On the player side, `get_own_shots` grew `ai_target_name`, named only when
the ranking clears the same confident/unambiguous/consistent bar the
auto-action drain itself requires; the player's shot history reads
"CharlesBot thinks: hit on X" or "hit — can't tell who" accordingly. **Open
question 1 is answered: yes**, the player-facing history does name the
target — decided alongside R8, which needs both parties to see enough to
appeal a verdict they were never otherwise told.

The original brief follows.

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

### #1 — Call it "CharlesBot", not "AI" *(shipped)*

**Shipped 28 Aug**, exactly as this entry prescribed: every user-facing
display string renamed (`ShotQueue.js`, `ShotHistory.js`, `AdminMode.js`'s
toggle labels, `ShotReplay.js`, and the tests asserting on those strings).
API fields, database columns and module names keep their `ai_*` names —
renaming them would have invalidated stored review payloads for nothing —
with a boundary comment at each site recording that "CharlesBot" is the
display name for what the code calls `ai_review`.

The original brief follows.

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

### #11 — Escalate the hard cases to a stronger model *(shipped)*

**Shipped 2026-08-27** as `backend/shot_escalation.py` (the escalation
contract and the async runner, mirroring `ai_shot_review.py`), the rewritten
`classify()` in `backend/shot_vision.py` (the "no armbands ⇒ bystander"
mapping is retired: a shot that hit a person is always `hit_player` now, with
the readable-channel count in the reason — bystander is a conclusion only the
stronger model or the admin can reach), the ladder in
`backend/shot_auto_actions._decide` (gated on `confident_channel_count` and
the new `shot_vision.armbands_confident`), `vision_client.
get_escalation_client()` (`OPENROUTER_ESCALATION_MODEL` — unset means
escalation is off and everything behaves as before), two columns on `Shot`
(`ai_escalation_state`, `ai_escalation`), and the escalation block in the
admin queue (`ShotQueue.js`), which shows the strong model's verdict,
reasoning and the ranked candidate list it was given.

**Widened 29 Aug — the stronger model stands in for the admin.** Charles's
call, after a test shot with one wrong garment colour sat in the queue
un-escalated: *"nothing should ever reach the admin unless it has first passed
through the stronger model"*. The ladder as shipped sorted on how much of the
outfit was legible, so a fully-read but self-contradictory photo — the hardest
case there is — was classified as easy and offered only the top rung's two
exits, auto-resolve or the admin. A merely *shy* reading escalated happily.
Now every way the weak reading fails to settle a shot routes to
`_decide_escalated`: unconfident overall, `inconsistent`, a tie, an
unrecognised outcome, a legacy `hit_bystander`, or too few readable channels.
The readable-channel test survives, but it now decides only whether the weak
reading may name somebody *on its own*. A stored escalation is consulted
before the weak reading is retried, so a manually fired one outranks it. The
admin's door is the stronger model handing the shot back — "unsure", or below
its own thresholds — plus the two absences of a second opinion: an errored
escalation, and no model to ask. `ai_escalation_enabled` is therefore a real
kill switch: off, every uncertainty is the admin's again.

Two consequences worth knowing. Under `ai_resolve_everything_enabled` an
unconfident head now escalates *before* it is forced, since a second opinion
that is actually coming beats a forced guess — `_forced_fallback` fires only
once the stronger model is out of the picture, and it now dispatches on the
weak reading's own outcome rather than always ranking candidates. And the one
case that still cannot escalate is a head with **no usable review at all**
(errored or unparseable), because `shot_escalation._load_context` builds its
candidate ranking from that reading; retries (below) make it rare, and
teaching escalation to run on a flat GPS-only ranking is the open follow-up.

**Retry, 29 Aug.** A vision call that errors or answers off-schema is now
retried up to twice before being stored as an error
(`ai_shot_review.REVIEW_ATTEMPTS = 3`, `_review_with_retries`) — that is
exactly what pressing "re-run review" in the queue did by hand, and it usually
worked. The semaphore is taken per attempt, so a retry queues behind other
shots rather than holding a slot across all three. Escalation calls are *not*
retried yet.

**Decisions taken on the open questions, and along the way:**

- **Storage:** a second column pair on `Shot` (`ai_escalation_state`,
  `ai_escalation`), not folded into `ai_review` — the weak and strong payloads
  stay separately inspectable (R2 will want to score them separately), and the
  queue endpoint (`admin_get_shot_ai_review`) simply grew
  `escalation_state`/`escalation` keys.
- **Queue blocking: yes**, same FIFO discipline as an ambiguous head — a
  pending or punted escalation blocks the shots behind it. A punted shot
  ("unsure", or a verdict below threshold, or an errored call) simply stays
  with the admin, which is where every shot went before any of this existed.
- **What the admin sees for a punted shot:** the strong model's verdict tag
  ("Needs your call"), its reasoning, and the ranked candidates with
  probabilities and whether each one's reference photo was shown — #3's
  surface, fed from the stored escalation payload.
- **The trigger lives in the auto-action drain** (`process_queue_head`), so
  escalation runs only when `ai_auto_actions_enabled` is on, only for the
  queue head, and only when `OPENROUTER_ESCALATION_MODEL` is configured —
  three separate reasons the safety valve survives. The escalated verdict
  re-enters `_decide`: auto-act on a confident player/miss/bystander, admin
  on the human rung.
- **0 or 1 readable channels escalate too**, not just the ladder's "2": the
  old code called those bystanders, which is exactly the retired mapping, and
  the strong model with reference photos can still judge them.
- **The weak model's overall confidence does not gate the escalate rungs**
  (it still gates the auto-eligible ones): the weak model being unsure is
  what escalation is *for*.
- **A re-run of the weak review clears the stored escalation** (storing a
  pending review nulls both columns): a new reading invalidates the old
  escalated verdict, and this doubles as the admin's way to retry an errored
  escalation.
- **Python owns the thresholds**, in `shot_escalation.py`:
  `ESCALATION_HIT_THRESHOLD = 0.75` (a wrong "player X" takes a life; a wrong
  "unsure" costs an admin thirty seconds — so naming a player needs more than
  the generic 0.6) and `ESCALATION_OUTCOME_THRESHOLD = 0.6` for miss and
  bystander (one bullet at stake, same as the weak auto-actions). Both are
  guesses awaiting R2's data.
- **One consequence worth naming:** three readable channels *without*
  armbands used to be able to auto-fire (the old `k + 1` readability gate
  passed); it now escalates instead, so with no escalation model configured
  those shots go to the admin rather than auto-firing. Deliberate — that rung
  is the one where the missing channel is the player marker.
- **The escalation layer has its own per-game toggle** (`Game.
  ai_escalation_enabled`, third checkbox on the admin game panel): off means
  the escalate rungs go straight to the admin, exactly as if no escalation
  model were configured. Unlike its two siblings it **defaults on** — they
  are the opt-in for the AI features, while this is a kill switch inside an
  already-opted-in feature (escalation only ever runs with auto-actions on
  and `OPENROUTER_ESCALATION_MODEL` set), so configuring the model should be
  enough to get it on the night.
- **The admin can fire an escalation by hand** ("Run escalated review" beside
  "Re-run AI review" in the queue): `admin_escalate_shot` runs whatever the
  toggles say — like `admin_review_shot`, an explicit admin ask — and needs a
  completed weak review to rank from (400 otherwise, and 400 with no
  escalation model configured). A manual run replaces any stored escalation.
- **A hit on an already-dead player is just a hit that does nothing** — never
  an escalation, never the admin's. Dead players stay in the candidate set
  (`eligible_candidates` no longer filters on `hit_points`; a knocked-out
  player is still physically there to be photographed, especially in the
  seconds after the killing shot resolves), so a shot queued behind the one
  that killed its target identifies normally and resolves as a hit — no
  damage, no second knockout announcement (`hit_user` now announces a plain
  hit for an already-dead target, which also fixes the manual admin path's
  double-knockout wart). The prior stays flat for the dead; a death-age
  down-weight is R2-fitting territory.

The original design brief follows.

**Design decided 2026-08-27; reference photos (the prerequisite, R7) are
shipped.** This section is the handoff for the remaining work. The one-line
version: stop treating "no armbands visible" as "bystander", identify with
whatever channels *are* readable at honestly reduced confidence, and route the
cases that reduced confidence cannot carry to a stronger model that sees the
reference photos — with a human admin as the final rung.

**What is wrong today.** `classify()` in `backend/shot_vision.py` uses the
armbands as the player gate: armbands read ⇒ player; armbands hidden ⇒ demand
all three other channels complete to a codeword, else **bystander**. Quite
often no armbands are visible on a genuine hit (all four of #4's residual
false misses are exactly this), and two or three readable channels are enough
information to *guess who it is* — the candidate set is a handful of nearby
living players, not the whole code space (#5's argument). The guess just
deserves much less confidence, and the confidence is what should decide
whether a machine acts on it, not whether the reading is discarded.

**The escalation ladder, by what was readable.** Confidence-gated throughout
(`confident_channel_count` is the existing readable-channel counter):

- **4 channels readable** — as today: identify via #5's posterior;
  auto-actionable when confident.
- **3 channels, armbands among them** — a good candidate for **no** review:
  the armbands are the one garment we supply, so player-ness is solid and one
  erasure is well within the code. Auto-actionable when the posterior is
  confident.
- **3 channels, armbands hidden** — probably **does** need review: identify
  anyway, but the missing channel is the player marker, so send it to the
  stronger model rather than auto-acting.
- **2 channels** (armbands or not) — **always** goes to the stronger model.
  Identification still runs and still produces the ranking (two correct reads
  discriminate sharply within a small candidate set), but at `k = 2` readable
  positions the code itself vouches for nothing, so no auto-action.

Bystander/miss remain possible *conclusions*, but "too few channels" stops
being the *route* to bystander — that mapping in `classify()` is retired.

**The ranking handed up.** The escalation input is #5's ranked posterior over
the game's living candidates, built from whichever channels were readable plus
the GPS location term (`shot_identification.rank_candidates` already computes
exactly this). When R5b's compass heading lands and the engagement envelope
becomes a cone, that folds into the same prior and the escalation inherits it
for free — the contract is simply "players ranked by probability".

**What the stronger model gets.** The full-resolution photo and zoom, the
ranked candidate list with priors and outfits, and the **reference photos of
the top three candidates** attached up front. It does *not* get the weak
model's conclusions — it draws its own from the pixels; the ranking is the
only thing it inherits. It must also be able to **request the reference photo
of any other listed candidate**: keep this model-agnostic by doing it as
another turn in the existing multi-turn shape (the reply schema carries a
`request_reference_photos: [candidate ids]` field and the follow-up turn
supplies the images — the same pattern as the screening/zoom loop), not as
provider tool-calling.

**It must decide, and the fence has a name.** The escalated call returns
exactly one of:

- **a specific player** (with confidence — Python still applies thresholds);
- **miss** — only when the shot genuinely missed;
- **bystander** — only when it genuinely hit a non-player;
- **escalate to the human admin** — the *only* valid answer for "this is a
  player but I cannot tell which". Miss and bystander must never be used as
  a dodge for that case; an undecidable player hit goes to a human, which
  lands the shot back where every shot went before any of this existed: the
  admin queue.

**The pieces, updated:**

**(a) Reference photos — shipped (R7).** Stored per player
(`User.reference_photo_base64`), captured by the admin at the door, already
run through the live vision pipeline as a kit check. The escalation reads
them from there; a game reset deletes them.

**(b) The trigger and the second client.** `backend/vision_client.py` is
model-agnostic and reads `OPENROUTER_MODEL` from the environment, so the
stronger model is a second configured client (e.g. an
`OPENROUTER_ESCALATION_MODEL` env var), not a new integration. The trigger
sits where `classify()`'s outcome meets `shot_auto_actions._decide`: the
ladder above decides auto-act / escalate / admin, and the escalated verdict
re-enters the same gate (auto-act on a confident player/miss/bystander
verdict, admin queue on the human rung). Cap the candidate list sent up by
the GPS-ranked prior (top ~5): every candidate is potentially a reference
photo in the request, and the bill scales with it.

**(c) The prompt is a different question.** The cheap pass asks "what colours
is this person wearing"; the escalation asks "which of these people is this —
or did the shot miss, or hit a non-player, or can you genuinely not tell
which player it is". Same observe-then-decide shape: the model reports its
match and its certainty, Python applies the thresholds and owns the
asymmetries (a wrong "player X" takes a life; a wrong "escalate" costs an
admin thirty seconds).

**Depends on:** #5 (shipped — the posterior is the input), R7 (shipped — the
reference photos), R2 (fits the thresholds), and benefits from #13.
**Open questions for the implementer:** where the escalated verdict is stored
(a second review column on `Shot`, or folded into `ai_review`); whether an
escalated shot blocks the auto-action queue behind it the way an ambiguous
head does today (probably yes — same FIFO discipline); and what the admin
queue shows for a shot the strong model punted (its reasoning and the ranked
list, presumably — that is #3's surface).

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

### R5 — Capture GPS accuracy and compass heading *(shipped)*

**Shipped**, both halves, plus an admin map view that was not in this entry.

- **R5a, accuracy.** `position.coords.accuracy` now rides every location
  upload: `sendLocationUpdate` in `react-ui/src/MapView.js` sends it,
  `set_location` (endpoint in `backend/main.py`, method in
  `backend/user_interface.py`) stores it in the new `User.location_accuracy`,
  and `AdminInterface.get_locations` returns it as `accuracy` — so it is
  inside every shot's `location_context`, which was the step this entry
  warned was the easy one to miss.
- **R5b, heading.** New nullable `Shot.heading` (degrees clockwise from
  north). `react-ui/src/MyWebcam.js` keeps a compass watch running while the
  camera is on screen and reads the latest heading at the moment of capture,
  so firing never waits on a sensor. The platform mess lives in
  `react-ui/src/utils.js` as `watchCompassHeading` /
  `headingFromOrientationEvent` (iOS's `webkitCompassHeading` off the plain
  event; everyone else's `deviceorientationabsolute`, whose `alpha` counts
  the other way), alongside the permission pair
  `isOrientationPermissionGranted` / `requestOrientationPermission` that
  matches the camera and location helpers. iOS's grant cannot be queried
  back, so it is remembered in `localStorage`.
- **The compass rung does not gate the ladder.** `OnboardingView.js` gets its
  third rung, but unlike camera and location it lets the items below it
  through: a phone with no compass, or a player who declines, must still be
  able to finish joining. Same instinct as "it must degrade silently" below —
  a missing heading stores null and the shot proceeds exactly as before.
- **New: the admin can see where a shot was fired from.**
  `react-ui/src/ShotMap.js` draws a thumbnail beside the photo in the shot
  queue: the venue's own map, the shooter's dot, their accuracy circle to
  scale and a cone in the direction they were pointing, with a caption
  (`±17 m · facing 043°`). It reads the shooter's fix straight out of
  `location_context` — the admin shot payload already carried it — and shares
  the georeferencing maths with the player's map through the new
  `mapProjection` in `react-ui/src/venue.js`, which `MapView.js` was rewired
  onto rather than having a second copy. A shot with no fix says so and shows
  nothing, which is what every shot fired before tonight will do.

**Nothing consumes either field yet, and that is deliberate.** The whole point
was to record what could not be recovered afterwards. Identification
(`backend/shot_identification.py`) and everything in `backend/identity/` are
untouched: #5's envelope stays isotropic until there is data to fit the cone
against. The admin map only *displays* the telemetry; no verdict depends on it.

The columns need a `resetdb`, which is free before the game's own reset.

---

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

### R3 — Screen Wake Lock *(shipped)*

**Shipped 28 Aug** as a `useWakeLock` hook, mounted unconditionally in
`UserMode.js` and re-acquiring on `visibilitychange`. **Deliberately no
toggle**: Charles's call was that an extra toggle confuses more than a
battery drain costs, and the phone's own power button is already the way to
turn the screen off if a player wants that.

The original brief follows.

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

### R7 — The reference photo as a kit check, run through the shot AI *(shipped)*

**Shipped 2026-08-27** as `backend/reference_photos.py` (the review runner,
mirroring `ai_shot_review.py` — same live vision contract, never a `Shot`
row), three columns on `User` (`reference_photo_base64`,
`reference_review_state`, `reference_review` — the photo follows
`Shot.image_base64`'s base64-in-a-column pattern),
`shot_identification.rank_reference_candidates` (the same scoring as
`rank_candidates` but flat-priored — no shooter, no location term — over
every placed player in the game), the single-writer accessors and the
game-reset wipe in `backend/admin_interface.py`, the
`admin_capture_reference_photo` / `admin_get_reference_photo` /
`admin_get_reference_review` / `admin_review_reference_photo` /
`admin_delete_reference_photo` / `admin_get_reference_photo_status`
endpoints in `backend/main.py`, and the admin capture page at
`/admin/reference` (`react-ui/src/ReferencePhotos.js`), which shows the
per-channel reads with confidences (a marginal channel is a visible warning)
and whether the photo resolves to the player it was taken of. Capture works
with the vision client unconfigured — the photo stores and the review simply
never runs, so the manual door check can never be blocked by the AI being
off. The review payload carries an `identification` section recording the
ranked candidates and whether the top match is the photographed player; a
game reset deletes the photos, which must not outlive the game.

Amended 2026-08-28 after the first live trial: the posterior is a product of
the prior and the image evidence, so a photograph with every channel erased
(the trial's was of a bare leg) returned the flat prior as a ranking, and the
page printed it as "Recognised as … (p=0.50)" — p=1.00 had the photographed
player been the only one placed. The section now carries
`readable_channels`, and at zero there is no ranking and no
`matches_expected` at all; the page reserves green for a match the decoder
calls confident, and shows everything else amber.

Amended 2026-08-29: the page now says what the player is *expected* to be
wearing, not only what the model made of them. Each
`admin_get_reference_photo_status` row carries an `expected_appearance`
(`identity_admin.expected_outfit` — the effective word, so an override is what
is expected, shaped like a review's `channels` so one component renders both),
and the roster shows it as a swatch strip. In a player's own view it is shown
**before** the camera, split into "hand them" (the hat and the armband, which
`identity_admin.provided_channels` names — the complement of the wardrobe
channels, so the two cannot disagree) and what they should have arrived in:
this is the moment the kit is handed over, so the colours have to be readable
while reaching into the box rather than only afterwards. Once the review lands,
the same list gains a second column — expected → read, with a per-garment
tick, cross or amber "not read" — so a failure names the garment rather than
only the player, which is the difference between sending somebody home and
swapping their armband. The original brief follows.

**Why the admin takes it, not the player.** The reference photo's first job is
not to feed #11 — it is a **manual gate**. Two of the four channels are
bring-your-own (#9) — t-shirt and trousers — so the single largest risk to the
night is somebody turning up in the wrong colours, or in something they called
"green" that photographs khaki. Checking that is a job for the person standing
at the door with the box of armbands and hats, because they are the only one
who can do anything about it: swap a garment, hand out a different armband, or
record an override there and then. A
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

### R8 — Let the players adjudicate: appeal, don't review *(shipped — Gaby's idea)*

**Shipped 28 Aug**, backend and frontend both. Decisions taken, matching this
entry's own "decide up front" list:

- **Budget.** `User.appeals_remaining`, `APPEALS_PER_GAME = 3` as a single
  constant in `backend/model.py` — decremented on lodging an appeal, refunded
  on upheld, reset alongside HP and ammo when the game resets. The admin's
  give-back control is a roster row, **Appeals: +1 / −1**
  (`admin_give_appeals`), the same shape as `admin_give_ammo`.
- **One appeal per shot per party, structurally.** `shooter_appeal_reason` and
  `target_appeal_reason` are separate columns on `Shot`, not a shared slot —
  both parties are refunded when either one's appeal is upheld.
- **Reasons** are this entry's four (`missed`, `wrong_target`, `not_a_player`,
  `already_out`) plus a fifth, `actually_hit`, for the shooter's own case:
  appealing a miss or bystander call that should have been a hit.
- **An appeal re-opens the shot; it never undoes it**, exactly as recommended
  below. `Shot.appeal_state` (`open` / `upheld` / `rejected`) marks it
  contested; a checked shot stays checked, so a contested shot can never
  re-enter the auto-action drain. Contested shots get their own admin list
  (`admin_get_contested_shots_info`), ordered by `appealed_at`, leaving
  `get_unchecked_shots` and the drain untouched.
- **Upheld is inferred at re-adjudication**, not a second verdict button: the
  ruling changed, or the hit moved to a different target, or the admin
  refunded the shot outright (benefit of the doubt). A miss and a bystander
  call count as the *same* ruling here — both say the shot hit no player, so
  re-ruling one as the other rejects the appeal. Resolutions are
  **terminal** — the admin's word ends the loop, which answers this entry's
  re-appeal question.
- **HP is never auto-unwound** (open question 6, answered as this entry
  recommended): the admin repairs HP and ammo by hand at re-adjudication. The
  public `APPEAL_UPHELD` ticker entry is the correction's social event; a
  private line tells each appellant directly.
- **`TickerEntry` gained `shot_id`.** The private "you were hit" line carries
  it and is tappable in the app, opening straight onto the shot — the way in
  this entry asked for, rather than making the player go looking.
- **A fourth per-game toggle, `ai_resolve_everything_enabled`** (default off),
  ships the "resolve harder, let appeals catch the errors" half: it relaxes
  only the confidence gate, so an unconfident miss/bystander/ambiguous-hit
  ranking resolves to the best call for the players to appeal. It is never
  forced when there is nothing to resolve *from* — no usable review, an
  inconsistent reading, no ranking at all (nobody to notify means nobody can
  appeal), or an errored escalation. The strict FIFO queue ordering is
  untouched either way.
- **`hit_user` now also fires the target's own `user` SSE event** — a real
  gap this entry surfaced rather than one it predicted: the victim's HUD
  never updated live before this.
- **The popup says when it scrolls.** A phone-shaped shot photo pushes the
  Appeal button just past the fold of the "My shots" detail view, and a dark,
  bar-less scroll box gave no sign of it — the button read as absent. `Popup`
  now floats a bobbing chevron at the bottom whenever there is content below,
  which scrolls to the bottom when tapped; every popup gets it, not just this
  one.
- **Shipped before the 19th, off by default everywhere.** This entry's "not
  before the 19th" caution was about switching appeals on for a live game,
  not about having the mechanism built and ready to switch on later.

The original brief follows.

**The idea.** Stop asking the admin to check every shot. CharlesBot resolves each
shot the moment the photo lands, and the two people who were actually there — the
shooter, and whoever CharlesBot says was hit — are both shown the photo and the
verdict. Either can press **Appeal** — three times a game, with the appeal
refunded whenever it succeeds. Only appealed shots reach the admin. The queue
stops being *every shot* and becomes *the contested ones*.

**Why this is worth more than another point of accuracy.** Everything else in
track A tries to make CharlesBot wrong less often. This changes what happens when
it is wrong, which is the more valuable half. The go/no-go on
`ai_auto_actions_enabled` currently rests on a false-hit rate measured over
thirteen fixtures, and switching it on is a bet, because an automatic error today
is both silent and final — nobody ever looks at that shot again. With appeals an
error is loud and recoverable, so the toggle stops being a bet on accuracy and
becomes a bet on *the errors being noticed*, which is a much easier thing to be
right about. It also removes the only structural limit on how big a game can get:
one admin adjudicating every shot, all night, in real time.

**The incentives do the work.** Line each way CharlesBot can be wrong up against
who is told and who wants it changed:

| CharlesBot's verdict          | Who sees it       | Who wants it looked at again                                        |
| ----------------------------- | ----------------- | ------------------------------------------------------------------- |
| Hit on Alice — correct        | shooter, Alice    | nobody. It stands, with no admin time spent.                        |
| Hit on Alice — actually a miss | shooter, Alice   | **Alice**: she has lost HP she should still have.                   |
| Hit on Alice — actually hit Bob | shooter, Alice  | **Alice**, who was never shot. (Bob is never told, and needn't be — Alice's appeal re-opens the shot either way.) |
| Miss — actually hit Alice     | shooter only      | **the shooter**: he wants his kill.                                 |
| Bystander — actually hit Alice | shooter only     | **the shooter**, likewise.                                          |
| Miss — correct                | shooter only      | nobody with a case, but see abuse below.                            |

The shooter and the target are on opposite teams, so for every error class there
is somebody who both *knows* about it and *wants* it revisited. That adversarial
pairing is what makes the scheme sound, and it also names its one hole:
**friendly fire has no opposed party** — a shot between teammates, wrongly
resolved, may suit both of them. Rare, low-stakes, and the admin can still open
any shot they like; not worth engineering against.

**The shooter's side is nearly built.** `ShotHistory.js` and
`shotHistoryStore.js` already give a player every shot they have fired, its
adjudicated outcome, and the photo (`/api/user_shot_image`, cached by
`ShotCache.js`), including today's `AI thinks: …` line for a shot the admin has
not reached. An Appeal button on that per-shot detail view is a small addition to
a surface that exists.

**The target's side does not exist, and is the real build.** A player who is hit
gets one private ticker line (`USER_GOT_HIT` / `USER_GOT_KNOCKED_OUT`, sent from
`admin_interface.hit_user`) and nothing else — no photo, no shot id, nothing to
appeal against. Needed:

- `Shot.target_user_id` is already recorded, so the query is there:
  `user_interface.get_own_shots` wants a sibling for *shots against me*, and
  `get_own_shot_image`'s `shot.user_id != self.user_id` check has to widen to
  admit the target. No new exposure — it is a photograph of them, taken of them,
  and the ticker has already named the shooter.
- Somewhere to show it. The existing shot-history popup is the natural home:
  either a second list, or one list with each entry marked fired/received.
- The private ticker message should carry the shot id so the line itself can be
  the way in, rather than making the player go looking.

**An appeal re-opens the shot; it does not undo it.** This is the part that will
bite if it is not decided up front. Resolving a shot mutates game state that
later events depend on — a knockout calls `clear_unchecked_shots`, which refunds
every shot the victim had queued, and the ticker has already announced it in
public. There is no compensating action anywhere in the codebase for any of that,
and writing a general unwind is far more than this item is worth. So:

> **Appealing marks the shot contested and puts it in front of the admin. It
> changes no HP, no ammo and no ticker by itself.** The admin then adjudicates
> with the tools that already exist — `hit_user`, `refund_shot`, `set_user_HP`,
> `hit_user_by_admin` — and a wrongly-taken life is handed back by hand.

Pragmatic, honest about what it is, and it means an appeal can never itself
corrupt the game state. It does need a ticker message for the correction, though:
"Alice is back in the game" is a social event, not a database update.

**Contested shots need their own queue, not the head of the existing one.**
`shot_auto_actions.process_queue_head` acts only on the oldest unchecked shot,
deliberately, because resolving a shot can invalidate the ones behind it. An
appealed shot re-entering that queue with its original timestamp would become the
head and jam the live drain behind a twenty-minute-old argument. Keep the two
apart: a `contested` flag (or an `appeal_state` column) that lists the shot in a
separate admin tab, leaving `get_unchecked_shots` and the drain untouched.

**Note that the two auto-action gates are separable**, and only one of them
relaxes here. The strict queue ordering exists because of *state dependency* and
still holds. The confidence threshold exists because of *accuracy*, and appeals
are exactly what justify loosening it: `_decide()` returning `None` would stop
meaning "stop the drain" and start meaning "resolve it as best you can, the
players will complain if it is wrong".

**It does not empty the queue, and shouldn't be sold as if it does.** Some shots
CharlesBot cannot resolve at all — a hit it is sure about but cannot pin to any
candidate has no verdict to show anybody, because there is no target to notify.
Those still go to the admin as they do now. The honest claim is that the admin
sees **the unresolvable plus the contested**, which on the numbers so far is a
small fraction of the night's shots rather than all of them.

**Abuse is the obvious failure mode, and the budget is the fix.** Appealing is
free and the upside is one-directional, so the dominant strategy would be to
appeal everything, which puts the admin back exactly where they started. So:
**three appeals per player per game, refunded whenever the appeal is upheld.**

That mechanic is better than it first looks, because of where the cost lands.
A player who is genuinely being misread — a bad photograph, an outfit that
lights badly, whatever CharlesBot keeps getting wrong about them — appeals as
often as they need to and never spends a thing, because every one of those
appeals succeeds. The budget only ever depletes for someone appealing shots
CharlesBot got *right*. **The price is on being wrong, not on appealing**, which
is exactly the incentive to want: it puts no friction in front of the honest
complaint the whole scheme depends on, and puts a hard stop in front of the
speculative one. Running out means three failed appeals, which is itself
something the admin should see.

Keep the per-shot rule alongside it — **one appeal per shot per party, and it
must state a reason** picked from a short list: *it missed* / *that wasn't me* /
*that's not a player* / *I was already out*. Per-shot stops one shot being
spammed, per-game caps the night. The reason is worth having for its own sake:
it labels the error class, which is precisely the data R1/R2 have to reconstruct
by hand today.

**The budget is ammo, mechanically.** `User.num_bullets` with `award_ammo()` is
the same shape and should be the model: an `appeals_remaining` column on `User`
defaulting to three, decremented when the appeal is lodged, incremented when it
is upheld, and reset alongside `num_bullets` and `hit_points` in
`admin_interface.reset_game`. Show it next to the appeal button the way
`BulletCount.js` shows ammo — a player deciding whether to spend one needs to
know what they have left.

**What the player actually sees.** An **Appeal** button on the shot, and a
confirmation popup before it is spent — nobody should lose an appeal to a
mis-tap, and the count is the thing they need in front of them at the moment
they decide:

> **Are you sure? You have 2 of 3 appeals left.**
> *Successful appeals are refunded.*

The second line in smaller white text under the question. It is there because the
budget is only fair if the player knows the refund rule *before* they weigh
spending one — a cap without the refund reads as "shut up and accept it", which
is the opposite of what this is for. **At zero the button is greyed out, not
hidden**, and says why: a control that vanishes is a bug report, and a player who
can see they are out of appeals understands the rule better than one who never
sees the button again.

`Popup.js` is already the fullscreen popup component and the shot-history detail
view is already inside one, so this is a confirmation step in an existing
surface. The count itself should ride the `UserModel` payload next to
`num_bullets`, so the existing SSE `user` event keeps it live without a new
endpoint or a poll.

**And the admin can hand appeals back.** A referee who has just talked something
through with a player needs to be able to give them another go — a budget with no
override turns a judgement call into a dead end. This is the same control the
admin already has for ammo: `AdminMode.js`'s per-user row has **Ammo: +1 / −1**
posting to `admin_give_ammo`, so **Appeals: +1 / −1** posting to
`admin_give_appeals` is the same row, the same shape, and the same backend
pattern. Reuse it rather than inventing a different one.

**Upheld or rejected should be inferred, not a second verdict button.** The
contested shot already carries CharlesBot's verdict in `ai_review`; if the
admin's adjudication differs from it, the appeal was upheld. That is one
comparison at the point the admin resolves the shot, and it keeps the admin's
workflow identical to the one they already have. Two cases need a stated rule:
a shot the admin ends up **refunding** (the knockout cascade, not a judgement
either way) should give the appeal back — benefit of the doubt costs nothing;
and an admin who agrees with CharlesBot's outcome but for different reasons is
a rejection, which is the right answer anyway since the game state is unchanged.

**What the budget costs, and it is not nothing.** A player unsure whether they
were really hit may sit on an appeal rather than risk it, so some real errors go
unreported — which is the one thing this whole item exists to prevent. Three is
therefore a number to revisit after a game, and it should live as a single
constant, not be scattered. It also weakens the note below: with a budget in
play, silence is partly explained by hoarding, not only by agreement.

**Silence is data too, with a caveat.** A shot neither party appealed is weak
evidence CharlesBot got it right, and there will be hundreds of them per game —
by far the largest labelled set the recognition work has ever had. Weak because
nobody may have looked; worth recording as *unappealed* rather than *confirmed*,
and never worth mixing with admin verdicts in the same column of R2's scorecard.

**Timing, and why this pairs with R4.** An appeal is only useful inside the
window where the shot still matters, so the target has to find out quickly. With
the app open, the existing SSE `user` event and the shot-history bubble already
do this. With the app closed — a phone in a pocket between fights, which is most
of a game — nothing reaches them until they look. That makes **R4 (Web Push)** the
natural partner: it is what turns "you were shot, appeal within a few minutes"
into something a player actually receives. Shippable without it; better with it.

**This partly answers open question 1.** If CharlesBot's word is final unless
appealed, then its word has to be shown to both parties — a shooter cannot appeal
a misattribution they were never told about. The reason for withholding the name
was that it was an unconfirmed guess leaking a player's position; under appeals
there is no "pre-confirmation" state to protect, because there is no admin pass
coming. The privacy argument does not disappear, but it changes shape and should
be re-answered here rather than assumed.

**Lands in:** `backend/model.py` (appeal columns on `Shot`, `appeals_remaining`
on `User` — remember there are no migrations, so `npm run resetdb`),
`backend/user_interface.py` (shots-against-me, the widened image check,
`appeal_shot` and the budget decrement), `backend/main.py` (the two new player
endpoints plus `admin_give_appeals`), `backend/admin_interface.py` (the contested
list, the upheld/rejected inference and its refund, granting appeals back, the
reset in `reset_game`),
`backend/shot_auto_actions.py` (resolve-everything mode, and never re-drain a
contested shot), `backend/ticker_message_dispatcher.py` (the correction message,
and the shot id on the private hit message),
`react-ui/src/ShotHistory.js` + `shotHistoryStore.js` (the appeal button, its
`Popup.js` confirmation, the remaining-appeals count and the received-shots
list), `react-ui/src/ShotQueue.js` (the contested tab), `react-ui/src/AdminMode.js`
(**Appeals: +1 / −1** on the per-user row). Tests in
`tests/test_shots.py`, `tests/test_admin_mode.py`, `ShotHistory.test.js`,
`ShotQueue.test.js`.

**Depends on:** nothing hard, but it wants #5 shipped (an auto-resolved hit has to
name somebody) and reads much better after #2 gives that name a display string.
**Feeds:** R1/R2 — every appeal is a labelled error with its class attached.
**Pairs with:** R4. **Not before the 19th**: it changes who adjudicates the game
on the night, which is not a thing to try for the first time on the night.

---

## Open questions

Answers to these change the shape of the work, not just its order.

1. ~~**Should the player-facing shot history name the target?**~~ **Answered:
   yes**, decided alongside R8 (shipped 28 Aug). #2 gives the admin a name, and
   the original suggestion here was to keep the player's view to hit / miss /
   bystander, on the grounds that an unconfirmed guess shouldn't leak a
   player's identity to the other team before an admin has confirmed it. R8
   overturned that: once CharlesBot's verdict is final unless appealed, there
   is no unconfirmed-guess state left to protect, and a shooter cannot appeal a
   misattribution they were never told about — both parties have to be shown
   enough to appeal against. `get_own_shots` now carries `ai_target_name`.
2. ~~**Do we ask players for a photo of themselves in their outfit at pick
   time?**~~ **Answered: no.** The photo moves to the door on the night, taken by
   the admin — see R7. Keeps the colour-picker a colour-picker, and makes the
   photo a check rather than a self-report.
3. **How long do reference photos live?** Suggestion: deleted with the game.
4. **Does the identification scheme survive two bring-your-own channels?** With
   the armbands and hat now provided (#9), only the t-shirt and trousers are
   left to players — roughly halving the exposure this question originally
   worried about, though it does not remove it: those two channels still depend
   on players owning and wearing the colours they picked. #10's picking page and
   R7's door check are the mitigations; R1/R2 will tell us afterwards how well
   it worked.
5. ~~**Is free choice of outfit worth the capacity it costs?**~~ **Answered:
   yes, and it costs nothing here.** §12.5 measured free choice across the *whole*
   space, where unlucky picks strand regions. Pinning the hat to the team
   partitions the space into seven independent buckets and prevents that
   stranding: inside a team, free choice and the code have identical capacity,
   because `d >= 3` under a shared hat already forces distinct t-shirts, trousers
   and armbands, and the trousers channel caps a team at its own colour count
   either way. What free choice adds is that those outfits can be chosen to fit
   the team's actual wardrobes — 82.8% of players in clothes they own against
   the code's 57.4%. See plan §12.6.
6. ~~**When an appeal is upheld, how far back does the correction reach?**~~
   **Answered: it doesn't.** Shipped 28 Aug as R8 recommended: the appeal
   re-opens the shot and the admin fixes HP and ammo by hand, because a
   knockout has already refunded the victim's queued shots and announced
   itself in the ticker, and a general unwind is more machinery than the game
   is worth. The alternative considered — holding each auto-verdict for an
   appeal window before applying it — needs no unwind at all, but delays every
   knockout by the length of the window, which in a game measured in seconds
   is its own problem, so it was not built.
