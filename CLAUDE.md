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
  - `ticker.py` / `ticker_message_dispatcher.py` — in-game announcements.
  - `items.py` / `item_actions.py` — collectible items and their effects.
  - `circles.py` — geographic game zones (exclusion / next / drop circles).
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
  - Views: `UserMode.js`, `AdminMode.js`, `ShotQueue.js`, `MapView.js`, etc.
  - Styling: CSS Modules (`*.module.css`) + Bootstrap; React hooks only (no Redux).
- `server/` — Express server (`server/index.js`) that serves the built React app
  and proxies `/api` in production (`npm run frontend`).
- `tests/` — pytest suite (`test_backend.py`, `test_items.py`, `test_shots.py`,
  `test_ticker.py`, `test_admin_mode.py`, `test_user_interface.py`,
  `test_sse.py`, `test_selenium.py`; fixtures in `conftest.py` and
  `shared_fixtures.py`).
- Root: `package.json` (orchestration scripts), `flake.nix` / `.envrc` (Nix dev
  env), `compose*.yml` + `Caddyfile` (deployment).

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
- Run `pre-commit run --all-files` before committing, and never introduce
  `FIXME` comments (CI gate).
