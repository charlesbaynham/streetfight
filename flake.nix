{
  description = "Simple npm+python environment";
  nixConfig = {
    extra-substituters = [ "https://streetfight.cachix.org" ];
    extra-trusted-public-keys = [ "streetfight.cachix.org-1:KzTe/3Xxx4mgAPgJzfScKkIoinUwN/VZFPo34B5vtsc=" ];
  };
  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
  inputs.cattle.url = "git+https://github.com/charlesbaynham/nix-proxmox-cattle?ref=v1";

  outputs = { self, nixpkgs, flake-utils, cattle }:
    let
      # The host the Proxmox template is built for. `nixosConfigurations` is not
      # a per-system output, so it has to sit outside eachDefaultSystem.
      lxcSystem = "x86_64-linux";

      streetfightModule = import ./nix/streetfight.nix;

      perSystem = flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # The revision this flake was evaluated from. Clean trees get `shortRev`;
        # dirty ones get `dirtyShortRev`; anything else (e.g. a tarball) gets a
        # placeholder. Baked into the backend package so a running server can
        # say what code it is.
        version = if self ? rev then self.shortRev else if self ? dirtyRev then self.dirtyShortRev else "unknown";

        backendPackage = pkgs.python3Packages.buildPythonPackage {
          pname = "backend";
          version = "0.1";
          src = ./backend;
          # nixpkgs >= 25.05 requires the build system to be declared explicitly
          # rather than inferred; backend/setup.py is plain setuptools.
          pyproject = true;
          build-system = [ pkgs.python3Packages.setuptools ];
          propagatedBuildInputs = [ ];
          # There is no .git next to the installed package at runtime, so the
          # revision has to travel with it. Read by backend/main.py.
          postInstall = ''
            printf '%s' ${version} > "$out/${pkgs.python3Packages.python.sitePackages}/backend/VERSION"
          '';
        };

        texDeps = with pkgs; (texlive.combine {
          inherit (texlive) scheme-small;
        });

        runtimePythonReqs = with pkgs.python3Packages; [
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
          # starlette's SessionMiddleware (backend/main.py) signs cookies with it
          itsdangerous
          # backend/vision_client.py calls OpenRouter with it; also what
          # starlette's TestClient uses
          httpx

          backendPackage
        ];

        devPythonReqs = with pkgs.python3Packages; [
          pip

          pytest
          pytest-asyncio
          pytest-mock
          # selenium
          # geckodriver-autoinstaller
          requests
        ];

        pythonReqs = runtimePythonReqs ++ devPythonReqs;

        # Just enough to run the backend: what the deployed container needs, and
        # deliberately free of pytest, pip and TeX.
        backendEnv = pkgs.python3.withPackages (ps: runtimePythonReqs);

        # Everything the test suite and the linters need, but no TeX. This is
        # what CI enters, so a test run no longer drags in a TeX distribution.
        ciReqs = [
          pkgs.nodejs
          (pkgs.python3.withPackages (ps: pythonReqs))
          pkgs.pre-commit
          pkgs.black
          pkgs.caddy
        ];

        # The full shell additionally carries TeX, which only the map/PDF
        # generation scripts need.
        reqs = ciReqs ++ [ texDeps ];

        frontendBuild = pkgs.buildNpmPackage rec {
          pname = "streetfight";
          version = "0.0.0";
          src = ./react-ui;
          npmDepsHash = "sha256-aOpQDSTk9PDDp0l2oa0d0FXBRyBiDuTsGbWIyiNkbCo=";
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
        devShell = pkgs.mkShell {
          name = "devShell";
          buildInputs = reqs;
        };

        devShells = {
          default = pkgs.mkShell {
            name = "devShell";
            buildInputs = reqs;
          };
          # Same as the default shell without TeX — used by CI.
          ci = pkgs.mkShell {
            name = "ciShell";
            buildInputs = ciReqs;
          };
        };

        apps = {
          inherit loadDocker;
          default = loadDocker;
          frontend = frontendApp;
          backend = backendApp;
        };

        packages = {
          inherit backendPackage backendEnv frontendBuild frontendBuildWithCaddy;
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
      # `.#proxmoxLxcTemplate` is the rootfs tarball Proxmox takes as a CT
      # template. Everything generic about being a cattle container — the LXC
      # fixups, the artifact naming, the "/data must be a mountpoint" guard —
      # comes from nix-proxmox-cattle; only the app wiring is here.
      lxcTemplate = cattle.lib.mkTemplate {
        inherit nixpkgs;
        name = "streetfight";
        system = lxcSystem;
        stateDir = "/data";
        modules = [
          streetfightModule
          {
            services.streetfight = {
              enable = true;
              backend = perSystem.packages.${lxcSystem}.backendEnv;
              frontend = perSystem.packages.${lxcSystem}.frontendBuild;
            };
          }
        ];
      };
    in
    nixpkgs.lib.recursiveUpdate perSystem
      (lxcTemplate // { nixosModules.streetfight = streetfightModule; });
}
