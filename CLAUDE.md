# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## Overview

**Streetfight** is a personal, mobile-first, team-based real-life game. QR-code
"loot" (weapons, armour, ammo, medpacks) is scattered around a town; players scan
codes to pick up items and photograph each other to "shoot", while admins review
the photos and validate hits. It is a full-stack app:

- **Backend** — FastAPI + SQLAlchemy (`backend/`), serving a REST API under `/api`
  plus Server-Sent Events (SSE) for realtime updates.
- **Frontend** — Create React App (`react-ui/`), a mobile-first PWA-style client.
- Glued together by a root `package.json`, a Nix flake, and Docker Compose.

## The game is live — the production database is real (2026-08-29)

**Join links are out.** Players are joining
`streetfight.houseabsolute.co.uk` and picking their clothes, so the droplet's
database at `/data` holds state that cannot be regenerated: assigned identity
slots (`User.identity_slot`), pinned team colours (`Team.identity_colour`),
the join links already in people's WhatsApp, shots and their photographs.
This supersedes the old "not deployed yet — breaking changes are free" note;
its licence is withdrawn.

What that changes, in practice:

- **Wiping the database now costs something real.** `resetdb`,
  `RESET_DATABASE`, and anything else that runs `create_all()` over a fresh
  file are dev-only. Never suggest one as a way past a problem on the live
  box, and say so plainly if a change would need one — every join QR already
  sent dies with the game it was minted for
  (`docs/r9_agent_walkthrough_2026-08-29.md` B2).
- **There are still no migrations**, so a change to `backend/model.py` and a
  live database are now in genuine tension. A column addition is not free:
  it needs a hand-written `ALTER TABLE` against `/data`, or a considered
  decision to lose the state. Raise the cost to Charles before writing the
  model change, not after.
- **The identity scheme is frozen.** Renumbering symbols, reordering or
  re-hexing a palette (`backend/identity/config.py`), or changing what a slot
  decodes to would re-clothe players who have already chosen. Treat those
  files as append-only unless Charles asks for the break knowingly.
- **Deploys are a deliberate act**, not a consequence of merging — see the
  deployment section below. Merging to master is safe at any hour; nothing
  reaches the players until someone runs the deploy workflow.

Everything else — code, styling, tests, admin pages — is as free to change as
it ever was. This is about state, not about caution generally.

## Planned work

`docs/roadmap.md` is the roadmap: the agreed future work, re-prioritised, with
the files each item lands in and the open questions still outstanding. Read it
before starting anything substantial - several items are deliberately sequenced
behind each other, and a few are "wire up what already exists" rather than the
rewrite they sound like. Keep it current: when an item ships, say so there.

## Contributing

Attempt to match existing code styles where possible. Prefer self-documenting code over verbose comments. Where a pattern has already been demonstrated elsewhere in the codebase, generalise and reuse it rather than minting a new, different version.

For a feature that affects the backend or the frontend functionality, ensure to add unit tests. One caveat to this is: don't add unit tests that test very simple behaviour. For example, if you add a button that says "hello", do not add a unit test that says, "Does the button say 'hello'?" We can trust code that far.

When fixing a bug, use a TDD workflow: first write a test that reproduces the
bug (it should fail against the current code), then make the fix and confirm
the test passes.

Keep the agent documentation up to date, such as this file and any other documentation for agents in the repository.

It's an unpolished personal project (see `README.md`), so favour pragmatic,
minimal changes over large refactors.

### The admin UI exemplar

`react-ui/src/ReferencePhotos.js` and its `.module.css` are the house style for
admin pages, and Charles has said so explicitly — match them rather than
inventing a look. What makes it work:

- **Functionality first.** No chrome, no decoration, no layout that exists to
  look designed. Every element on the page is something the admin does or reads.
- **Big, bulky, unmissable buttons.** `min-height: 3.5em` for the primary
  action, `3em` in a button row, `3.2em` for a roster row — comfortably past the
  44px touch minimum, because this is driven one-handed on a phone with a box of
  armbands in the other hand.
- **One column of large targets**, ordered as the job is done: pick a player,
  act, read the verdict, go back.
- **Status says the state in words**, in a pill with a shared colour tone
  (`statusGood` / `statusWarn` / `statusBad`, matching
  `AdminIdentity.module.css`), never a bare icon or colour alone.
- **Colour means certainty**: green and red are for answers, amber for
  everything the machine is not sure of. See `IdentificationVerdict`.

**One page is exempt: `SpectatorView.js`.** Charles exempted it explicitly -
"an entirely different vibe". Everything above is tuned for a phone held
one-handed with a box of armbands in the other; the spectator screen is read
from three metres by people who will never touch it, on a TV left running for
hours. It keeps the last two rules - state said in words, and colour meaning
certainty - and none of the shapes. Do not "fix" it back towards this
exemplar.

## Repository layout

- `backend/` — FastAPI application.
  - `main.py` — app entrypoint (`app`); all `/api` routes are defined here.
  - `model.py` — SQLAlchemy ORM models + Pydantic schemas
    (`Game`, `User`, `Team`, `Shot`, `Item`, `TickerEntry`).
  - `database.py` / `database_scope_provider.py` — engine, session factory, and
    the `@db_scoped` decorator that manages session lifecycle and post-commit
    event triggering.
  - `user_interface.py` / `admin_interface.py` — game logic (player-facing and
    admin operations: shot validation, HP/ammo, weapons, circles, resets).
  - `shot_identification.py` — which player a shot photograph shows: builds the
    candidate set and the location term, and scores the reading against each
    candidate's *effective word* via `identity/decoder.py`.
  - `shot_escalation.py` — the hard cases (roadmap #11): too few readable
    garments sends the queue head to a second vision pass
    (`OPENROUTER_ESCALATION_MODEL`) with the GPS-ranked candidates and their
    reference photos. That model is free to be stronger than the cheap
    pass's, but doesn't have to be — unset, it mirrors `OPENROUTER_MODEL`, so
    the extra context (candidates, reference photos) is what earns the
    escalation its keep, not being a bigger model. Its verdict re-enters the
    auto-action gate, with "unsure" landing the shot back with the admin.
  - `reference_photos.py` — the kit check at the door (roadmap R7): the admin's
    photo of a player, put through the *same* vision path a shot takes
    (`ai_shot_review._review_image_data`) and then scored against everyone who
    has picked an outfit. Stored on the `User`, never as a `Shot`. What the
    player is *supposed* to be wearing rides on the roster instead
    (`identity_admin.expected_outfit`, in each
    `admin_get_reference_photo_status` row), shaped like a review's `channels`
    so the page renders expectation and reading through one component.
  - `ticker.py` / `ticker_message_dispatcher.py` — in-game announcements.
  - `items.py` / `item_actions.py` — collectible items and their effects.
  - `circles.py` — geographic game zones (exclusion / next / drop circles).
  - `venues.py` — where a game is played: the map image, its georeferencing and
    the landmarks circles can be placed at. See the venues note below.
  - `sse_event_streams.py` + `asyncio_triggers.py` — SSE streams and the
    asyncio event registry that drives live updates.
- `react-ui/` — Create React App frontend.
  - `src/index.js` — entrypoint (React Router).
  - `src/utils.js` — `sendAPIRequest(...)` fetch wrapper (prefixes `/api/`),
    plus geolocation/camera permission helpers.
  - `src/UpdateListener.js` — SSE client; `registerListener`/`deregisterListener`
    dispatch typed updates ("user", "ticker", ...).
  - `src/setupProxy.js` — dev proxy: forwards `/api`, `/docs`, `/openapi.json` to
    the backend at `http://127.0.0.1:8000`.
  - `src/venue.js` + `src/mapImages.js` — fetches the venue from the backend and
    turns its reference points into map geometry (`mapGeometry`) and pixel
    positions inside a box (`mapProjection`, shared by `MapView.js` and the
    admin's per-shot `ShotMap.js`); `mapImages.js` is the bundled map images
    the server's `map.image` key resolves against. `ShotMap.js` draws the
    whole crowd, not just the shooter: everybody else in that shot's
    `location_context` who fits in the box, nearest first, with a teammate
    told apart from an opponent and anything that weakens the position - a
    stale fix, a player who is out - said in words beside the dot. It is a
    snapshot of the moment, so fix ages are measured against the shot's own
    `time_created` (`shotEpochSeconds`), never the wall clock.
  - Views: `UserMode.js`, `AdminMode.js`, `ShotQueue.js`, `MapView.js`, etc.
    `PickOutfit.js` (route `/pick`) is the player-facing outfit-picking page a
    team join code lands on; it shares the colour `Swatch.js` component with
    the admin identity pages (`AdminIdentity.js`, `IdentityDemo.js`). Its
    footer links to `HowItWorks.js` (route `/how-it-works`), a static essay on
    the error-correcting code behind the outfits — currently a placeholder
    skeleton awaiting Charles's prose, marked `PLACEHOLDER START/END`. It opens
    in a new tab because the picker's wardrobe ticks are unsaved React state.
    `SpectatorView.js` (route `/admin/spectator`) is the big-screen dashboard
    for people who are not playing - a laptop wired to a TV, left alone all
    evening (roadmap R11). Read-only, and it has **three faces**: the map face
    (map, shot feed with live adjudication, roster, team totals, ticker), a
    **gallery** face showing recent shots large, and a **shot takeover** that
    overlays either when a shot lands. The screen alternates map and gallery on
    a timer. **It is deliberately exempt from the admin house style below** -
    see that section. Its look came from a separate Claude design session
    (`docs/spectator_view/design_brief.md`, which records what was asked for
    and what came back), so `SpectatorView.module.css` is a delivered artefact:
    prefer re-briefing over editing it by hand. Note the integration shim at
    its top - `index.css`'s global `* { font-size: 12px }` beats inheritance and
    would otherwise flatten the whole type scale. Because it is left running on
    a device nobody touches, it holds a screen wake lock (`useWakeLock.js`,
    shared with user mode) and *says so in the headline when it has not got
    one* - the tablet locking itself is how the dashboard disappears, and a
    browser too old for the Wake Lock API is the one case nothing can be done
    about from here.
    `ReferencePhotos.js` (route `/admin/reference`) is the door kit-check page
    (roadmap R7): it shows what each player is expected to be wearing - the hat
    and armband we hand over first, *before* the camera, because that is the
    moment they are handed over - captures a reference photo, and then puts the
    model's reading beside that expectation garment by garment. It falls back to
    `ShotQueue.js`'s exported tag renderers for a player with no outfit to
    compare against.
  - Styling: CSS Modules (`*.module.css`) + Bootstrap; React hooks only (no Redux).
- `server/` — Express server (`server/index.js`) that serves the built React app
  and proxies `/api` in production (`npm run frontend`).
  - `test_world/` — the deterministic thirty-player sample game (roadmap R11):
    a cast dealt to locked counts, an hour of simulated movement and
    phone-shaped telemetry over the real venue, ten shot scenarios *selected*
    out of the encounter pool rather than invented, and a content-addressed
    image store. Driven by `python -m backend.test_world <world|scenes|
    generate|observe|gate|gateb|check|shots>`; `world.json` in
    `test_world/data/` is its single source of truth and everything
    else is derived from it. That data sits *inside* the package, not under
    `tests/`, because the replay is not only a test tool — the admin's demo
    button runs it on a server with no checkout anywhere near it — so
    `world.json` and `data/shots/` are declared as package data in
    `pyproject.toml` and travel into every deployment. The generated image
    store (`data/images/`) and the generator's own inputs deliberately do not:
    only a checkout ever regenerates a picture. `MAKE_DEBUG_ENTRIES` builds
    this game, so the sample database is a real crowd rather than ten empty
    teams.
    `shots` (`npm run demoshots`, `test_world/replay.py`) puts the ten cropped
    photographs into that game as shots somebody fired. It walks the scenarios
    in tick order, moving the whole cast to the fix each of them had *at that
    tick* before firing, because a shot's `location_context` is a snapshot of
    the moment its photograph was taken — firing all ten against the game's
    final positions would give every shot telemetry that contradicts its own
    picture. The simulated hour is anchored to end now, so the newest shot is
    a minute old and the oldest about ninety; shot ids are derived from the
    seed, so replaying twice is a no-op (`--only S4` re-loads one).
- `backend/demo_game.py` — the same ten shots, but **dripped in live**: the
  admin's **Fire demo game** button (`AdminMode.js`'s `DemoGamePanel`,
  `/api/admin_start_demo_game`) provisions the sample game if it is not there
  and then fires one shot every thirty seconds or so from a background asyncio
  task. `npm run demoshots` fills a queue to adjudicate; this fills a dashboard
  to *watch*, which cannot show the spectator screen reacting to a shot if
  every shot landed before the page loaded. Time is sped up by **re-anchoring
  each shot**, not by scaling the clock: `anchor_epoch(tick)` puts that shot's
  tick at this instant, so the shot reads as just fired while every fix behind
  it keeps the exact age the world gave it. Idempotent (pressing it again while
  it runs changes nothing, and after a cancel it resumes — the shot ids come
  from the seed; a half-provisioned game, cast interrupted mid-way by a crash,
  a reload, or a deleted player, is completed rather than fired into),
  cancellable, and it **refuses to run at all** if anybody in a team is not
  one of the thirty simulated players, since it creates thirty players and
  shoots at them.
- `scripts/` — standalone tools, not part of the app.
  `simulate_code_capacity.py` Monte-Carlos how much identity capacity is lost if
  players pick outfits freely instead of taking the codeword the scheme assigns
  (see `docs/team_photo_identification_plan.md` §12.5).
  `deploy.sh <live|staging> [ref]` wraps the two deploy workflows — see the
  deployment section below.
- `.claude/` — the agent tooling. `hooks/session-start.sh` bootstraps a fresh
  checkout (see "Session bootstrap" below), and `skills/` holds the repeatable
  procedures:
  - **`run-mobile-app`** — launch the stack and screenshot the UI at a phone
    viewport, with a fake camera and GPS.
  - **`draw-venue-map`** — make and georeference a map for a new venue.
  - **`regenerate-test-world-images`** — rebuild the test world and its
    generated photographs. Read it *before* spending anything at OpenRouter.
  - **`deploy-streetfight`** — deploy live or staging, verify, roll back.

  Keep these current the same way as this file: when a procedure changes,
  change the skill that describes it rather than leaving a second version in
  prose somewhere.
- `tests/` — pytest suite (`test_backend.py`, `test_items.py`, `test_shots.py`,
  `test_ticker.py`, `test_admin_mode.py`, `test_user_interface.py`,
  `test_sse.py`, `test_selenium.py`; fixtures in `conftest.py` and
  `shared_fixtures.py`).
- Root: `package.json` (orchestration scripts), `pyproject.toml` + `uv.lock`
  (the Python dependencies), `flake.nix` / `.envrc` (Nix dev env),
  `compose*.yml` + `Caddyfile` (deployment).

## Setup & run (development)

All commands below are run from the repo root.

### Session bootstrap (agents: this is already done)

`.claude/hooks/session-start.sh` runs on every session start and leaves the
checkout able to run the tests, the linters and the app: `uv sync --frozen
--all-groups`, `npm install` (which covers `react-ui` through the root
package's `install` lifecycle script), a self-signed cert, and `.env`.

It is **async**, so it may still be running when you get control.
`.claude/.session-start.done` appears only when it has finished and
`.claude/session-start.log` says what happened — read the log rather than
re-running the installs, and wait on the marker if you are about to run
something that needs the environment.

Every step is conditional on its own output being absent, so it is safe on a
laptop with a setup already in place: **`.env` and the certificates are never
overwritten**. That is also why it does the safe parts of `npm run bootstrap`
by hand rather than calling it — `bootstrap` ends with `cp .env.dev .env`,
which would replace a real `OPENROUTER_API_KEY` with a comment. It also skips
`npm run build`, since every path an agent uses serves from the dev server.

```bash
# First-time setup by hand, if you are not in an agent session: npm i +
# generate self-signed cert + build frontend + cp .env.dev .env. NOTE this
# overwrites .env.
npm run bootstrap

# Run the backend (uvicorn with autoreload)
npm run backend          # uvicorn backend.main:app --reload --reload-dir backend

# Run the frontend dev server (HTTPS) in another terminal
npm run dev              # cd react-ui && npm start

# ...or run both at once
npm run dev_both

# Reset / initialise the database
npm run resetdb          # python -m backend.reset_db

# Fill the sample game's shot queue with the ten demo shots (dev only, free)
npm run demoshots        # python -m backend.test_world shots
```

To watch a dashboard fill up instead of finding it already full, use the admin
page's **Fire demo game** button (`backend/demo_game.py`), which drips the same
ten shots in one at a time over about five minutes.

There are **no database migrations** (no Alembic). The schema is created from the
ORM models in `backend/model.py` via `create_all()`. After changing a model,
reset the dev DB with `npm run resetdb` — **in dev only**: the live droplet's
database holds a running game, so a model change now needs a hand-written
`ALTER TABLE` there, or Charles's agreement to lose the state. See "The game
is live", above.

Nix alternative: `nix develop` to enter the dev shell, then `nix run .#backend`
and `nix run .#frontend` in separate terminals.

## Python dependencies

Declared **once**, in `pyproject.toml`, and resolved by **uv** into `uv.lock`.
Nix does not carry a second list: `flake.nix` feeds `uv.lock` to **uv2nix**,
which builds the dev shell, the CI shell and the deployed `backendEnv` from it.
So a bare `uv sync` in a throwaway container installs the same versions the LXC
container runs — that parity is the whole point, so **do not** hand-install
packages with `pip` and **do not** add a Python dependency to `flake.nix`.

```bash
uv sync --frozen --all-groups   # exactly what the lock says (agents, CI, containers)
uv add <pkg>                    # add a runtime dep; updates pyproject.toml + uv.lock
uv add --dev <pkg>              # add a test-only dep
uv run pytest                   # run inside the venv without activating it
```

Both paths work and agree; pick by what you already have:

| Environment | Command | Gets |
| --- | --- | --- |
| Has Nix | `nix develop` | Python + node + caddy + pre-commit + TeX |
| No Nix | `uv sync --frozen --all-groups` | Python only, same versions |

Notes and gotchas:

- `sourcePreference = "wheel"` in `flake.nix` — every dependency here publishes a
  wheel, and sdists are where uv2nix needs hand-written overrides. Prefer a
  dependency that ships wheels; that is why the lock carries `psycopg2-binary`
  rather than `psycopg2`, which is sdist-only and would want `pg_config`.
- uv does not lock build systems, so they come from the
  `pyproject-build-systems` overlay rather than `uv.lock`. If a new dependency
  fails to build complaining about a missing build backend, that overlay is
  where it belongs.
- The git revision baked into the deployed package (`backend/VERSION`, served by
  `/api/get_version`) is applied by the `versionOverlay` in `flake.nix`.
- After changing `pyproject.toml`, commit the regenerated `uv.lock` with it.

## Testing

```bash
pytest                   # backend suite (setup.cfg sets testpaths = tests)
pytest -m "not selenium" # default scope, skipping browser tests
pytest --runselenium     # include selenium/browser integration tests
cd react-ui && npm test  # frontend tests
npm test                 # full suite: pytest then react-ui tests
```

CI runs the backend tests via `nix develop -c pytest`
(`.github/workflows/test_backend.yml`).

## Lint / format / pre-commit

Python formatting is handled by **black**, **isort**
(`--profile black --force-single-line-imports`), and **autoflake**; **flake8** is
configured in `setup.cfg` (`max-line-length = 120`, `extend-ignore = W291`).
JavaScript is formatted with **prettier**. Run everything via:

```bash
pre-commit run --all-files
```

**CI rejects any `FIXME` comments** (`.github/workflows/check_fixme.yml`) — do not
leave `FIXME` markers in committed code.

## Environment variables

Defaults live in `.env.dev` (copied to `.env` by `npm run bootstrap`). Key ones:

| Variable             | Purpose                                              |
| -------------------- | ---------------------------------------------------- |
| `DATABASE_URL`       | DB connection (SQLite in dev, PostgreSQL in prod)    |
| `SECRET_KEY`         | Session/cookie signing secret                        |
| `ADMIN_PASSWORD`     | Admin login password                                 |
| `LOG_LEVEL`          | Python logging level (e.g. `DEBUG`, `INFO`)          |
| `MAKE_DEBUG_ENTRIES` | Auto-create a sample game/teams on DB reset          |
| `RESET_DATABASE`     | Wipe the DB on startup                               |
| `WEBSITE_URL`        | Frontend URL (used for CORS)                         |
| `API_URL`            | Backend API base URL                                 |
| `OPENROUTER_API_KEY` | OpenRouter key for AI shot review (unset = disabled) |
| `OPENROUTER_MODEL`   | Vision model id (placeholder default, see below)     |
| `OPENROUTER_ESCALATION_MODEL` | Stronger vision model for escalated shots (unset = mirrors `OPENROUTER_MODEL`, so escalation is on wherever recognition is) |
| `OPENROUTER_ESCALATION_REASONING_EFFORT` | Reasoning-effort override for the escalation model |
| `OPENROUTER_TIMEOUT_SECONDS` | Per-request timeout for the vision call      |
| `OPENROUTER_REASONING_EFFORT` | Reasoning-effort override (none/minimal/low/medium/high/xhigh/max); unset = no override sent |
| `AI_SHOT_REVIEW_CONCURRENCY` | Parallel reviews when draining a backlog     |

## Deployment (brief)

The **`deploy-streetfight` skill** is the operating summary — how to deploy
either target, verify it, and roll it back — and `scripts/deploy.sh
<live|staging> [ref]` is the command. **Merging to master deploys neither**;
`live` and `staging` are both moved by hand, and live is never deployed on an
agent's own initiative. What follows is the architecture.

Three deployment targets share one service definition:

- **The cloud droplet (the live deployment)** is a NixOS host:
  `nixosConfigurations.streetfight-cloud` in the flake, wiring the
  deployment-agnostic `nix/streetfight.nix` module to `nix/disko-cloud.nix`
  (disk layout) and `nix/cloud-host.nix` (machine config). Installed once,
  destructively, with `nix run .#install-cloud -- --target root@<ip>
  --secrets <file>`, which captures the droplet's networking into
  `nix/cloud-net.json` before anything destructive happens (DigitalOcean
  offers no DHCP, so a config carrying another droplet's address installs a
  machine that boots dark); updated with
  `nixos-rebuild switch --flake .#streetfight-cloud --target-host root@<ip>`
  — though the routine path is the **Deploy to droplet** workflow
  (`.github/workflows/deploy.yml`), a `workflow_dispatch` button that moves
  the `live` branch to a chosen revision; a timer on the droplet
  (`nix/auto-deploy.nix`, roadmap R10) polls that branch and switches to it
  within a few minutes. **Merging to master deploys nothing** — that gate
  exists because there is now a game running on the box. Caddy terminates TLS
  itself there (`services.streetfight.hostname`); secrets live in
  `/data/secrets/streetfight.env` (`nix/streetfight.env.example` documents
  the format). See `docs/deployment_droplet.md` for the full runbook,
  including the cutover that stands down the old home-network LXC
  deployment.
- **The Proxmox LXC** (`.#proxmoxLxcTemplate`, via `nix-proxmox-cattle`) is
  **staging**, on the home lab: the container that used to run the game, kept
  after the cutover as somewhere to try things. Same shape as the droplet's
  gate, one branch along — the **Deploy to staging** workflow
  (`.github/workflows/deploy-staging.yml`) moves the `staging` branch, CI
  publishes the template as a release asset only from that branch, and the
  hypervisor at home polls for it. TLS is terminated upstream by traefik
  (gardenfacer), so it answers plain HTTP on :80 and is reachable only inside
  the house, at `https://streetfight-staging.i.houseabsolute.co.uk`. It sets
  `services.streetfight.sampleGame`, so its database is the deterministic test
  world rather than real players, and it carries the *same* secrets as live
  apart from `WEBSITE_URL`. Full runbook: `docs/deployment_staging.md`. **A
  merge to master deploys neither target** — `live` and `staging` are both
  moved by hand.
- **Docker Compose** (`compose.yml`) runs a **Caddy** frontend, the
  **FastAPI** backend and a **Cloudflare DDNS** sidecar on any Docker host.
  Overlays: Traefik (`compose.traefik.yml`), auto-update via Watchtower
  (`compose.watchtower.yml`), prebuilt ghcr.io images without auto-update
  (`compose.ghcr.yml`). `SITE_ADDRESS` sets the hostname Caddy serves and
  gets a certificate for (unset = `localhost`); it must agree with
  `WEBSITE_URL`, which is what join links and item QRs encode. Images are
  built from the Nix flake (`nix build .#dockerFrontend .#dockerBackend`)
  and published to ghcr.io by CI (`.github/workflows/build_images.yml`).

## Conventions & gotchas for agents

- The app uses **synchronous SQLAlchemy under async FastAPI**. Database access is
  managed by the `@db_scoped` decorator (`backend/database_scope_provider.py`) —
  rely on it rather than hand-managing sessions/commits.
- Realtime updates flow through `asyncio_triggers` → SSE streams in
  `sse_event_streams.py`. When you change state that clients observe, make sure
  the corresponding update event is triggered.
- **An SSE stream is only cleaned up when the client's disconnect reaches the
  backend**, and the two node proxies had to be taught to pass it on.
  `updates_generator` and `admin_updates_generator` cancel their producer tasks
  in a `finally`, which runs when Starlette cancels the response — but only if
  the socket actually closes. node-http-proxy tears the upstream request down
  on the incoming request's `aborted` event, which a GET that arrived complete
  never emits, so a closed tab used to leave the backend streaming keepalives
  into a socket nobody read, forever. Both node servers therefore share one
  proxy definition (`server/apiProxy.js`, used by `server/index.js` and
  `react-ui/src/setupProxy.js`) which destroys the upstream request on the
  response's `close`. The Caddy deployments (`Caddyfile`,
  `nix/streetfight.nix`) proxy the backend themselves and were never affected.
  Anything watching several events at once must cancel the losers too — see
  `AdminInterface.generate_any_game_updates`.
- No Alembic: edit `backend/model.py`, then `npm run resetdb` in dev — and
  never on the live droplet, which is now carrying a real game.
- **Venues** (`backend/venues.py`) are the single place where a location is
  defined: map image key, the two reference points that georeference it, the
  corner mini-map width, and the landmarks. One is active at a time
  (`ACTIVE_VENUE` — comment / uncomment), and the frontend reads it from
  `GET /api/get_venue`. Playing somewhere new means adding a `Venue` there,
  dropping the map into `react-ui/src/images/` and adding one line to
  `react-ui/src/mapImages.js` — nothing in `MapView.js` should need touching.
  Note the resort venue currently active is a temporary test one.
- **The test world costs money to change, and only in one direction.** An
  image in `backend/test_world/data/images/` is content-addressed on its
  prompt, inputs, model and parameters, so editing a scene description
  regenerates exactly the images it touches and nothing else — and re-running
  `generate` when nothing has changed sends nothing at all. Google models are
  refused in both the generation and the localisation paths by an explicit
  guard, because the recogniser under test is a Google model and using one to
  make or measure its own inputs would make the benchmark circular.
  Measurements from `observe` are recorded and reported, never acted on:
  wanting a different picture means editing the scene description, which is
  the only lever. **Dry-run `generate` and read the plan before spending** —
  the `regenerate-test-world-images` skill is the full pipeline.
- Run `pre-commit run --all-files` before committing, and never introduce
  `FIXME` comments (CI gate).
- **AI shot review** (`backend/ai_shot_review.py`, `backend/shot_vision.py`,
  `backend/vision_client.py`) is off unless `OPENROUTER_API_KEY` is set *and* an
  admin ticks the per-game **recognition** toggle (`ai_shot_review_enabled`) —
  that toggle only annotates the queue. A second, independent per-game toggle
  (`ai_auto_actions_enabled`, default off) lets `backend/shot_auto_actions.py`
  auto-apply verdicts whose overall confidence ≥ `confident_threshold` (0.6),
  but only ever to the **head** of the queue: an unsettled head blocks the
  shots behind it. **The escalation pass stands in for the admin**
  (`backend/shot_escalation.py`, `OPENROUTER_ESCALATION_MODEL`): unset, it
  mirrors `OPENROUTER_MODEL` (`vision_client.get_escalation_client`), so with
  recognition configured and the per-game `ai_escalation_enabled` toggle on
  (its default), *nothing reaches a human until it has looked*, with no second
  model to set up. Point `OPENROUTER_ESCALATION_MODEL` at a genuinely stronger
  model to make escalation a real second opinion rather than the same model
  asked twice. Every way the weak reading fails to
  settle a shot — unconfident, fits nobody (`inconsistent`), a tie, an
  unrecognised outcome, or too little read to name anybody — escalates. So
  the readable-channel test (4, or 3 including armbands) no longer picks who
  gets a second opinion; it only decides whether the **weak** reading may name
  somebody on its own. A stored escalation is consulted *before* the weak
  reading is retried — its verdict outranks the reading that prompted it,
  including one an admin fired by hand (`admin_escalate_shot`, "Run escalated
  review"). The admin sees a shot only when the escalation model handed it back
  ("unsure", or below its own thresholds: 0.75 to name a player, 0.6 for a
  miss/bystander), when the escalation errored, or when there is no vision at
  all to ask (`OPENROUTER_API_KEY` unset) — that toggle is a kill switch
  inside an opted-in feature, not a third opt-in, which is why it defaults
  **on**. A pending escalation blocks
  the queue the same way. "Too few channels" is never a bystander verdict on
  its own — `classify()`'s old mapping to that is retired. A fourth per-game
  toggle, `ai_resolve_everything_enabled` (default off), relaxes only the
  confidence gate: an unconfident verdict resolves to the best call so the
  players can appeal it (see appeals, below) rather than waiting on the admin
  — but only once escalation is out of the picture, since a second
  opinion that is actually coming beats a forced guess. It never forces a
  resolution with nothing to resolve *from* — no usable review, an
  inconsistent reading, no ranking at all, an errored escalation — since with
  nobody to notify, nobody can appeal; strict queue ordering is untouched
  either way. A vision call that errors or answers off-schema is retried
  automatically (`ai_shot_review.REVIEW_ATTEMPTS`, 3 attempts) before it is
  stored as an error, since that is what pressing "re-run review" did by hand.
  `OPENROUTER_MODEL` is a placeholder awaiting a trial against real photos, so
  keep the client and the prompt model-agnostic: no provider-specific features,
  and never assume structured-output support. User-facing strings call all of
  this **"CharlesBot"**, never "AI" — the `ai_*` field, column and module
  names stay as they are (renaming would invalidate stored review payloads),
  with a boundary comment at each display site recording the convention.
- **Appeals** (roadmap R8): either party to a resolved shot may appeal it once,
  from a per-game budget (`User.appeals_remaining`, `APPEALS_PER_GAME = 3` in
  `backend/model.py`), refunded when upheld. Appeal columns live on `Shot`
  (`appeal_state`, `appealed_at`, `shooter_appeal_reason`,
  `target_appeal_reason`) — appealing marks the shot contested and re-opens it
  for the admin, but never re-enters the auto-action drain: contested shots
  have their own list (`admin_get_contested_shots_info`), ordered oldest
  complaint first. Upheld is *inferred* at re-adjudication rather than chosen
  (`_settle_appeal`), and miss and bystander count as one ruling there: both
  say the shot hit no player, so swapping one for the other rejects the appeal
  rather than refunding it. A checked shot stays checked otherwise; resolutions are
  terminal.
- The **replay workbench** (`/admin/replay`, `react-ui/src/ShotReplay.js` →
  `admin_replay_shot_review`) trials a vision contract against real shots
  without storing anything. That contract is three things, and they must stay
  editable *together*: the prompt, the `zoom_mode` (`shot_vision.ZOOM_SCREENED`
  / `ZOOM_UPFRONT` / `ZOOM_SINGLE` — which decides the follow-up turns) and the
  response `schema`. Vary the wording alone and the model is still forced to
  answer the old schema through the old follow-ups, so the new prompt has no
  effect — that was a real bug (roadmap R1). `build_prompt(zoom_mode=…)` writes
  the zoom wording that matches the shape being run; keep them in step.
- **`Shot.heading` is captured, not consumed.** The compass heading
  `MyWebcam.js` records at the moment of a shot exists because it cannot be
  recovered after a game night. Nothing in `backend/shot_identification.py` or
  `backend/identity/` reads it, and that is deliberate until there is real data
  to fit a model against — the admin's per-shot map
  (`react-ui/src/ShotMap.js`) only displays it. See `docs/roadmap.md` R5 and
  #5. The fix accuracy that rides each `set_location` **is** consumed: it is
  σ_fix in the location term (`_effective_sigma_m`), which is why a phone that
  honestly reports a bad fix is discounted rather than believed.
- **A shot is scored as of when it was taken.** `rank_candidates` reads
  `at_time` from the shot's own `time_created` (`shot_epoch`). Fix age is what
  turns the location term off, so scoring against the present clock ages every
  fix by however long the shot sat in the queue — which is worst exactly when
  the queue is longest. There is no fallback: `shot_epoch` **raises** on a
  shot with no time, `shots.time_created` is `nullable=False`, and
  `submit_shot` is the only writer. The way that actually goes wrong is not a
  corrupt row but a **columns-only query that forgets to select it** — which is
  what `QueueHead` did, so the auto-action drain was scoring every head as
  "now". Any new projection that will be passed to identification needs
  `time_created` in it.
- **The vision model never sees the code.** It is asked only what colour each
  garment is and how sure it is; all the error correction happens
  deterministically in Python. Identification (`backend/shot_identification.py`)
  scores that reading against what each living candidate is *actually wearing*
  (their slot plus any overrides), not against the codebook — so a player in a
  non-canonical outfit is still identified, which the older
  `shot_vision.slot_candidates_from_review` path cannot do. That path survives
  only as the auto-action readability gate (`confident_channel_count`): with
  only `k` readable channels an MDS code matches *some* codeword for any
  reading, so it vouches for nothing however it is scored.
- The colour scheme players wear lives in `backend/identity/config.py`
  (4 channels × 7 colours, `[4,2,3]` Reed–Solomon). Seven everywhere, but **four
  different physical palettes**: `main` (which is now the t-shirt's alone, plus
  the fallback for any channel without one), `TROUSERS_PALETTE`, `HAT_PALETTE`
  and `ARMBANDS_PALETTE`. Only the *cardinality* reaches the code, so nothing
  has to match anything else and almost nothing does.
  `backend/identity/` must stay pure — no database, web or vision imports. See
  `docs/team_photo_identification_plan.md` for the reasoning.
- **Trousers are their own palette** (`TROUSERS_PALETTE`), simulated separately
  for legs and sharing only `black` with the main one, hex and all: black, grey,
  off-white, blue, red, olive, mustard. Three achromatics spread across the
  lightness range plus four chromatics spread around the hue circle — the
  neutrals are separated by `L*`, which survives a colour cast, rather than by
  hue. See plan §9.1.
- **The hat and armband palettes are measured, not designed** (`HAT_PALETTE`,
  `ARMBANDS_PALETTE`, added 2026-08-29). Those two garments have been bought, so
  the kit in Charles's house is the ground truth and the CIEDE2000 optimisation
  is superseded for them — hats are black, navy, green, burgundy, rust, tan,
  salmon; armbands are brown, blue, purple, lime, red, orange, yellow. Their
  hexes were taken off photographs, each white-balanced against the paper in its
  own frame (both were lit by a phone torch, whose low-CRI spectrum is why the
  saturated reds — burgundy above all — are the least certain entries and want a
  daylight re-shoot if they ever need to be exact). Two consequences worth
  carrying: the armbands have **no black**, so
  the withheld slot 0 is black/black/black/**brown** rather than all-black; and
  the hat is now the least separated channel in the scheme (min ΔE2000 14.2,
  burgundy/rust), which `d = 3` absorbs but which is the first suspect if
  identification underperforms. See plan §9.1a and roadmap R6.
- **Colour definitions (`COLOUR_BUCKETS`) are keyed per channel**, like
  `PALETTE_HEX`, with a per-colour fallback to `main` — because the channels
  genuinely disagree: charcoal is `black` on the legs (grey is two stops away)
  and explicitly not black on a top (no grey to catch it), and `red` means a
  pillar-box bandage on the arm but a much darker dye on a t-shirt. Three of the
  four channels now define most of their own terms; the hat's matter most,
  because burgundy, rust and salmon are three warm reds a loose definition would
  let collapse. Both audiences that
  answer in these words render each channel's own: the swatch notes on `/pick`
  (`channels[].notes` from `_channels_payload`) and the vision prompt, which
  puts them inside that channel's question rather than in one shared list. Keep
  the two in step — identification scores what the player said against what the
  model said, so they must mean the same thing by a colour name.
- One channel (`TEAM_CHANNEL` in that config, the **hat**) is spent on telling
  teams apart by eye: the join-QR pre-allocation
  (`backend/identity/allocation.py` → `identity_admin.build_join_codes`) hands
  each team a block of slots sharing one hat colour, and no two teams share a
  colour. That is an allocation policy only — the decoder is unaffected. A hat
  colour covers seven slots — six for black, and only because slot 0 is withheld
  and its hat symbol is black; the palettes have nothing to do with it — so a
  bigger team picks up a whole second colour rather than sharing a part-used
  one. Six teams of five fit comfortably: each takes one colour and black is
  never reached.
- `Team.identity_colour` is **pinned** the first time `build_join_codes` runs
  for a game, and left untouched on every later call (even after a new team is
  added) — so a team that has already started picking outfits never gets
  re-coloured out from under players who chose against its original hat.
- Players choose their own outfit rather than being assigned one: a team join
  code (`slot=None` in `JoinCodeModel`) sends the scanner to `/pick`, which
  offers a ranked, paginated list built by
  `identity_admin.outfit_options`. Ranking is canonical-first — an option
  needing zero overrides from a Reed–Solomon codeword always outranks a rarer
  one needing even one — then rarity, gated throughout on Hamming distance
  against everyone already placed in the game.
