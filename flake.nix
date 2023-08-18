{
  description = "Simple npm-only environment
  ";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        reqs = [
          pkgs.nodejs
        ];

      in
      {
        devShell =
          pkgs.mkShell {
            name = "devShell";
            buildInputs = reqs;
          };

        apps = rec {
          start = flake-utils.lib.mkApp {
            drv = (pkgs.writeShellScriptBin "script" ''
              export PATH=${pkgs.lib.makeBinPath reqs}:$PATH

              exec npm run start
            '');
          };
          deploy = flake-utils.lib.mkApp {
            drv = (pkgs.writeShellScriptBin "script" ''
              export PATH=${pkgs.lib.makeBinPath reqs}:$PATH

              exec npm run deploy
            '');
          };
          default = start;
        };
      }
    );
}
