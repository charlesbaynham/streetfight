{
  description = "Simple npm+python environment";
  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs, flake-utils }:
    let
      # The host the Proxmox template is built for. `nixosConfigurations` is not
      # a per-system output, so it has to sit outside eachDefaultSystem.
      lxcSystem = "x86_64-linux";

      perSystem = flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        backendPackage = pkgs.python3Packages.buildPythonPackage {
          pname = "backend";
          version = "0.1";
          src = ./backend;
          # nixpkgs >= 25.05 requires the build system to be declared explicitly
          # rather than inferred; backend/setup.py is plain setuptools.
          pyproject = true;
          build-system = [ pkgs.python3Packages.setuptools ];
          propagatedBuildInputs = [ ];
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
          # starlette's TestClient dropped `requests` in favour of httpx
          httpx
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
    in
    nixpkgs.lib.recursiveUpdate perSystem {
      nixosModules.streetfight = import ./nix/streetfight.nix;

      # The deployable host. Building `.#proxmoxLxcTemplate` produces the rootfs
      # tarball that gets uploaded to Proxmox as a CT template; replacing the
      # container with a new template *is* the deploy mechanism, so this config
      # is never applied with `nixos-rebuild` on a running container.
      nixosConfigurations.streetfight-lxc = nixpkgs.lib.nixosSystem {
        system = lxcSystem;
        modules = [
          self.nixosModules.streetfight
          ./nix/lxc.nix
          {
            services.streetfight = {
              enable = true;
              backend = perSystem.packages.${lxcSystem}.backendEnv;
              frontend = perSystem.packages.${lxcSystem}.frontendBuild;
              # The rootfs of this container is thrown away on every deploy, so
              # a /data that is not the Proxmox mountpoint means silent data
              # loss at the next one.
              requireStateMountpoint = true;
            };
          }
        ];
      };

      packages.${lxcSystem}.proxmoxLxcTemplate =
        self.nixosConfigurations.streetfight-lxc.config.system.build.tarball;
    };
}
