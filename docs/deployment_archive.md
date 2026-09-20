# Deploying the public archive (`live`)

The runbook for **CT 124 (the Street Fight archive)** on the home lab, which
serves <https://streetfight.houseabsolute.co.uk> — the permanent, public
archive of the game played in Westminster on **19 September 2026**.

It exists for two reasons:

- **The printed QR codes are still out there.** 255 item codes and 4 team
  cards were printed on 17 September, and a printed code is a URL beginning
  with the minting machine's `WEBSITE_URL`. Every card taped around
  Westminster therefore points at `https://streetfight.houseabsolute.co.uk/?d=…`
  and will be found by strangers for years. Without this container that name
  falls through the house's `*.houseabsolute.co.uk` wildcard to the border
  router and returns a bare 404.
- **The essay.** `/how-it-works`, on the Reed–Solomon scheme behind the
  outfits, is the thing people actually want to read afterwards.

The droplet that served the game itself was destroyed on 19–20 September 2026.
Its runbook, and the install-once procedure, are kept as history in
[`deployment_droplet.md`](deployment_droplet.md).

## What a visitor gets

Nothing was switched off; the app is running normally against the real
database. Who sees what falls out of the app's existing rules:

| Visitor | Gets |
|---|---|
| A stranger (no name, no `game_id`, no team) | `WhatIsThis` at `/` — the holding page — and `/how-it-works`. `UserMode`'s `useIsStranger` chooses it *above* the SSE connection, so reading it holds no stream open. |
| A stranger who scanned a card | The same. `CollectItemsFromQueryParams` is mounted inside `BulletCount.js`, which a stranger never renders, so the `?d=…` sits unread in the address bar. **No special handling, and none is wanted.** |
| A returning player | Their own game back — shot history, outfit, map, ticker. The session cookie has `max_age` of ten years and is signed with `SECRET_KEY`, which is why the archive **must** carry the live key (below). |
| Charles | Everything, behind `ADMIN_PASSWORD`: the queue, the roster, and the spectator view of the finished game at `/admin/spectator`. |

⚠️ **There is no public view of the finished game, deliberately** (Charles,
2026-09-20). The 350 shot photographs are of real people at real places; they
stay behind the admin password. If a future change would put a roster, a
gallery or a spectator screen in front of an unauthenticated visitor, that is
a decision to take knowingly, not a tidy-up.

⚠️ **A returning player can still collect a card.** The live `SECRET_KEY`
means every printed code validates, and the last gate `collect_item` applies
is `user.team is None`, which a returning player passes. So a player who
scans a card in the street *will* collect it into the archived game. Accepted
knowingly rather than overlooked — the app was left fully live.

## The chain

```
scripts/deploy.sh live <ref>
  -> Deploy to archive (.github/workflows/deploy.yml) moves refs/heads/live
  -> build_images.yml runs on `live`, publishing
       streetfight-archive-lxc-proxmox-<label>-<sha>.tar.xz as a release asset
  -> cattle-deploy.timer on homeserver sees the new asset, verifies its
       sha256, destroys and recreates CT 124 from it, polls /api/get_version
  -> healthy: recorded as last-known-good
     unhealthy: last-known-good template redeployed
```

Same shape as staging, one branch along. **Merging to master deploys
nothing** — `live` and `staging` are both moved by hand.

The flake builds **two** templates from one definition
(`mkStreetfightTemplate`), differing only in the name baked into the
artifact, which is how the deployer tells them apart. `mkTemplate` calls every
template `proxmoxLxcTemplate`, so each is renamed to its service in the
flake's outputs and CI passes `attr: streetfight-archive` explicitly.

## The registry

Two lines' worth in `homelab-infra` — one, here, and nothing in
`internal.yaml`:

```yaml
# services.yaml
streetfight-archive: {vm_id: 124, ip: 10.0.1.48, port: 80, repo: charlesbaynham/streetfight, state_gb: 10, health_path: /api/get_version,
              publish: streetfight}
```

- The key **must** equal the template name in `flake.nix`: it is the asset
  prefix the deployer selects on.
- `publish: streetfight` is what puts it on the internet, through the border
  router. ⛔ **Do not create a Cloudflare A record** — the name is covered by
  the `*.houseabsolute.co.uk` wildcard and its wildcard certificate, and an
  explicit record beats the wildcard and shadows the route.
- `health_path` is not the default `/`: Caddy answers 200 from the static
  frontend with the backend dead, so `/` is a health check that cannot fail.
- ⚠️ **Not in the nightly `daily-all` backup**, deliberately (Charles,
  2026-09-20): the database is re-seedable from the Nextcloud archive and the
  secrets are escrowed on the Secret Server. See "Re-seeding" below.

## The state volume

`usb-zfs:subvol-9124-disk-0`, owned by reserved VMID **9124** — which is what
makes it outlive the container that is destroyed on every deploy. **Never
delete it.** It holds:

```
/data/db/data.db            the 19 September database, 216 MB, photographs and all
/data/secrets/streetfight.env   SECRET_KEY, ADMIN_PASSWORD, WEBSITE_URL
/data/logs/                 backend logs, and a copy of every shot photograph
/data/processed_shots/
/data/qr_codes.csv          empty here; nothing mints codes on this box
```

⚠️ **`SECRET_KEY` must be the live game's**, not a fresh one. It signs the
session cookies every player still holds, so a new key would lock all of them
out of their own history and make the restore pointless. It is escrowed on
CT 118 (the Secret Server) as `get_streetfight_secret_key`, and on CT 101
(the Street Fight staging container)'s state volume.

⚠️ `OPENROUTER_API_KEY` is deliberately **absent**: no vision calls, no
spend, and nothing in the archive needs re-reviewing.

## Re-seeding the database

The source of truth is the Nextcloud archive on CT 100 (the photo node), at
`Archives/streetfight/streetfight-game-archive-2026-09-19/` — 1.3 GB, 818
files, checksummed, and itself in the nightly backup to Backblaze. That is why
this container is not backed up.

On `homeserver`, with the deploy held
(`touch /var/lib/homelab-infra/cattle/streetfight-archive.hold`):

```bash
V=$(pvesm path usb-zfs:subvol-9124-disk-0)
mkdir -p "$V"/db "$V"/secrets "$V"/logs/images "$V"/processed_shots
cp streetfight-live-2026-09-19.db "$V"/db/data.db
sha256sum "$V"/db/data.db            # against the archive's SHA256SUMS
sqlite3 "$V"/db/data.db 'PRAGMA integrity_check;'
chown -R 100000:100000 "$V"
chmod 700 "$V"/secrets
```

Then release the hold and deploy. A sanity check on the restored database:

```bash
sqlite3 "$V"/db/data.db 'select count(*) from shots; select count(*) from users;'
# 350 shots, 58 users (31 named, 26 in a team)
```

⚠️ Order matters. `database.load()` runs `create_all()` at startup, so a
container that starts before the file is in place writes an empty database and
then serves it.

## Rolling back

Either re-deploy an older revision through the workflow, or name a generation
directly on `homeserver` (three are kept per service):

```bash
/opt/homelab-infra/bin/cattle-deploy.sh streetfight-archive template-20260920-abc1234
```

## Traps

1. **The one-page release window.** `resolve_release` in
   `homelab-infra/bin/cattle-deploy.sh` fetches `releases?per_page=100` — one
   page — and takes the newest carrying
   `streetfight-archive-lxc-proxmox-*.tar.xz`. This container is deployed
   rarely while staging churns, so after roughly a hundred further staging
   deploys its asset falls off page 1 and `deploy_one` logs *"no release
   published yet, skipping"* and returns 0, **silently**. The running
   container is unharmed; it simply stops updating. Deploy by explicit tag
   when that happens.
2. **Both templates share a release tag.** `template-<date>-<sha7>`, so if
   the same revision is deployed to both branches on the same UTC day, the
   second deploy's "drop a same-day release" step removes the first's asset
   too. Harmless — the other container resolves the previous release — but it
   explains an unexpected redeploy.
3. **⚠️ Do not run `bin/cattle-rm.sh streetfight`.** Its template-cache glob
   `streetfight-*` matches *both* `streetfight-staging-…` and
   `streetfight-archive-…`.
4. **`pct exec` has no PATH on a NixOS guest** — use
   `/run/current-system/sw/bin/systemctl`.
5. **Publishing a name rebuilds the border router.** The rendered Traefik
   config is hashed into a cloud-init snippet filename, which is ForceNew, so
   adding or changing `publish:` destroys and recreates VM 102 — about 25
   minutes on the current hardware, during which everything the house
   publishes is down. Not a concern for an ordinary app deploy here; only for
   a change to the registry line.
