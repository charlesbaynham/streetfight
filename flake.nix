{
  description = "Simple npm+python environment";
  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.05";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        backendPackage = pkgs.python3Packages.buildPythonPackage rec {
          name = "backend";
          src = ./backend;
          propagatedBuildInputs = [ ];
        };

        texDeps = with pkgs; (texlive.combine {
          inherit (texlive) scheme-small;
        });

        pythonReqs = with pkgs.python3Packages; [
          pip

          # Runtime
          python-dotenv
          qrcode
          click
          sqlalchemy
          pillow
          psycopg2
          sqlalchemy-utils
          tzdata
          fastapi
          wsproto
          uvicorn

          # Development
          pytest
          pytest-asyncio
          pytest-mock
          # selenium
          # geckodriver-autoinstaller
          requests

          backendPackage
        ];

        reqs = with pkgs; [
          texDeps
          pkgs.nodejs
          (pkgs.python3.withPackages (ps: pythonReqs))
          pkgs.pre-commit
          pkgs.black
          pkgs.caddy
        ];

        frontendBuild = pkgs.buildNpmPackage rec {
          pname = "streetfight";
          version = "0.0.0";
          src = ./react-ui;
          npmDepsHash = "sha256-qnDS3SKAPPdsYviMwrqpZ+/Sb6fTKTS/MUJqjz1zasw=";
          makeCacheWritable = true;
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

        frontendApp =
          let
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

        backendApp =
          let
            python = pkgs.python3.withPackages (ps: pythonReqs ++ [ backendPackage ]);
          in
          flake-utils.lib.mkApp
            {
              drv = (pkgs.writeShellScriptBin "script" ''
                export PATH=${pkgs.lib.makeBinPath [ python ]}:$PATH

                exec python -m uvicorn backend.main:app --host 0.0.0.0
              '');
            };

        loadDocker = flake-utils.lib.mkApp
          {
            drv = (pkgs.writeShellScriptBin "script" ''
              nix build .#dockerFrontend
              export IMG_ID=$(docker load -i result | sed -nr 's/^Loaded image: (.*)$/\1/p' | xargs -I{} docker image ls "{}" --format="{{.ID}}")
              docker tag $IMG_ID streetfight-frontend:latest

              nix build .#dockerBackend
              export IMG_ID=$(docker load -i result | sed -nr 's/^Loaded image: (.*)$/\1/p' | xargs -I{} docker image ls "{}" --format="{{.ID}}")
              docker tag $IMG_ID streetfight-backend:latest
            '');
          };


      in
      {
        devShell =
          pkgs.mkShell {
            name = "devShell";
            buildInputs = reqs;
          };

        apps = {
          inherit loadDocker;
          default = loadDocker;
          frontend = frontendApp;
          backend = backendApp;
        };

        packages = {
          inherit backendPackage frontendBuild frontendBuildWithCaddy;
          default = frontendBuild;
          dockerFrontend = pkgs.dockerTools.buildLayeredImage {
            name = "streetfight-frontend";
            created = "now";
            config = {
              Cmd = [ frontendApp.program ];
              ExposedPorts = {
                "80/tcp" = { };
                "443/tcp" = { };
              };
              Env = [ "SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt" ];
            };
          };
          dockerBackend = pkgs.dockerTools.buildLayeredImage {
            name = "streetfight-backend";
            created = "now";
            config = {
              Cmd = [ backendApp.program ];
              WorkingDir = "/data";
              Volumes = { "/data" = { }; };
            };
          };
        };
      }
    );
}
