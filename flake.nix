{
  description = "Simple npm+python environment";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        reqs = with pkgs; [
          pkgs.nodejs
          (pkgs.python3.withPackages (ps: with ps; [
            pip

            # Runtime
            python-dotenv
            sqlalchemy
            pillow
            psycopg2
            sqlalchemy-utils
            fastapi
            wsproto
            uvicorn

            # Development
            pytest
            pytest-asyncio
            # selenium
            # geckodriver-autoinstaller
            requests
          ]))
          pkgs.pre-commit
          pkgs.black
          pkgs.caddy
        ];

        frontendBuild = pkgs.buildNpmPackage rec {
          pname = "streetfight";
          version = "0.0.0";
          src = ./react-ui;
          npmDepsHash = "sha256-giQlRyvKQHlahSoBpJyLftuWZ+8k/REjYIPWR6riycw=";
          installPhase = ''
            mkdir $out
            cp -a build/. $out
          '';
        };

        frontendBuildWithCaddy = pkgs.stdenv.mkDerivation {
          name = "streetfight-with-caddy";
          src = frontendBuild;
          installPhase = ''
            mkdir $out
            mkdir $out/result
            cp "${./Caddyfile}" $out/Caddyfile
            cp -a $src/. $out/result
          '';
        };

        frontendApp = let
              inputs = [
                pkgs.caddy
              ];
            in
            (
              flake-utils.lib.mkApp
                {
                  drv = (pkgs.writeShellScriptBin "script" ''
                    export PATH=${pkgs.lib.makeBinPath inputs}:$PATH
                    cd ${frontendBuildWithCaddy}

                    exec caddy run
                  '');
                }
            );

        backendApp = flake-utils.lib.mkApp
            {
              drv = (pkgs.writeShellScriptBin "script" ''
                export PATH=${pkgs.lib.makeBinPath reqs}:$PATH

                python -m backend.reset_db && true
                exec uvicorn backend.main:app --host 0.0.0.0
              '');
            };

      in
      {
        inherit pkgs;

        devShell =
          pkgs.mkShell {
            name = "devShell";
            buildInputs = reqs;
          };

        apps = {
          frontend =frontendApp;
          backend = backendApp;
        };

        packages = {
          inherit frontendBuild frontendBuildWithCaddy;
          default = frontendBuild;
          dockerFrontend = pkgs.dockerTools.buildLayeredImage {
            name = "streetfight-frontend";
            config = {
              Cmd = [ frontendApp.program ];
              ExposedPorts = {
                  "80/tcp" = {};
                  "443/tcp" = {};
              };
            };
          };
          dockerBackend = pkgs.dockerTools.buildLayeredImage {
            name = "streetfight-backend";
            config = {
              Cmd = [ backendApp.program ];
              ExposedPorts = {
                  "8080/tcp" = {};
              };
            };
          };
        };
      }
    );
}
