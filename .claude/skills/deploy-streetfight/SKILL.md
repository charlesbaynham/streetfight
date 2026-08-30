---
name: deploy-streetfight
description: Deploy streetfight to live (the DigitalOcean droplet) or staging (the home-lab LXC), check what a box is currently running, or roll one back. Use whenever someone asks to deploy, ship, release, put something live, put a branch on staging, or check which revision a deployment is on. Merging to master deploys nothing, so this is always a deliberate, separate act.
---

# Deploying streetfight

**Merging to master deploys nothing.** Both deployments are gated behind a
manual workflow, because the droplet carries a real game whose join links are
already in people's WhatsApp. Deploying is always a separate, deliberate act.

Neither workflow has a route into the box it deploys. All either one does is
**force a branch ref** to the revision you chose; the target polls that ref and
switches itself. Nothing on the internet holds credentials into either host.

|  | Live (droplet) | Staging (home lab) |
| --- | --- | --- |
| Where | DigitalOcean, `167.172.62.186` | CT 101 on `homeserver`, `10.0.1.30` |
| Public origin | `https://streetfight.houseabsolute.co.uk` | `https://streetfight-staging.i.houseabsolute.co.uk` |
| Shape | whole NixOS host (`nixosConfigurations.streetfight-cloud`) | LXC template (`.#proxmoxLxcTemplate`) |
| Branch it polls | `live` | `staging` |
| Workflow | **Deploy to droplet** (`deploy.yml`) | **Deploy to staging** (`deploy-staging.yml`) |
| Picked up by | `nix/auto-deploy.nix` timer, a couple of minutes | cattle-deploy on the hypervisor, 15–25 minutes |
| TLS | Caddy on the box, its own Let's Encrypt cert | gardenfacer's wildcard |
| Reachable from | the internet | the house LAN and the tailnet only |
| Database | **real and irreplaceable** | empty on a fresh boot; the sample game is made by the **Fire demo game** button |

## Deploying

```bash
scripts/deploy.sh staging                # put master on staging
scripts/deploy.sh staging my-branch      # try a PR head on a real phone
scripts/deploy.sh live master            # asks you to type "live" first
```

`ref` is anything git resolves — a branch, a tag, a SHA. The script wraps
`gh workflow run`, watches the run, and afterwards reports what the droplet
says it is running. `--skip-build-check` deploys even when the closure is not
in Cachix (the box then builds it itself, slowly); `--no-wait` returns at the
dispatch.

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
the ref, so going backwards works exactly like going forwards.

```bash
scripts/deploy.sh live <older-sha>
nixos-rebuild switch --rollback     # on the box; there is no auto-rollback
```

**Staging**: ⚠️ re-running the workflow on an older revision **may do nothing**
— the deployer picks the newest release by publication time, and re-pushing a
revision already built today re-uploads to the existing release without
changing its timestamp. Roll back on `homeserver` by naming the generation:

```bash
/opt/homelab-infra/bin/cattle-deploy.sh streetfight-staging template-20260830-c828e38
```

Three generations are kept per service.

## When the workflow is not the right tool

`nixos-rebuild switch --flake .#streetfight-cloud --target-host root@<ip>`
builds locally and pushes the closure. Use it for the one deploy that cannot go
through the workflow — the first after an install — for something not in the
repository at all (an uncommitted fix at 11pm on a game night), or if Actions
is down.

Installing a droplet from scratch is `nix run .#install-cloud -- --target
root@<ip> --secrets ./streetfight.env`. It is **destructive** — it reformats
the disk. Do not skip its `--vm-test`: it is the only check that catches a
system which installs cleanly and then never boots, and skipping it is exactly
how the first two installs went dark. Full detail in
`docs/deployment_droplet.md`.

## State, and what a deploy does not touch

`/data` on the droplet (database, shot photos, secrets, logs) is an ordinary
directory on the root disk — no block volume — so **the host is not
disposable**. `nixos-rebuild` never touches `/data`; only destroying the
droplet or re-running `nixos-anywhere` does.

**Back up before a game, not after**: `rsync -a root@<ip>:/data/ ./backup-data/`.
The shot photos and database are the labelled training data R1/R2 feed on.

Staging is backed up by nothing, deliberately, and wiping it is free — that is
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

- `docs/deployment_droplet.md` — install, the manual gate, how the droplet
  picks it up, state and backups, the cutover from the home LXC.
- `docs/deployment_staging.md` — the two deployments side by side, the sample
  game, rollback, secrets rotation, the homelab-infra registry entries.
