---
name: run-mobile-app
description: Launch the streetfight app (FastAPI backend + React dev server) in a headless container and drive it with Playwright at a mobile viewport - fake camera, fake GPS, auto-joined player - to take screenshots of the user-facing UI. Use whenever you need to run the app, see a frontend change working, or screenshot user mode / admin pages. The game is mobile-only: never judge the UI at a desktop viewport.
---

# Run the app and screenshot it (mobile viewport)

The frontend is a mobile-first PWA; always render it at a phone viewport
(390x844, DPR 3, touch). The steps below cold-start the whole stack in a fresh
Linux container and end with a PNG of the in-game user view, with the player
already named, on a team, and holding ammo.

## 1. Setup — already done for you

The `SessionStart` hook (`.claude/hooks/session-start.sh`) installs the Python
and node dependencies, writes `.env` if there isn't one, and — in a container
with a preinstalled Chromium — installs the Playwright driver into
`$STREETFIGHT_PW_DRIVER`. It runs in the background, so if you are early:

```bash
until [ -f .claude/.session-start.done ]; do sleep 5; done   # or just read the file
```

`.claude/session-start.log` says what it did and what failed. Prefix Python
calls with `uv run` (or use `.venv/bin/...`) unless you are in `nix develop`.

Only if the hook did not run, or reported a failure:
`uv sync --frozen --all-groups`, `npm install`, and for the driver
`mkdir -p "$SCRATCH/driver" && cd "$SCRATCH/driver" && npm init -y && npm i playwright`
— in a scratch dir **outside** the repo. Never run `playwright install` where
`PLAYWRIGHT_BROWSERS_PATH` is already set (Claude Code containers set
`/opt/pw-browsers`); the browser is on disk already.

## 2. Database

```bash
# .env sets the sqlite DB, admin password "password", and MAKE_DEBUG_ENTRIES,
# which creates an *active* sample game (id
# a47c0fcf-67bd-4c91-a83b-1ac6c3d8fd43) with ten empty teams.
set -a && . ./.env && set +a && uv run python -m backend.reset_db
```

## 3. Launch backend and frontend (both in background)

```bash
# Backend on :8000
set -a && . ./.env && set +a && uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
# wait until: curl -sf http://127.0.0.1:8000/api/hello   -> {"msg":"Hello world!"}

# Frontend on :3000. The package.json start script hardcodes HTTPS=true, so
# bypass it: plain HTTP is fine because localhost is a secure context, so the
# camera API still works.
cd react-ui && HTTPS=false BROWSER=none PORT=3000 npx react-scripts start
# ready when: curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/  -> 200
# (first compile takes ~1 min; the CRA dev proxy forwards /api to :8000)
```

## 4. Screenshot the user view

```bash
cd "${STREETFIGHT_PW_DRIVER:-$SCRATCH/driver}"
cp <this skill dir>/scripts/screenshot_usermode.js .
node screenshot_usermode.js usermode.png
```

The script (see `scripts/screenshot_usermode.js`) does, in order:

1. Launches Chromium with `--use-fake-ui-for-media-stream
--use-fake-device-for-media-stream` - the "camera" becomes a green test
   pattern, so `WebcamView` renders without hardware.
2. Opens a context with a 390x844 touch viewport, granted `camera` +
   `geolocation` permissions, and a fake GPS position.
3. Loads `/`, then in-page `fetch`es (sharing the session cookie):
   `set_name`, admin login, `admin_add_user_to_team`, `admin_give_ammo`.
4. Reloads and screenshots. **Look at the PNG** - a blank frame means the
   launch failed.

## Gotchas (learned the hard way)

- **`POST /api/join_game` is broken** (`UserInterface` has no `join_game`
  method - dead code). Players really join via
  `admin_add_user_to_team?user_id=..&team_id=..`. Get a team id from
  `GET /api/admin_list_games` after admin auth.
- **Admin auth is a cookie**: `POST /api/admin_authenticate?password=password`
  on the same browser context; subsequent `admin_*` calls just work. The
  admin pages at `/admin` need the same cookie (log in at `/admin/login` or
  call the endpoint before navigating).
- **`admin_give_ammo` 500s if the user is not yet on a team** (the ticker
  needs a game id) - always add-to-team first.
- **The user lands in `OnboardingView`** unless all three hold: name set,
  game active, camera + location permissions granted. Permissions are
  re-polled every 5 s, so a just-granted permission can take a moment.
- The screenshot's green background is the fake camera feed, not a bug.
- To also populate the HUD weapon slot, use
  `POST /api/admin_set_weapon?user_id=..&weapon=..` (valid names come from
  `WEAPON_NAME_LOOKUP` in `backend/item_actions.py`).
