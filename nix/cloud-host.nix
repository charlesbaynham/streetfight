# Machine-level configuration for the cloud droplet - everything about being
# a small public VM, and nothing about the game (that's ./streetfight.nix,
# wired up in the flake's `nixosConfigurations.streetfight-cloud`).
#
# State: unlike the Proxmox cattle deployment, /data here is an ordinary
# directory on the root filesystem - there is no block volume. That makes
# this host NOT disposable: the database, shot photos and secrets die with
# the disk, so back up /data (see docs/deployment_droplet.md) before
# anything that could lose the droplet. Chosen deliberately for a one-box,
# one-game deployment; attaching a DO block volume and mounting it at /data
# is the upgrade path if that ever changes.
{ config, lib, ... }:

let
  # Replace with the real deploy key before installing; the assertion below
  # refuses to build a system that would be installed with no way in.
  deployKeys = [
    "REPLACE-ME with the deploy ssh public key"
  ];
in
{
  assertions = [
    {
      assertion = !lib.any (k: lib.hasPrefix "REPLACE-ME" k) deployKeys;
      message = ''
        nix/cloud-host.nix still contains the placeholder deploy key.
        Put the real SSH public key in `deployKeys` before installing -
        with PasswordAuthentication off, a host installed with the
        placeholder is unreachable.
      '';
    }
  ];

  # GRUB for both firmware types; disko-cloud.nix carries the matching BIOS
  # boot partition and ESP, and disko points grub at the right device.
  boot.loader.grub = {
    enable = true;
    efiSupport = true;
    efiInstallAsRemovable = true;
  };

  networking.hostName = "streetfight-cloud";
  networking.useDHCP = lib.mkDefault true;

  # 22 for deploys; 80/443 are what Caddy answers on once
  # services.streetfight.hostname is set (80 also carries the ACME HTTP
  # challenge, so it stays open even though the game lives on 443).
  networking.firewall.allowedTCPPorts = [ 22 80 443 ];

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };
  users.users.root.openssh.authorizedKeys.keys = deployKeys;

  # nixos-rebuild evaluates on the target; a 1 GB droplet needs the headroom.
  swapDevices = [
    {
      device = "/swapfile";
      size = 2048;
    }
  ];

  system.stateVersion = "26.05";
}
