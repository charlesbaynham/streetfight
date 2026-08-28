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
  # The keys that can deploy (and get root on) this host. The assertion below
  # refuses to build a system that would be installed with no way in.
  deployKeys = [
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGK5nWZ5ORwLuuiLzwzcOTJGyJfavI0ZAQ6GAsAlT0NJ JuiceSSH"
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCs2CID/pgMVIdyWwkP/cjic12rIBT62LSay2rD+9cx6W7ko9Y4qziireen0wWxYralR0rTuXGtGEAnZ1i9Eozoj/tqAgJ2kJk9UYkfrBLGPJyc+yT9L8A80wGauZxaUWrgQ0c1E8EqVMu8sVotfc13HdHW21TMoDzFh3x3y6K8/KDZUjtiv7XRlf6hX3RdL+zbN9KTzurRrt/VnSjRC0A+TrP9HEuzlcPOVKC39OCVZ9OWRbdoUPJPL3hE5vh6Wbf6bVrYhROrQJjxVCiCWQrhHfSa09wmhLg+dgnk1gkuX2OlIgLWe8j74lNr5z+I8XxT6JAko8I7J9chJHE1w5n9uvUII1+WgDmWhlov9lEia7io/vJ1IZR8CBJg7IfPmd5HZijQof8Md6sR3bdDxQ0ZuvhGn/juvKyP7fYUmQgX8uy1e5ZNKgD6rDgZOOPM2KD+lCAxfrt5gRujxJyig7MfZv08eV62ye8DkdXJ3DTyBEs91LgD83yVBrs/a/Yr5WC/3i9TnfDCKZ3TbcOgcViD8qnFmF5t9neF3e8EOc8uWfWso0MfK5EUUBAiRH8Kefoe7PaffShihWZDOz5D9YlcCLepQMMgKd5YOhnscmLQXyl3bOg7aCYiM0GT0Z53dinrh27qf5ioGrPXO4KWStyU5U8gRYBrxGuxK0kcmUiwgw== (none)"
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
