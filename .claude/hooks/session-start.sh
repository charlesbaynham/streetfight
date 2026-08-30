#!/usr/bin/env bash
#
# SessionStart hook: make a fresh checkout able to run the tests, the linters
# and the app, before an agent asks it to.
#
# This runs on a laptop as readily as in a cloud container, so **every step is
# conditional on its own output being absent**. Two things in particular are
# never overwritten:
#
#   .env       gitignored, and where a real OPENROUTER_API_KEY lives. This is
#              why the hook does the safe parts of `npm run bootstrap` by hand
#              rather than calling it: bootstrap ends with `cp .env.dev .env`,
#              which would replace a working key with a comment.
#   cert.pem   likewise gitignored; regenerating it for no reason re-triggers
#   key.pem    every browser's "not trusted" interstitial.
#
# The dependency installs are lock-driven and idempotent, so they run every
# time: that is what fixes a venv left stale by a pull that moved uv.lock.
# `npm run build` is deliberately not run - it is a production build of the
# frontend, and every path an agent uses (`npm run dev`, the run-mobile-app
# skill) serves from the dev server instead.
#
# Nothing here is fatal. A step that fails logs why and the next one still
# runs; a session with no network still starts, just without deps.

set -uo pipefail

# Async: the session starts immediately and this continues in the background.
# `.claude/session-start.log` is the running commentary and
# `.claude/.session-start.done` appears only when every step has finished, so
# anything that needs the environment ready can wait on the marker rather than
# guess. See "Session bootstrap" in CLAUDE.md.
echo '{"async": true, "asyncTimeout": 900000}'

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$ROOT" || exit 0

MARKER="$ROOT/.claude/.session-start.done"
LOG="$ROOT/.claude/session-start.log"
rm -f "$MARKER"
: >"$LOG"

step() { printf '\n=== %s ===\n' "$1" >>"$LOG"; }
note() { printf '%s\n' "$1" >>"$LOG"; }

step "environment file"
if [ -f .env ]; then
    note "kept the existing .env (never overwritten - it may hold real keys)"
elif [ -f .env.dev ]; then
    cp .env.dev .env && note "created .env from .env.dev"
else
    note "no .env.dev to copy from; skipped"
fi

step "dev certificate"
if [ -f cert.pem ] && [ -f key.pem ]; then
    note "kept the existing cert.pem / key.pem"
elif command -v openssl >/dev/null 2>&1; then
    openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 \
        -days 3650 -nodes \
        -subj "/C=XX/ST=StateName/L=CityName/O=CompanyName/OU=CompanySectionName/CN=CommonNameOrHostname" \
        >>"$LOG" 2>&1 && note "generated a self-signed cert" || note "openssl failed; skipped"
else
    note "no openssl on PATH; skipped"
fi

step "python dependencies"
if command -v uv >/dev/null 2>&1; then
    # --frozen: install exactly what uv.lock says and never re-resolve, which
    # is the same resolution Nix builds the deployed container from.
    if uv sync --frozen --all-groups >>"$LOG" 2>&1; then
        note "uv sync --frozen --all-groups: ok"
    else
        note "uv sync failed - see above. Try 'nix develop' if you have Nix."
    fi
else
    note "no uv on PATH; skipped (a Nix dev shell provides Python instead)"
fi

step "node dependencies"
if command -v npm >/dev/null 2>&1; then
    # The root package.json has an `install` lifecycle script that installs
    # react-ui, so this one command covers both trees.
    if npm install --no-audit --no-fund >>"$LOG" 2>&1; then
        note "npm install (root + react-ui): ok"
    else
        note "npm install failed - see above"
    fi
else
    note "no npm on PATH; skipped"
fi

step "playwright driver"
# Only where a Chromium is already on disk - i.e. a Claude Code container,
# which sets PLAYWRIGHT_BROWSERS_PATH. On a laptop this is somebody's own
# business and the hook stays out of it. The driver lives in the cache rather
# than the repo so it survives between sessions and dirties nothing; the
# run-mobile-app skill reads STREETFIGHT_PW_DRIVER to find it.
DRIVER="${XDG_CACHE_HOME:-$HOME/.cache}/streetfight-pw-driver"
if [ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" ]; then
    note "PLAYWRIGHT_BROWSERS_PATH unset; skipped (not a preinstalled-browser container)"
elif [ -d "$DRIVER/node_modules/playwright" ]; then
    note "driver already at $DRIVER"
    [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "export STREETFIGHT_PW_DRIVER=$DRIVER" >>"$CLAUDE_ENV_FILE"
elif command -v npm >/dev/null 2>&1; then
    mkdir -p "$DRIVER"
    if (cd "$DRIVER" && npm init -y >/dev/null 2>&1 &&
        npm i --no-audit --no-fund playwright >/dev/null 2>&1); then
        note "installed the playwright driver at $DRIVER"
        [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "export STREETFIGHT_PW_DRIVER=$DRIVER" >>"$CLAUDE_ENV_FILE"
    else
        note "playwright driver install failed; the run-mobile-app skill can do it by hand"
    fi
fi

step "done"
date -u +"finished %Y-%m-%dT%H:%M:%SZ" >>"$LOG"
cp "$LOG" "$MARKER"
