# Disk layout for the cloud droplet, applied destructively by nixos-anywhere
# at install time (and never again after that - disko only formats).
#
# GPT with both a BIOS boot partition (EF02) and an ESP, so the image boots
# whichever firmware the droplet presents; cloud-host.nix installs GRUB for
# both. DigitalOcean droplets present the disk as /dev/vda and boot BIOS on
# their standard images, but CONFIRM BEFORE THE REAL INSTALL: run
# `nixos-anywhere --generate-hardware-config` against the droplet and check
# the device node and firmware it reports rather than trusting this comment.
{
  disko.devices.disk.main = {
    device = "/dev/vda";
    type = "disk";
    content = {
      type = "gpt";
      partitions = {
        bios = {
          size = "1M";
          type = "EF02";
        };
        esp = {
          size = "512M";
          type = "EF00";
          content = {
            type = "filesystem";
            format = "vfat";
            mountpoint = "/boot";
          };
        };
        root = {
          size = "100%";
          content = {
            type = "filesystem";
            format = "ext4";
            mountpoint = "/";
          };
        };
      };
    };
  };
}
