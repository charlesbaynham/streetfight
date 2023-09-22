{ self, lib, buildNpmPackage, fetchFromGitHub }:

buildNpmPackage rec {
  pname = "streetfight-backend";
  version = "0.0.0";

  src = self;

  # npmDepsHash = "sha256-tuEfyePwlOy2/mOPdXbqJskO6IowvAP4DWg8xSZwbJw=";

  # The prepack script runs the build script, which we'd rather do in the build phase.
  npmPackFlags = [ "--ignore-scripts" ];

  NODE_OPTIONS = "--openssl-legacy-provider";

  # meta = with lib; {
  #   description = "A modern web UI for various torrent clients with a Node.js backend and React frontend";
  #   homepage = "http://example.com";
  #   # license = licenses.gpl3Only;
  #   # maintainers = with maintainers; [ winter ];
  # };
}
