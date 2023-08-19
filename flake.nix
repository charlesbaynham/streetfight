{
  description = "Simple npm+python environment";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        reqs = [
          pkgs.nodejs
          (pkgs.python3.withPackages (ps: with ps; [
            pip
            
            # Runtime
            python-dotenv
            sqlalchemy
            psycopg2
            sqlalchemy-utils
            fastapi

            # Development
            pytest
            pre-commit
            pip-tools
            black
            # selenium
            # geckodriver-autoinstaller
            requests
          ]))
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
