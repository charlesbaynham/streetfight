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

## Planned work

`docs/roadmap.md` is the roadmap: the agreed future work, re-prioritised, with
the files each item lands in and the open questions still outstanding. Read it
before starting anything substantial - several items are deliberately sequenced
behind each other, and a few are "wire up what already exists" rather than the
rewrite they sound like. Keep it current: when an item ships, say so there.

## Contributing

Attempt to match existing code styles where possible. Prefer self-documenting code over verbose comments. Where a pattern has already been demonstrated elsewhere in the codebase, generalise and reuse it rather than minting a new, different version.

For a feature that affects the backend or the frontend functionality, ensure to add unit tests. One caveat to this is: don't add unit tests that test very simple behaviour. For example, if you add a button that says "hello", do not add a unit test that says, "Does the button say 'hello'?" We can trust code that far.

Keep the agent documentation up to date, such as this file and any other documentation for agents in the repository.

It's an unpolished personal project (see `README.md`), so favour pragmatic,
minimal changes over large refactors.

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
    turns its reference points into map geometry; `mapImages.js` is the bundled
    map images the server's `map.image` key resolves against.
  - Views: `UserMode.js`, `AdminMode.js`, `ShotQueue.js`, `MapView.js`, etc.
    `PickOutfit.js` (route `/pick`) is the player-facing outfit-picking page a
    team join code lands on; it shares the colour `Swatch.js` component with
    the admin identity pages (`AdminIdentity.js`, `IdentityDemo.js`).
  - Styling: CSS Modules (`*.module.css`) + Bootstrap; React hooks only (no Redux).
- `server/` — Express server (`server/index.js`) that serves the built React app
  and proxies `/api` in production (`npm run frontend`).
- `scripts/` — standalone analysis tools, not part of the app.
  `simulate_code_capacity.py` Monte-Carlos how much identity capacity is lost if
  players pick outfits freely instead of taking the codeword the scheme assigns
  (see `docs/team_photo_identification_plan.md` §12.5).
- `tests/` — pytest suite (`test_backend.py`, `test_items.py`, `test_shots.py`,
  `test_ticker.py`, `test_admin_mode.py`, `test_user_interface.py`,
  `test_sse.py`, `test_selenium.py`; fixtures in `conftest.py` and
  `shared_fixtures.py`).
- Root: `package.json` (orchestration scripts), `pyproject.toml` + `uv.lock`
  (the Python dependencies), `flake.nix` / `.envrc` (Nix dev env),
  `compose*.yml` + `Caddyfile` (deployment).

## Setup & run (development)

All commands below are run from the repo root.

```bash
# First-time setup: npm i + generate self-signed cert + build frontend + cp .env.dev .env
npm run bootstrap

# Run the backend (uvicorn with autoreload)
npm run backend          # uvicorn backend.main:app --reload --reload-dir backend

# Run the frontend dev server (HTTPS) in another terminal
npm run dev              # cd react-ui && npm start

# ...or run both at once
npm run dev_both

# Reset / initialise the database
npm run resetdb          # python -m backend.reset_db
```

There are **no database migrations** (no Alembic). The schema is created from the
ORM models in `backend/model.py` via `create_all()`. After changing a model,
reset the dev DB with `npm run resetdb`.

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
| `OPENROUTER_TIMEOUT_SECONDS` | Per-request timeout for the vision call      |
| `OPENROUTER_REASONING_EFFORT` | Reasoning-effort override (none/minimal/low/medium/high/xhigh/max); unset = no override sent |
| `AI_SHOT_REVIEW_CONCURRENCY` | Parallel reviews when draining a backlog     |

## Deployment (brief)

`docker compose up` runs three services (`compose.yml`): a **Caddy** frontend
(serves the React build, reverse-proxies `/api`), the **FastAPI** backend, and a
**Cloudflare DDNS** sidecar. Optional overlays add Traefik
(`compose.traefik.yml`) or auto-update via Watchtower (`compose.watchtower.yml`).
Images are built from the Nix flake
(`nix build .#dockerFrontend .#dockerBackend`) and published to ghcr.io by CI
(`.github/workflows/build_images.yml`).

## Conventions & gotchas for agents

- The app uses **synchronous SQLAlchemy under async FastAPI**. Database access is
  managed by the `@db_scoped` decorator (`backend/database_scope_provider.py`) —
  rely on it rather than hand-managing sessions/commits.
- Realtime updates flow through `asyncio_triggers` → SSE streams in
  `sse_event_streams.py`. When you change state that clients observe, make sure
  the corresponding update event is triggered.
- No Alembic: edit `backend/model.py`, then `npm run resetdb` in dev.
- **Venues** (`backend/venues.py`) are the single place where a location is
  defined: map image key, the two reference points that georeference it, the
  corner mini-map width, and the landmarks. One is active at a time
  (`ACTIVE_VENUE` — comment / uncomment), and the frontend reads it from
  `GET /api/get_venue`. Playing somewhere new means adding a `Venue` there,
  dropping the map into `react-ui/src/images/` and adding one line to
  `react-ui/src/mapImages.js` — nothing in `MapView.js` should need touching.
  Note the resort venue currently active is a temporary test one.
- Run `pre-commit run --all-files` before committing, and never introduce
  `FIXME` comments (CI gate).
- **AI shot review** (`backend/ai_shot_review.py`, `backend/shot_vision.py`,
  `backend/vision_client.py`) is off unless `OPENROUTER_API_KEY` is set *and* an
  admin ticks the per-game **recognition** toggle (`ai_shot_review_enabled`) —
  that toggle only annotates the queue. A second, independent per-game toggle
  (`ai_auto_actions_enabled`, default off) lets `backend/shot_auto_actions.py`
  auto-apply verdicts whose overall confidence ≥ `confident_threshold` (0.6),
  but only ever to the **head** of the queue: an ambiguous head stays with the
  admin and blocks the shots behind it.
  `OPENROUTER_MODEL` is a placeholder awaiting a trial against real photos, so
  keep the client and the prompt model-agnostic: no provider-specific features,
  and never assume structured-output support.
- The **replay workbench** (`/admin/replay`, `react-ui/src/ShotReplay.js` →
  `admin_replay_shot_review`) trials a vision contract against real shots
  without storing anything. That contract is three things, and they must stay
  editable *together*: the prompt, the `zoom_mode` (`shot_vision.ZOOM_SCREENED`
  / `ZOOM_UPFRONT` / `ZOOM_SINGLE` — which decides the follow-up turns) and the
  response `schema`. Vary the wording alone and the model is still forced to
  answer the old schema through the old follow-ups, so the new prompt has no
  effect — that was a real bug (roadmap R1). `build_prompt(zoom_mode=…)` writes
  the zoom wording that matches the shape being run; keep them in step.
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
  (4 channels × 7 colours, `[4,2,3]` Reed–Solomon). `backend/identity/` must stay
  pure — no database, web or vision imports. See
  `docs/team_photo_identification_plan.md` for the reasoning.
- One channel (`TEAM_CHANNEL` in that config, the **hat**) is spent on telling
  teams apart by eye: the join-QR pre-allocation
  (`backend/identity/allocation.py` → `identity_admin.build_join_codes`) hands
  each team a block of slots sharing one hat colour, and no two teams share a
  colour. That is an allocation policy only — the decoder is unaffected. A hat
  colour covers five slots (four for black), so a bigger team picks up a whole
  second colour rather than sharing a part-used one.
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
