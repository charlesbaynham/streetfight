# Deploying to staging

The runbook for the **staging** deployment: a Proxmox LXC container on the home
lab, at <https://streetfight-staging.i.houseabsolute.co.uk>.

It exists because `live` does not have room for mistakes. That box is a public
site carrying the real 19 September 2026 game, with the printed QR codes still
in the street pointing at it, so `master` cannot be put on it casually. Staging is the same application from the same repository, on a
container that costs nothing to break, with no real players on it: its
database starts empty, and the sample game is made on demand from a seed.

> Live 30 Aug 2026. It is CT 101 on `homeserver` at `10.0.1.30`, reusing the
> container and the state volume that ran the game before the droplet cutover.

## The two deployments, side by side

| | Live (the public archive) | Staging (home lab) |
| --- | --- | --- |
| Where | CT 124 on `homeserver`, `10.0.1.48` | CT 101 on `homeserver`, `10.0.1.30` |
| Shape | LXC template (`.#streetfight-archive`) | LXC template (`.#streetfight-staging`) |
| Branch | `live` | `staging` |
| Workflow | **Deploy to archive** (`deploy.yml`) | **Deploy to staging** (`deploy-staging.yml`) |
| What moves | the `live` ref; CI publishes a template release, the hypervisor polls that | the same, one branch along |
| TLS | wallfacer, on its `*.houseabsolute.co.uk` wildcard | gardenfacer, on its `*.i.houseabsolute.co.uk` wildcard |
| Reachable from | the internet | the house LAN and the tailnet, and nowhere else |
| Database | the real 19 September game, irreplaceable | empty until somebody presses **Fire demo game** |

**Merging to master deploys neither.** Both are a deliberate act, and the two
branches are the whole gate.

## Deploying

Run the **Deploy to staging** workflow, or:

```bash
scripts/deploy.sh staging                # master
scripts/deploy.sh staging my-branch      # a branch, to try on a phone
scripts/deploy.sh staging pr/222         # a pull request, by its number
```

or by hand:

```bash
gh workflow run deploy-staging.yml -f ref=master
```

`ref` is anything git will resolve - a branch, a tag, a SHA - **and a pull
request**, written `pr/222`, `#222` or bare `222`. Putting an unmerged branch on
staging to try it on a phone is the ordinary case, not the exception: master is
only the input's default. The workflow checks that revision's LXC template built,
force-pushes it to `refs/heads/staging`, clears the way for a fresh release (see
below), and dispatches the build. That is all it does; it holds no credential for
anything at home.

A pull request is fetched as `refs/pull/222/head` rather than by branch name,
which is also what makes a **fork's** PR deployable - no branch of this
repository holds that commit. The one thing that costs: a fork's head never got
a push event here, so it has no `build_lxc_template` check run for the workflow
to look at, and that deploy wants `skip_build_check`.

### Why the workflow deletes a release before building

⚠️ **Load-bearing, and easy to mistake for tidying.** `build-template.yml` names
its release `template-<date>-<sha7>`, and the deployer at home takes the newest
release *by publication time*. So a revision already built today gets its asset
re-uploaded to the release that already exists, whose timestamp does not move -
and nothing at home ever notices.

That is barely visible when only master is ever deployed. It is the ordinary
case the moment staging is used for pull requests: try a branch, put master back
an hour later, and master's release is already this morning's. The deploy run
goes green, and staging carries on running the branch.

So `deploy-staging.yml` deletes that release, if it exists, between moving the
ref and dispatching the build, and the build republishes it seconds later. The
only asset destroyed is the one about to be rebuilt; the git tag is left in
place for `gh release create` to reuse. Nothing else in this repository
publishes releases, so there is nothing else it can hit.

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

Both targets are cattle containers now, so both work the same way, and the gate
is at the *producer* rather than the consumer: `build-template.yml` publishes a
release only when `github.ref` is the branch it was told, so if that run never
happens the artifact never exists at all and the hypervisor has nothing to fetch.

| | Live (the archive) | Staging (LXC) |
| --- | --- | --- |
| Branch the deploy moves | `live` | `staging` |
| Template attribute CI builds | `streetfight-archive` | `streetfight-staging` |
| What the hypervisor polls | the releases API, for a new asset | the same |
| Needs a workflow to run on the deploy branch | **yes** | **yes** |

⚠️ Until 20 Sep 2026 `live` was a DigitalOcean droplet, whose gate genuinely
*was* different — it polled the git ref and pulled its closure from Cachix,
which is branch-agnostic, so a swallowed push event cost it nothing. That is
no longer true of either target, and the "trigger the build explicitly" step
below is now load-bearing on both.

The shape is forced rather than chosen. A cattle container is replaced wholesale
by template filename - there is no in-place `switch` - so the artifact has to be
a *file* the hypervisor can fetch; and `resolve_release` takes the newest release
by publication time, so publishing from every branch and letting the consumer
choose would just deploy master.

The template filename *is* the deploy mechanism: Proxmox treats a container's
template as ForceNew, so a new filename replaces the container. The mechanics live
in `homelab-infra` (`bin/cattle-deploy.sh`, `services.yaml`) and are documented in
`ha-workspace`'s `docs/infra/cattle-containers.md`.

### Why the workflow does not wait for it

`deploy.yml` ends by polling `streetfight.houseabsolute.co.uk/api/get_version`
until it reports the new revision, which it can because the archive is on the
public internet. This one cannot: staging answers on `10.0.1.30`, a private
address a GitHub runner has no route to. The job therefore ends at the push and tells you
where to look:

- the *Build images* run on `staging`, which publishes the release asset;
- `journalctl -u cattle-deploy -f` on `homeserver`;
- and, from the LAN or the tailnet:

  ```bash
  curl -s https://streetfight-staging.i.houseabsolute.co.uk/api/get_version
  ```

### Rolling back

Deploy the earlier revision the same way - `scripts/deploy.sh staging <older-sha>`
- exactly as on the droplet. Going backwards used to be the one thing that
quietly did not work, for the reason above; the release drop is what fixed it,
so a re-deploy of a revision built earlier today now genuinely republishes.

You can also roll back on `homeserver` without CI at all, naming the generation
you want:

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

The registry key has to match the template's name in this repo's `flake.nix`
(`streetfight-staging`), because that is what names the release asset and how the
deployer finds it. ⚠️ The flake builds **two** templates now — this one and
`streetfight-archive`, the public archive at
[`deployment_archive.md`](deployment_archive.md) — so CI passes `attr:` to the
reusable build workflow explicitly rather than relying on its default. There is no `publish:` key, which is what keeps staging off the
public internet, and no DNS or certificate step at all - gardenfacer's wildcard
already covers the name.

`health_path` points at `/api/get_version` rather than `/` on purpose: Caddy goes
on answering 200 from the static frontend with the backend dead, so `/` is a health
check that cannot fail and the rollback it exists to trigger would never fire.
