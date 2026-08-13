# Proxmox LXC host configuration for Street Fight.
#
# The rootfs built from this is a *template*, not a machine that gets upgraded:
# a deploy replaces the container wholesale rather than running `nixos-rebuild`
# inside it. Consequently nothing here is expected to be edited on the running
# container, and no /etc/nixos/configuration.nix is shipped — the configuration
# lives in this flake and only in this flake.
{ config, lib, modulesPath, ... }:

{
  imports = [ "${modulesPath}/virtualisation/proxmox-lxc.nix" ];

  proxmoxLXC = {
    privileged = false;
    # Leave networking to Proxmox: the container resource pins a static IP (or
    # a fixed MAC), so a replacement keeps the address the router in front of it
    # is already pointing at. Managing it here would fight that.
    manageNetwork = false;
    manageHostName = false;
  };

  # Units that cannot work inside an unprivileged LXC container. The upstream
  # module already masks /sys/kernel/debug; these two are the remaining ones
  # that otherwise fail noisily on every boot.
  systemd.mounts = [
    {
      enable = false;
      where = "/dev/mqueue";
    }
    {
      enable = false;
      where = "/sys/fs/fuse/connections";
    }
  ];

  # Name the artifact after the NixOS label so successive builds do not collide
  # in Proxmox's template storage. Rolling back means redeploying a previous
  # template, which needs the old file to still be there.
  # The label already carries the "lxc-proxmox" tags and the nixpkgs revision,
  # giving names like streetfight-lxc-proxmox-26.05.20260811.70cc455.tar.xz.
  image.baseName = "streetfight-${config.system.nixos.label}";

  # Keep the template small: local-lvm on the hypervisor is tight, and under the
  # cattle model there is transiently room needed for two copies.
  documentation.enable = false;
  documentation.nixos.enable = false;

  time.timeZone = "Europe/London";

  # This is a template that is replaced rather than upgraded in place, so the
  # usual "don't change this after install" caveat does not really apply — but
  # the sqlite database on the mountpoint does outlive any single container.
  system.stateVersion = "26.05";
}
