# Deploying to staging

The runbook for the **staging** deployment: a Proxmox LXC container on the home
lab, at <https://streetfight-staging.i.houseabsolute.co.uk>.

It exists because the droplet does not have room for mistakes. That box carries a
real game whose join links are already in people's WhatsApp, so `master` cannot be
put on it casually. Staging is the same application from the same repository, on a
container that costs nothing to break, with no real players on it: its
database starts empty, and the sample game is made on demand from a seed.

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
| Database | real, irreplaceable | empty until somebody presses **Fire demo game** |

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

### Why that first arrow is a workflow_dispatch

⚠️ **The push does not set the build off by itself.** `deploy-staging.yml` moves
the ref with the default `GITHUB_TOKEN`, and GitHub does not fire
`push`-triggered workflows for `GITHUB_TOKEN` pushes - its anti-recursion
protection. So the workflow ends by dispatching `build_images.yml` against
`staging` explicitly. **Do not remove that step**: without it the ref moves, every
check in the deploy run goes green, and no release is ever published - staging
just quietly stays where it was. That is exactly how it failed on 30 Aug 2026.

This is the one place staging is *not* the droplet's mirror image. Both gates are
a hand-moved branch, but the two boxes watch different things:

| | Live (droplet) | Staging (LXC) |
| --- | --- | --- |
| What the box polls | the git ref, `git ls-remote refs/heads/live` | the releases API, for a new asset |
| So a deploy is due when | the ref moved | a new release asset appeared |
| Where the build comes from | Cachix - content-addressed, so branch-agnostic | a release asset, published only from `staging` |
| Needs a workflow to run on the deploy branch | no | **yes** |

The droplet's gate is at the *consumer*: `nix/auto-deploy.nix` decides which ref
to pull, and the closure is in Cachix whichever branch built it, so a swallowed
push event costs it nothing. Staging's gate is at the *producer*:
`build-template.yml` publishes a release only when `github.ref` is `staging`, so
if that run never happens the artifact never exists at all.

The asymmetry is forced rather than chosen. A cattle container is replaced
wholesale by template filename - there is no in-place `switch` - so the artifact
has to be a *file* the hypervisor can fetch; and `resolve_release` takes the
newest release by publication time, so publishing from every branch and letting
the consumer choose would just deploy master.

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

## The sample game — made by hand, not on boot

**Staging starts empty.** It no longer sets
`services.streetfight.sampleGame`, so `MAKE_DEBUG_ENTRIES` is not in the
backend's environment and a fresh database stays a fresh database: a boot
creates the schema and nothing else. Populating it is a deliberate press, not
something the box does to itself every time it restarts.

The press is the admin page's **Fire demo game** button
(`backend/demo_game.py`), which clears the database, rebuilds the deterministic
test world - six teams of five, each having picked an outfit through the real
picking code - arms the cast, starts the game, and then drips the ten demo
shots in one at a time about thirty seconds apart. That is also what makes it
worth watching: the sample game on its own is thirty players standing still,
and the spectator screen exists to react to a shot landing.

Everything is derived from one seed (`reset_db.SAMPLE_SEED`), so the game, its
teams and its join codes are the same every press and a printed join code keeps
working across a redeploy.

Staging is the right place for that button: it refuses outright if any player
who is in a team is not one of the thirty simulated ones, or if the database
holds any game that is not the demo's own - so it will not run against the live
droplet, and here both checks pass as long as nobody has created a game of
their own on the box. If one has been created and is no longer wanted, delete
it from the admin page (or wipe the database, below) before pressing.

An existing staging container carries whatever its state volume already holds,
so a box that was populated by the old start-up behaviour keeps that sample
game until the next press or wipe. A leftover sample game is the demo's own to
wipe, so it does not block the button.

Wiping staging back to nothing is free, and is also the fix for a model change
the start-up column-adder cannot absorb (`database.add_missing_columns` adds
new columns to an existing database at start-up, but cannot drop or retype
one). On `homeserver`:

```bash
rm -f "$(pvesm path usb-zfs:subvol-9101-disk-0)"/db/data.db
```

The next deploy - or a restart - rebuilds the schema, and leaves it empty for
the button.

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
