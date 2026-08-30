# Deploying to a DigitalOcean droplet (NixOS)

The runbook for running the game from a public cloud VM - written for the dry
run of 30 Aug 2026, but nothing in it is specific to that day. The droplet
replaces the home-lab LXC deployment (see the cutover section at the bottom);
that LXC has since come back as **staging**, which is a different runbook -
[`deployment_staging.md`](deployment_staging.md).

> **Status, 28 Aug 2026**: cutover in progress on the live droplet
> `167.172.62.186`. The first two installs completed cleanly and then never
> booted - two independent holes, both invisible from outside (a dark
> droplet, no SSH, no ping) and both now fixed in `nix/cloud-host.nix`:
> the default initrd carries **no virtio drivers**, so stage 1 hung looking
> for `/dev/vda`; and **DigitalOcean provides no DHCP** - the stock image's
> netplan is fully static from cloud-init metadata, so `useDHCP` boots with
> no addresses (the installer masks this by replaying the live config
> through kexec). The static values are baked in; re-capture them from a
> stock rebuild if the droplet is ever rebuilt. Root also gained a hashed
> *console* password (plaintext escrowed on homeserver) so the DO web
> console can reach a network-dead host; SSH stays key-only, and the deploy
> key that did the install is now in `deployKeys` alongside Charles's own.
> The `--vm-test` step was initially skipped (no KVM in the deploying
> container) in favour of a disk/firmware pre-check, which caught neither
> hole - the vm-test *does* (it boots the installed disk), and it runs fine
> under plain TCG emulation, just slowly. Don't skip it again.
> Third install (virtio + static networking fixes) booted first time on
> 28 Aug; the site is live.

The droplet is a **NixOS host**: `nixosConfigurations.streetfight-cloud` in
the flake, installed destructively onto the stock droplet with
`nixos-anywhere` and updated afterwards with `nixos-rebuild --target-host`.
It wires the same deployment-agnostic service module the LXC uses
(`nix/streetfight.nix`) to two new files: `nix/disko-cloud.nix` (disk layout)
and `nix/cloud-host.nix` (sshd, firewall, swap, boot loader). The one
behavioural difference from the LXC is TLS: there is no border router in
front of a droplet, so `services.streetfight.hostname` is set and Caddy
terminates TLS itself with automatic Let's Encrypt certificates. Phones
refuse the camera and geolocation APIs on an untrusted origin, and the whole
game is camera and geolocation, so a working certificate is a hard
requirement, not a nicety.

The public origin is **`https://streetfight.houseabsolute.co.uk`** - the same
address the home deployment served, so nothing already shared changes.

(A docker-compose path also exists - `compose.yml` +
`compose.ghcr.yml`/`compose.watchtower.yml`, with `SITE_ADDRESS` steering the
containerised Caddy the same way - and works on any Docker host. It is the
fallback, not the plan.)

## Installing a droplet

```bash
nix run .#install-cloud -- --target root@<droplet-ip> --secrets ./streetfight.env
```

That is the install. It is **destructive** - it reformats the target's disk -
and asks you to type the target address before it does. What it does, in
order, and why each step is in there rather than in this document:

1. **Checks the secrets file** against the same contract the service's
   preflight enforces at boot: `SECRET_KEY`, `ADMIN_PASSWORD` and
   `WEBSITE_URL` present and not the placeholders from
   `nix/streetfight.env.example`, and `WEBSITE_URL` naming the host Caddy
   will get a certificate for. A bad secrets file should cost a message, not
   a reinstall.
2. **Captures the droplet's networking** into `nix/cloud-net.json`, which
   `nix/cloud-host.nix` reads. DigitalOcean offers no DHCP, so those literals
   decide whether the installed system comes up at all - and they are
   different on every droplet. This step is why installing onto a new droplet
   no longer needs a hand-edit first. It stages the file, because nix reads
   only tracked files and an uncommitted capture would be invisible to the
   build it configures; commit it after the install.
3. **Confirms the disk** disko is about to format actually exists on the
   target, printing the droplet's real disks if not.
4. **Assembles the `--extra-files` tree** with `data/secrets/streetfight.env`
   at 0600 inside a 0700 directory, in a temporary directory it cleans up.
5. **Boots the built image locally** (`nixos-anywhere --vm-test`). Skippable
   with `--skip-vm-test`; don't. It runs under plain TCG without KVM - slow,
   not broken - and it is the only check that catches a system which installs
   cleanly and then never comes up. It was skipped for the first two installs,
   which is exactly how both went dark.
6. **Installs.**

### What it does not do

- **Create the droplet.** Do that in the DigitalOcean UI first: 2 GB
  (`nixos-anywhere` runs its installer from RAM), and give the key you will
  deploy with root access when provisioning it. That key must also be in
  `deployKeys` in `nix/cloud-host.nix` - an assertion refuses to evaluate a
  config carrying the placeholder, because password auth is off and a host
  installed without a key is unreachable.
- **DNS.** The record must reach the droplet directly - **DNS-only (grey
  cloud) in Cloudflare, not proxied** - or the ACME challenge cannot arrive.
  Ports 22/80/443 are opened by the NixOS firewall config; if a DO cloud
  firewall is attached, open them there too.
- **Fill in the secrets.** `nix/streetfight.env.example` documents the
  format. Keeping an escrowed `SECRET_KEY` rather than minting a new one
  keeps every join link already shared alive across a rebuild. Never commit
  the real file.

## Updating a droplet

```bash
nixos-rebuild switch --flake .#streetfight-cloud --target-host root@<ip>
```

`nixos-rebuild --target-host` builds on the deploying machine (which has the
`streetfight.cachix.org` substituter from the flake's `nixConfig`) and pushes
the closure, so the droplet itself never has to build or trust anything.

You will rarely need it - the deploy workflow, below, is the routine path. It
is the tool for the **one deploy that cannot go through the workflow**: the
first one after an install, which is what installs the deployer itself. It is
also the fallback if GitHub Actions is down.

### Deploying: the manual gate

**Merging to master deploys nothing.** Deploys are a deliberate act, because
there is a game running on this box.

To deploy, run the **Deploy to droplet** workflow: Actions -> Deploy to
droplet -> Run workflow, or

```bash
gh workflow run deploy.yml -f ref=master        # or a tag, a branch, a SHA
```

`.github/workflows/deploy.yml` is a `workflow_dispatch` job - GitHub's
equivalent of a GitLab manual pipeline step. It has no route into the droplet
and needs none: all it does is force `refs/heads/live` to the revision you
chose, then watch `/api/get_version` until the droplet reports it. Deploying
an *earlier* commit is how you roll back, and works the same way (which is why
the push is a force).

Before moving the ref it checks that `build_cloud_system` succeeded for that
revision, i.e. that the droplet can substitute the system closure from Cachix
rather than building it on one vCPU. `skip_build_check` overrides that when
you are willing to wait.

If you want a second pair of eyes on a deploy, add an `environment:` to the
job and give that environment required reviewers in the repository settings -
GitHub will then hold the run at an approval prompt. Not configured today: the
button *is* the approval.

### How the droplet picks it up

`nix/auto-deploy.nix` puts a timer and a oneshot on the droplet: each tick
asks GitHub for the head of the **`live`** branch with `git ls-remote`, and
does nothing at all unless it has moved. When it has, the droplet runs
`nixos-rebuild switch` against
`github:charlesbaynham/streetfight/<rev>#streetfight-cloud`, then checks
`/api/get_version` reports that revision. The host reaches out; nothing on
the internet holds credentials into it.

Until the first workflow run there is no `live` branch at all; the deployer
logs `nothing to deploy` each tick and exits cleanly. `git push origin
master:live` creates it by hand if you would rather not wait for Actions.

`/var/lib/streetfight-autodeploy/` records the last revision that succeeded
and the last that failed, and neither is retried — so a commit that breaks
the build or the health check is deployed once and then left alone until a
new commit lands. `journalctl -u streetfight-autodeploy` is the log.

```bash
systemctl start streetfight-autodeploy       # deploy now, don't wait for the tick
systemctl disable --now streetfight-autodeploy.timer   # kill switch
nixos-rebuild switch --rollback              # recovery; there is no auto-rollback
```

The manual `nixos-rebuild --target-host` line above still works and is the
right tool for deploying something that is not in the repository at all - an
uncommitted fix at 11pm on a game night.

Three things this needs on the droplet, all of them set by the module and
each of which silently breaks the deploy if it goes missing (all three were
found broken on the live box, 2026-08-29):

- **`nix.settings.experimental-features`** — `nixos-rebuild --flake` fails
  outright without `nix-command` and `flakes`, and neither is on by default.
- **`git`** — needed for the `ls-remote` gate, and again because the flake
  takes `cattle` as a `git+https` input, which nix cannot fetch without a git
  binary even when the configuration being evaluated never uses it.
- **`nix.settings.substituters`** — the flake's own `nixConfig` only applies
  once accepted at a prompt, which a systemd service never sees, so
  `streetfight.cachix.org` is baked into the system configuration. Without
  it the droplet builds the frontend and the Python environment itself on one
  vCPU.

## State and backups

`/data` (database, shot photos, secrets, logs) is an ordinary directory on
the droplet's root disk - no block volume - so **the host is not
disposable**: destroy the droplet and the game state goes with it. Two
consequences, both deliberate for a one-box deployment:

- **Back up before the launch, not after**: `rsync -a root@<ip>:/data/ ./backup-data/`
  (or a DO snapshot of the whole droplet). The shot photos and database are
  the labelled training data R1/R2 feed on - after the game, pull them off
  before doing anything rash.
- Rebuilding the host (`nixos-rebuild`) never touches `/data`; only
  destroying the droplet or re-running `nixos-anywhere` (which re-formats
  the disk) does.

## Verifying it

1. `https://streetfight.houseabsolute.co.uk` loads with a padlock (no
   certificate warning - a warning means DNS is wrong or still proxied, and
   phones will refuse the camera).
2. `https://streetfight.houseabsolute.co.uk/api/get_version` returns the
   deployed git revision, and it matches the commit you deployed. It reads
   `unknown` when the flake was evaluated from a source carrying no git
   revision — which is what a `path:` reference or a bare directory gives
   you. Deploying from `.#` in a clean checkout, or from `github:.../<rev>`
   as auto-deploy does, both stamp it properly.
3. On a real phone: log in as admin (`/admin`), create a game and a team,
   and open the identity page - the team join links it mints should start
   with `https://streetfight.houseabsolute.co.uk`. Follow one and check the
   browser asks for camera and location permissions.

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
   Transfer them straight into the droplet's
   `/data/secrets/streetfight.env` over SSH (or the `--extra-files` tree if
   the install hasn't happened yet) - never into a repo, a PR, a pastebin
   or a chat log.
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
consuming them the deployment is stood down.

**The LXC template was not retired afterwards - it became staging.** The
container on the home lab is now `streetfight-staging`, deployed from the
`staging` branch exactly as the droplet is from `live`, and reachable only
inside the house at `https://streetfight-staging.i.houseabsolute.co.uk`. So
`build_lxc_template` stays, now releasing from `staging` rather than master.
See [`deployment_staging.md`](deployment_staging.md).
