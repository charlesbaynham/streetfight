# Deploying to staging

The runbook for the **staging** deployment: a Proxmox LXC container on the home
lab, at <https://streetfight-staging.i.houseabsolute.co.uk>.

It exists because the droplet does not have room for mistakes. That box carries a
real game whose join links are already in people's WhatsApp, so `master` cannot be
put on it casually. Staging is the same application from the same repository, on a
container that costs nothing to break, with a sample game in it instead of real
players.

> Live 30 Aug 2026. It is CT 101 on `homeserver` at `10.0.1.30`, reusing the
> container and the state volume that ran the game before the droplet cutover.

## The two deployments, side by side

| | Live (droplet) | Staging (home lab) |
| --- | --- | --- |
| Where | DigitalOcean, `167.172.62.186` | CT 101 on `homeserver`, `10.0.1.30` |
| Shape | Whole NixOS host (`nixosConfigurations.streetfight-cloud`) | LXC template (`.#proxmoxLxcTemplate`) |
| Branch | `live` | `staging` |
| Workflow | **Deploy to droplet** (`deploy.yml`) | **Deploy to staging** (`deploy-staging.yml`) |
| What moves | the `live` ref; the host polls it | the `staging` ref; CI publishes a template release, the hypervisor polls that |
| TLS | Caddy on the box, its own certificate | gardenfacer, on its `*.i.houseabsolute.co.uk` wildcard |
| Reachable from | the internet | the house LAN and the tailnet, and nowhere else |
| Database | real, irreplaceable | the sample game, rebuilt from a seed |

**Merging to master deploys neither.** Both are a deliberate act, and the two
branches are the whole gate.

## Deploying

Run the **Deploy to staging** workflow, or:

```bash
gh workflow run deploy-staging.yml -f ref=master
```

`ref` is anything git will resolve - a branch, a tag, a SHA - so putting a pull
request's head on staging to try it on a phone is the ordinary case. The workflow
checks that revision's LXC template built, then force-pushes it to
`refs/heads/staging`. That is all it does; it holds no credential for anything at
home.

What happens next, unattended, in about fifteen to twenty-five minutes:

```
staging moves
  -> build_images.yml runs on `staging` and publishes
       streetfight-staging-lxc-proxmox-<label>-<sha>.tar.xz as a release asset
  -> cattle-deploy.timer on homeserver sees the new asset, verifies its sha256,
       destroys and recreates CT 101 from it, and polls /api/get_version
  -> healthy: recorded as this service's last-known-good
     unhealthy: the last-known-good template is redeployed, and Charles is notified
```

The template filename *is* the deploy mechanism: Proxmox treats a container's
template as ForceNew, so a new filename replaces the container. The mechanics live
in `homelab-infra` (`bin/cattle-deploy.sh`, `services.yaml`) and are documented in
`ha-workspace`'s `docs/infra/cattle-containers.md`.

### Why the workflow does not wait for it

`deploy.yml` ends by polling the droplet's `/api/get_version` until it reports the
new revision. This one cannot: staging answers on `10.0.1.34`, a private address a
GitHub runner has no route to. The job therefore ends at the push and tells you
where to look:

- the *Build images* run on `staging`, which publishes the release asset;
- `journalctl -u cattle-deploy -f` on `homeserver`;
- and, from the LAN or the tailnet:

  ```bash
  curl -s https://streetfight-staging.i.houseabsolute.co.uk/api/get_version
  ```

### Rolling back

⚠️ **Re-running the workflow on an older revision may do nothing.** The deployer
picks the newest release *by publication time*, and the release tag is
`template-<date>-<sha7>` - so re-pushing a revision already built today re-uploads
its asset to the release that already exists, without changing that release's
timestamp, and nothing looks new.

Roll back on `homeserver` instead, naming the generation you want:

```bash
/opt/homelab-infra/bin/cattle-deploy.sh streetfight-staging template-20260830-c828e38
```

Three generations are kept per service, so recent ones are still downloadable.

## The sample game

Staging sets `services.streetfight.sampleGame`, which puts `MAKE_DEBUG_ENTRIES` in
the backend's environment. On start-up the app builds the deterministic test world
- six teams of five, each having picked an outfit through the real picking code -
if the database does not already hold it, and does nothing if it does. So the
first boot after a wipe populates it and every redeploy afterwards leaves it
alone.

Everything is derived from one seed (`reset_db.SAMPLE_SEED`), so a join code
printed from staging keeps working across a redeploy.

The sample game is thirty players standing still. To watch a game *happen* —
which is what the spectator screen exists for — use the admin page's **Fire demo
game** button (`backend/demo_game.py`), which drips the ten demo shots in one at
a time about thirty seconds apart. Staging is the right place for it: it refuses
outright if any player who is in a team is not one of the thirty simulated ones,
so it will not run against the live droplet, and here that check always passes.

Wiping staging back to nothing is free, and is the fix for a model change the
start-up column-adder cannot absorb (`database.add_missing_columns` adds new
columns to an existing database at start-up, but cannot drop or retype one). On
`homeserver`:

```bash
rm -f "$(pvesm path usb-zfs:subvol-9101-disk-0)"/db/data.db
```

The next deploy - or a restart - rebuilds the schema and the sample game.

## Secrets

Staging reads `/data/secrets/streetfight.env` on its state volume, the same
contract as every other deployment (`nix/streetfight.env.example`), and the unit
refuses to start without `SECRET_KEY`, `ADMIN_PASSWORD` and `WEBSITE_URL`.

It carries **the same secrets as the live game**, deliberately, with `WEBSITE_URL`
the one difference:

```
WEBSITE_URL=https://streetfight-staging.i.houseabsolute.co.uk
```

Two things follow from sharing `SECRET_KEY`. A printed item QR is signed with it,
so real printed codes work on staging - which is the point. And the admin password
is the same on both, so staging is not a place to hand the admin login to somebody
you would not hand the live one to.

Rotating anything there is a `seed-secret.sh` on `homeserver`; ⚠️ it *replaces* the
file rather than appending, so merge:

```bash
V=$(pvesm path usb-zfs:subvol-9101-disk-0)/secrets/streetfight.env
{ grep -v '^WEBSITE_URL=' "$V"
  printf 'WEBSITE_URL=https://streetfight-staging.i.houseabsolute.co.uk\n'
} | /opt/homelab-infra/bin/seed-secret.sh streetfight-staging streetfight.env
```

then `pct exec 101 -- /run/current-system/sw/bin/systemctl restart streetfight-backend`,
because systemd reads an `EnvironmentFile` once at process start.

## What is not backed up

Nothing here is. VMID 101 is deliberately absent from the nightly `daily-all`
vzdump job: the database is a seeded fixture and the secrets are the live game's,
which are escrowed elsewhere. Do not start keeping anything on staging that you
would miss.

## The other side of it

The container, its address, its resources and its route are declared in two lines
in `homelab-infra`:

```yaml
# services.yaml
streetfight-staging: {vm_id: 101, ip: 10.0.1.30, port: 80, repo: charlesbaynham/streetfight, state_gb: 100, mac: "BC:24:11:5F:1E:01", health_path: /api/get_version}

# internal.yaml
streetfight-staging: {service: streetfight-staging}
```

The registry key has to match `cattle.name` in this repo's `flake.nix`
(`streetfight-staging`), because that is what names the release asset and how the
deployer finds it. There is no `publish:` key, which is what keeps staging off the
public internet, and no DNS or certificate step at all - gardenfacer's wildcard
already covers the name.

`health_path` points at `/api/get_version` rather than `/` on purpose: Caddy goes
on answering 200 from the static frontend with the backend dead, so `/` is a health
check that cannot fail and the rollback it exists to trigger would never fire.
