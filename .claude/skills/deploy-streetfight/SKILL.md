---
name: deploy-streetfight
description: Deploy streetfight to live (the public archive of the 19 September 2026 game) or staging (the box for trying a branch on a phone), check what a box is currently running, or roll one back. Use whenever someone asks to deploy, ship, release, put something live, put a branch on staging, or check which revision a deployment is on. Merging to master deploys nothing, so this is always a deliberate, separate act.
---

# Deploying streetfight

**Merging to master deploys nothing.** Both deployments are gated behind a
manual workflow, because `live` is a public site carrying the real 19 September
2026 game and the printed QR codes still in the street point at it. Deploying
is always a separate, deliberate act.

Neither workflow has a route into the box it deploys. All either one does is
**force a branch ref** and dispatch the build; the hypervisor at home polls the
releases API for the template that build publishes and replaces the container
with it. Nothing on the internet holds credentials into either host.

|  | Live (the archive) | Staging (home lab) |
| --- | --- | --- |
| Where | CT 124 on `homeserver`, `10.0.1.48` | CT 101 on `homeserver`, `10.0.1.30` |
| Public origin | `https://streetfight.houseabsolute.co.uk` | `https://streetfight-staging.i.houseabsolute.co.uk` |
| Shape | LXC template (`.#streetfight-archive`) | LXC template (`.#streetfight-staging`) |
| Branch it polls | `live` | `staging` |
| Workflow | **Deploy to archive** (`deploy.yml`) | **Deploy to staging** (`deploy-staging.yml`) |
| Picked up by | cattle-deploy on the hypervisor, 15–25 minutes | the same |
| TLS | wallfacer's wildcard | gardenfacer's wildcard |
| Reachable from | the internet | the house LAN and the tailnet only |
| Database | **the real 19 September game**, restored by hand | empty on a fresh boot; the sample game is made by the **Fire demo game** button |

⚠️ Until 20 Sep 2026 `live` was a DigitalOcean droplet. It was destroyed once
the game was archived; `live` now moves CT 124 (the Street Fight archive) on
the home lab. See `docs/deployment_archive.md`.

## Deploying

```bash
scripts/deploy.sh staging                # put master on staging
scripts/deploy.sh staging my-branch      # try a branch on a real phone
scripts/deploy.sh staging pr/222         # ...or a pull request, by number
scripts/deploy.sh live master            # asks you to type "live" first
```

`ref` is anything git resolves — a branch, a tag, a SHA — and on **staging** a
pull request too, written `pr/222`, `#222` or bare `222` (its head is fetched as
`refs/pull/222/head`, so a fork's PR works; that one wants
`--skip-build-check`, since a fork head has no check run here). Master is the
default, never a restriction: trying an unmerged branch is what staging is for.
Live refuses a PR number, deliberately. The script wraps
`gh workflow run`, watches the run, and afterwards reports what the archive
says it is running. `--skip-build-check` deploys without waiting for the
template build to go green; `--no-wait` returns at the dispatch.

Equivalently, by hand:

```bash
gh workflow run deploy.yml -f ref=master            # live
gh workflow run deploy-staging.yml -f ref=master    # staging
```

**With no `gh`** — which is the case in a Claude Code container — use the
GitHub MCP tool `actions_run_trigger` on `deploy.yml` or `deploy-staging.yml`
with `ref` as the input, or tell the user to press the button in the Actions
tab.

### Before deploying live, always

1. **Ask Charles.** Live is the running game; never deploy it on your own
   initiative. Staging needs no such ceremony — that is what it is for.
2. Check the revision is what you think it is, and that CI is green on it.
3. Prefer putting it on **staging first**. Staging exists precisely so master
   is not tried out on the players, and a PR head on staging is the ordinary
   case.

## Verifying

```bash
curl -s https://streetfight.houseabsolute.co.uk/api/get_version
curl -s https://streetfight-staging.i.houseabsolute.co.uk/api/get_version   # LAN/tailnet only
```

`get_version` returning `unknown` means the flake was evaluated from a source
carrying no git revision — a `path:` reference or a bare directory. Deploying
from `.#` in a clean checkout, or `github:.../<rev>` as auto-deploy does,
stamps it properly.

For live, also check the site loads **with a padlock**. A certificate warning
means DNS is wrong or has been re-proxied, and phones will then refuse the
camera and geolocation APIs — which is the entire game.

## Rolling back

**Live**: deploy an earlier revision the same way. The workflow force-pushes
the ref, so going backwards works exactly like going forwards — or name a
generation directly on the hypervisor (three are kept per service).

```bash
scripts/deploy.sh live <older-sha>
# ...or, on homeserver:
/opt/homelab-infra/bin/cattle-deploy.sh streetfight-archive template-<date>-<sha7>
```

**Staging**: the same way — `scripts/deploy.sh staging <older-sha>`. This used
to be the one thing that quietly did nothing (the deployer takes the newest
release by publication time, and a revision already built today re-uploaded to
the release that already existed); `deploy-staging.yml` now deletes that release
so the build republishes it. Or roll back on `homeserver` without CI, naming the
generation:

```bash
/opt/homelab-infra/bin/cattle-deploy.sh streetfight-staging template-20260830-c828e38
```

Three generations are kept per service.

## When the workflow is not the right tool

There is no `nixos-rebuild --target-host` path to either box any more: both are
cattle, replaced wholesale by template filename, so the artifact has to be
built and published before anything can deploy. If Actions is down, nothing
deploys — which is the intended trade, since the alternative is a hand-built
container nothing can reproduce.

What you *can* do by hand, on `homeserver`, is re-point a container at a
template that already exists:

```bash
/opt/homelab-infra/bin/cattle-deploy.sh streetfight-archive template-<date>-<sha7>
touch /var/lib/homelab-infra/cattle/streetfight-archive.hold   # suspend deploys
```

The droplet's install-once procedure (`nix run .#install-cloud`) is kept in
`docs/deployment_droplet.md` in case a cloud host is ever wanted again. The
flake still carries `nixosConfigurations.streetfight-cloud` and CI still
build-tests it, but no droplet exists.

## State, and what a deploy does not touch

Both containers are **cattle**: every deploy destroys and recreates them. What
survives is `/data`, a Proxmox volume owned by a reserved VMID that the
container does not own — `usb-zfs:subvol-9124-disk-0` for the archive,
`subvol-9101-disk-0` for staging. **Never delete either.** They hold the
database, the shot photographs, the secrets and the logs.

⚠️ The archive's `SECRET_KEY` must stay the live game's: it signs the session
cookies players still hold, so rotating it locks every one of them out of
their own history. It is escrowed on CT 118 (the Secret Server).

Neither is in the nightly backup, deliberately. The archive's database is
re-seedable from the Nextcloud copy at
`Archives/streetfight/streetfight-game-archive-2026-09-19/`; see
`docs/deployment_archive.md`.

Staging is backed up by nothing either, and wiping it is free — that is
the fix for a model change the start-up column-adder cannot absorb
(`database.add_missing_columns` can add a column to a live database but cannot
drop or retype one).

## Secrets

Every deployment reads `/data/secrets/streetfight.env`
(`nix/streetfight.env.example` is the format) and refuses to start without
`SECRET_KEY`, `ADMIN_PASSWORD` and `WEBSITE_URL`.

Staging carries **the same secrets as live**, deliberately, with `WEBSITE_URL`
the one difference — so printed item QRs work on both, and the admin password
is the same on both. Never commit a real secrets file, and never paste one into
a PR, an issue or a chat log.

## The full runbooks

This skill is the operating summary. Where it and these disagree, they win:

- `docs/deployment_archive.md` — the public archive: what a stranger sees, the
  registry entry, the state volume, re-seeding the database, the traps.
- `docs/deployment_droplet.md` — **historical**: how the droplet was installed
  and run, kept in case a cloud host is ever wanted again.
- `docs/deployment_staging.md` — the two deployments side by side, the sample
  game, rollback, secrets rotation, the homelab-infra registry entries.
