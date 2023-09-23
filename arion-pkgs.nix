let
  flake = (builtins.getFlake (toString ./.));
#   system = "aarch64-linux";
in
  flake.pkgs