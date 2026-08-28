# Deploying to a DigitalOcean droplet (NixOS)

The runbook for running the game from a public cloud VM - written for the dry
run of 30 Aug 2026, but nothing in it is specific to that day. The droplet
replaces the home-lab LXC deployment (see the cutover section at the bottom).

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

## Before the install

1. **Droplet size**: `nixos-anywhere` runs its installer from RAM - 2 GB is
   comfortable. If the droplet is smaller, resize it before starting rather
   than fighting it.
2. **Deploy key**: put the real SSH public key in `deployKeys` in
   `nix/cloud-host.nix`. The config *refuses to evaluate* while the
   placeholder is in place (password auth is off, so a host installed
   without a key is unreachable). The stock droplet must also accept that
   key for root - add it when provisioning.
3. **Confirm the disk**: run
   `nixos-anywhere --generate-hardware-config` against the droplet and check
   the device node and firmware it reports. `nix/disko-cloud.nix` assumes
   `/dev/vda` and carries a hybrid BIOS+UEFI GPT layout so either firmware
   boots, but the device node must match what the droplet actually has.
4. **Prove it boots**: `nixos-anywhere --vm-test --flake .#streetfight-cloud`
   before pointing anything at the real droplet. The install is destructive
   and irreversible.
5. **DNS**: the `streetfight.houseabsolute.co.uk` record must reach the
   droplet directly - **DNS-only (grey cloud) in Cloudflare, not proxied** -
   or the ACME HTTP challenge can't arrive. (Ports 22/80/443 are opened by
   the NixOS firewall config; if a DO cloud firewall is attached, open them
   there too.)

## Secrets

`/data/secrets/streetfight.env` must exist before first boot - the service's
preflight check refuses to start without it, deliberately. Deliver it with
`--extra-files`: build a local tree containing
`data/secrets/streetfight.env` (directory mode 0700) and pass it at install
time. `nix/streetfight.env.example` documents the format; the real values
come from the home deployment's escrow (cutover, below). At minimum:
`SECRET_KEY`, `ADMIN_PASSWORD`, `WEBSITE_URL`, plus `OPENROUTER_API_KEY` and
the model settings for CharlesBot. Never commit the real file.

Keeping the escrowed `SECRET_KEY` (rather than minting a new one) keeps
every join link already shared alive across the cutover.

## Install and deploy loop

```bash
# One-time, destructive install onto the stock droplet:
nixos-anywhere --flake .#streetfight-cloud \
  --extra-files ./extra-files \
  root@<droplet-ip>

# Every update after that:
nixos-rebuild switch --flake .#streetfight-cloud --target-host root@<ip>
```

`nixos-rebuild --target-host` builds on the deploying machine (which has the
`streetfight.cachix.org` substituter from the flake's `nixConfig`) and pushes
the closure, so the droplet itself never has to build or trust anything.

Note what this means for updates: unlike the LXC (and unlike the
watchtower-based docker path), **a master push does not update the droplet
by itself** - somebody runs the `nixos-rebuild` line. On a game day that is
arguably a feature; if hands-off updates are wanted later, that is a
decision to take deliberately, not a thing this setup half-does.

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
   deployed git revision, and it matches the commit you deployed.
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
consuming them the deployment is stood down. Removing the
`build_lxc_template` job is later cleanup, not part of the cutover.
