# Deploying to a cloud VM (DigitalOcean droplet)

The runbook for running the game from a plain cloud VM with Docker installed -
written for the dry run of 30 Aug 2026, but nothing in it is specific to that
day. The droplet replaces the home-lab LXC deployment (see the cutover section
at the bottom); it runs the images CI publishes to ghcr.io (public, no
registry login needed) and auto-updates them on every master push via
watchtower, matching the pull-on-push behaviour the LXC had. The droplet
needs Docker only - no Nix, no Node, no Python.

The public origin is **`https://streetfight.houseabsolute.co.uk`** - the same
address the home deployment served, so nothing already shared changes. On the
droplet, Caddy terminates TLS itself (at home that was traefik's job), which
is what the `SITE_ADDRESS` knob in the Caddyfile exists for.

## What you need before starting

- A droplet (the smallest tier is plenty for ~10 players; 1 GB RAM is fine -
  the heavy lifting, vision review, happens on OpenRouter's servers, not ours).
- **DNS pointing at it**: the `streetfight.houseabsolute.co.uk` A record moved
  to the droplet's IP, **DNS-only (grey cloud) in Cloudflare, not proxied** -
  Caddy answers Let's Encrypt's HTTP challenge itself and can't do that from
  behind Cloudflare's proxy. Phones refuse the camera and geolocation APIs on
  an untrusted origin, and the whole game is camera and geolocation, so a
  working certificate is a hard requirement, not a nicety.
- The secrets escrowed from the home deployment (see cutover, below).

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
SITE_ADDRESS=streetfight.houseabsolute.co.uk
WEBSITE_URL=https://streetfight.houseabsolute.co.uk

# Inside the compose network the frontend proxies to the backend container,
# not localhost. Delete the .env.dev line or set it explicitly:
API_URL=http://backend:8000

# Secrets - the values escrowed from the home deployment, not fresh ones.
# SECRET_KEY signs every join link that gets sent out: keeping the old key
# keeps every link already shared alive across the cutover. (Starting truly
# fresh instead? openssl rand -hex 32 - and accept that old links die.)
SECRET_KEY=<escrowed>
ADMIN_PASSWORD=<escrowed>

# Production behaviour
LOG_LEVEL=INFO
MAKE_DEBUG_ENTRIES=     # blank: no sample game
DEBUG_DATABASE=         # blank
# RESET_DATABASE stays unset - the schema is created automatically on first
# boot (create_all); setting this wipes the database on every restart.

# CharlesBot - the dry run's whole point is exercising this, so all keys set
OPENROUTER_API_KEY=<escrowed>
OPENROUTER_MODEL=google/gemini-3.7-flash-20260813
OPENROUTER_ESCALATION_MODEL=google/gemini-3.7-pro-20260813

# ghcr images + auto-update on master pushes (watchtower polls every 30 s)
COMPOSE_FILE=compose.yml:compose.watchtower.yml
```

Then:

```bash
docker compose pull
docker compose up -d frontend backend watchtower
```

Naming the services skips `cloudflare-ddns`, which a droplet with a static IP
and a manually created A record doesn't need (unconfigured it just
crash-loops noisily).

If the droplet runs a firewall (`ufw` is enabled by default on DigitalOcean's
Docker image), open 80 and 443: `ufw allow 80,443/tcp`. Port 80 must be open
even though the game runs on 443 - it's how Let's Encrypt's HTTP challenge
arrives.

`compose.ghcr.yml` is the same image source *without* watchtower, for when a
deployment should stay pinned until an explicit `docker compose pull` -
swap it into `COMPOSE_FILE` in place of `compose.watchtower.yml` if that's
ever wanted.

## Verifying it

1. `https://streetfight.houseabsolute.co.uk` loads with a padlock (no
   certificate warning - a warning means SITE_ADDRESS/DNS is wrong, or the
   record is still proxied, and phones will refuse the camera).
2. `https://streetfight.houseabsolute.co.uk/api/get_version` returns the
   deployed git revision, and it matches the master commit you expect.
3. Push a trivial commit to master and watch `docker compose logs -f
   watchtower` pick it up - confirms auto-deploy works before it matters.
4. On a real phone: log in as admin (`/admin`), create a game and a team,
   and open the identity page - the team join links it mints should start
   with `https://streetfight.houseabsolute.co.uk`. Follow one and check the
   browser asks for camera and location permissions.

## Day-of notes

- **Auto-update is on by design** (watchtower tracks `latest`, which tracks
  master), so a push to master redeploys the live game within ~30 s. On a
  game day that cuts both ways: it's the fastest possible path for shipping a
  fix mid-game, and it means *don't merge to master during play unless you
  mean it*.
- **State lives in named volumes** (`database`, `caddy_data`) plus the
  `./logs` and `./processed_shots` bind mounts, so a watchtower redeploy or
  `docker compose down` keeps all of it; `docker compose down -v` destroys
  the database and the certificates. To wipe between the dry run and the
  real game, prefer admin reset from the UI, or `down -v` and re-`up`.
- Shot photos land in `./processed_shots` and the database volume - worth
  `tar`-ing off the droplet after the game: they are the labelled training
  data R1/R2 feed on.

## Cutover from the home LXC deployment

The game currently runs on the home network as a Proxmox LXC behind traefik
(which terminates TLS for `streetfight.houseabsolute.co.uk`), auto-redeployed
on new releases. **The authoritative description of that setup - how the
secrets are defined, how the auto-redeploy works, and how to stand it down -
lives in the home-infrastructure repository, which is granted to the session
doing the cutover.** Read it first; this section fixes the *order* of the
cutover, not the mechanics of the home side, and where the two disagree the
infrastructure repo wins.

Order matters: escrow first, then point DNS at the droplet, then stop the
home side - so there is never a moment with secrets in only one place or the
domain pointing at nothing.

1. **Escrow the secrets**, from wherever the infrastructure repo says they
   are defined. Needed on the droplet: `SECRET_KEY`, `ADMIN_PASSWORD`,
   `OPENROUTER_API_KEY` (and any other `OPENROUTER_*` values); the
   Cloudflare API token is also worth having for step 3's DNS change.
   Transfer them straight into the droplet's `.env` over SSH - never into a
   repo, a PR, a pastebin or a chat log.
2. **Archive the lab's game data** before touching anything: the database
   and the processed-shots directory, tar'd off the LXC. Nothing migrates to
   the droplet (the dry run starts from a clean database); this is purely so
   the resort-era shots and telemetry aren't lost with the container.
3. **Move DNS**: repoint the `streetfight.houseabsolute.co.uk` record from
   the home IP to the droplet's static IP, DNS-only (grey cloud). Drop the
   TTL first if it's long. The droplet's Caddy obtains its certificate on
   the first request after propagation.
4. **Verify the droplet** end to end (section above) *while the LXC is still
   up* - if something's wrong, DNS can go straight back.
5. **Stop the home side**, per the infrastructure repo's procedure: disable
   whatever performs the automatic redeployment, stop the LXC, and remove
   the traefik route. Disabling the auto-redeploy must not be skipped, or a
   later release quietly resurrects the container.

This game repo's CI needs no change: it publishes artefacts (images, the LXC
template) and has no route into the home network, so once the home side stops
consuming them the deployment is stood down. Removing the
`build_lxc_template` job is later cleanup, not part of the cutover.
