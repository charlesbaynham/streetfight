# Deploying to a cloud VM (DigitalOcean droplet)

The runbook for putting the game on the public internet from a plain cloud VM
with Docker installed - written for the dry run of 30 Aug 2026, but nothing in
it is specific to that day. It uses the images CI publishes to ghcr.io (public,
no registry login needed) via `compose.ghcr.yml`, so the droplet needs Docker
only - no Nix, no Node, no Python.

## What you need before starting

- A droplet (the smallest tier is plenty for ~10 players; 1 GB RAM is fine -
  the heavy lifting, vision review, happens on OpenRouter's servers, not ours).
- **A domain name pointing at it.** This is not optional: phones refuse the
  camera and geolocation APIs on an untrusted origin, and the whole game is
  camera and geolocation. Create an `A` record for e.g.
  `streetfight.example.com` → the droplet's IP before first boot, so Caddy can
  pass the Let's Encrypt challenge immediately.
- An OpenRouter API key, if CharlesBot is playing.

## Steps

```bash
# On the droplet
git clone https://github.com/charlesbaynham/streetfight.git
cd streetfight
cp .env.dev .env
```

Then edit `.env`. The dev defaults are wrong for production in ways that
matter; set every one of these:

```bash
# The public origin. SITE_ADDRESS is what Caddy serves (and gets a
# certificate for); WEBSITE_URL is what every join link and item QR encodes,
# so they must agree.
SITE_ADDRESS=streetfight.example.com
WEBSITE_URL=https://streetfight.example.com

# Inside the compose network the frontend proxies to the backend container,
# not localhost. Delete the .env.dev line or set it explicitly:
API_URL=http://backend:8000

# Secrets. SECRET_KEY signs every join link that gets sent out - if it
# changes, every link already shared on WhatsApp dies. Generate it once
# (openssl rand -hex 32) and keep it for the life of the game.
SECRET_KEY=<openssl rand -hex 32>
ADMIN_PASSWORD=<something real>

# Production behaviour
LOG_LEVEL=INFO
MAKE_DEBUG_ENTRIES=     # blank: no sample game
DEBUG_DATABASE=         # blank
# RESET_DATABASE stays unset - the schema is created automatically on first
# boot (create_all); setting this wipes the database on every restart.

# CharlesBot (optional - leave the key blank and the admin adjudicates
# every shot by hand, which also works)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=google/gemini-3.7-flash-20260813
OPENROUTER_ESCALATION_MODEL=google/gemini-3.7-pro-20260813

# Use the ghcr images
COMPOSE_FILE=compose.yml:compose.ghcr.yml
```

Then:

```bash
docker compose pull
docker compose up -d frontend backend
```

Naming the two services skips `cloudflare-ddns`, which a droplet with a
static IP and a manually created A record doesn't need (unconfigured it just
crash-loops noisily).

If the droplet runs a firewall (`ufw` is enabled by default on DigitalOcean's
Docker image), open 80 and 443: `ufw allow 80,443/tcp`. Port 80 must be open
even though the game runs on 443 - it's how Let's Encrypt's HTTP challenge
arrives.

## Verifying it

1. `https://streetfight.example.com` loads with a padlock (no certificate
   warning - a warning means SITE_ADDRESS/DNS is wrong, and phones will
   refuse the camera).
2. `https://streetfight.example.com/api/get_version` returns the deployed
   git revision, and it matches the master commit you expect.
3. On a real phone: log in as admin (`/admin`), create a game and a team,
   and open the identity page - the team join links it mints should start
   with `https://streetfight.example.com`. Follow one and check the browser
   asks for camera and location permissions.

## Day-of notes

- **Pin the code by pinning the moment you pull.** `latest` tracks master, so
  run `docker compose pull && docker compose up -d frontend backend` when the
  code is where you want it, and don't pull again mid-game. (This is also why
  this runbook uses `compose.ghcr.yml` and not `compose.watchtower.yml` -
  watchtower would redeploy under the players' feet 30 s after a master push.)
- **State lives in named volumes** (`database`, `caddy_data`) plus the
  `./logs` and `./processed_shots` bind mounts. `docker compose down` keeps
  all of it; `docker compose down -v` destroys the database and the
  certificates. To wipe between the dry run and the real game, prefer
  admin reset from the UI, or `down -v` and re-`up`.
- Shot photos land in `./processed_shots` and the database volume - worth
  `tar`-ing off the droplet after the game before destroying it: they are the
  labelled training data R1/R2 feed on.
