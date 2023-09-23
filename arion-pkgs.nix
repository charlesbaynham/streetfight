let
  flake = (builtins.getFlake (toString ./.)).pkgs;
in
  flake.pkgs