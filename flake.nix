{
  description = "Simple npm+python environment";
  nixConfig = {
    extra-substituters = [ "https://streetfight.cachix.org" ];
    extra-trusted-public-keys = [ "streetfight.cachix.org-1:KzTe/3Xxx4mgAPgJzfScKkIoinUwN/VZFPo34B5vtsc=" ];
  };
  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
  inputs.cattle.url = "git+https://github.com/charlesbaynham/nix-proxmox-cattle?ref=v1";
  # Declarative disk layout for the cloud droplet, applied by nixos-anywhere.
  inputs.disko = {
    url = "git+https://github.com/nix-community/disko";
    inputs.nixpkgs.follows = "nixpkgs";
  };

  # Python dependencies are resolved by uv into ./uv.lock and built from it by
  # uv2nix, so the LXC container, the dev shell, CI and a bare `uv sync` in a
  # throwaway container all get the same versions.
  inputs.pyproject-nix = {
    url = "github:pyproject-nix/pyproject.nix";
    inputs.nixpkgs.follows = "nixpkgs";
  };
  inputs.uv2nix = {
    url = "github:pyproject-nix/uv2nix";
    inputs.pyproject-nix.follows = "pyproject-nix";
    inputs.nixpkgs.follows = "nixpkgs";
  };
  # uv does not lock build systems, so they come from this overlay rather than
  # from uv.lock. This is the single most common uv2nix stumbling block.
  inputs.pyproject-build-systems = {
    url = "github:pyproject-nix/build-system-pkgs";
    inputs.pyproject-nix.follows = "pyproject-nix";
    inputs.uv2nix.follows = "uv2nix";
    inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, flake-utils, cattle, disko, pyproject-nix, uv2nix, pyproject-build-systems }:
    let
      inherit (nixpkgs) lib;

      # The host the Proxmox template is built for. `nixosConfigurations` is not
      # a per-system output, so it has to sit outside eachDefaultSystem.
      lxcSystem = "x86_64-linux";

      streetfightModule = import ./nix/streetfight.nix;

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      # Prefer prebuilt wheels: every dependency here publishes one, and sdists
      # are where uv2nix needs hand-written overrides.
      pyprojectOverlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      perSystem = flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        # The revision this flake was evaluated from. Clean trees get `shortRev`;
        # dirty ones get `dirtyShortRev`; anything else (e.g. a tarball) gets a
        # placeholder. Baked into the backend package so a running server can
        # say what code it is.
        version = if self ? rev then self.shortRev else if self ? dirtyRev then self.dirtyShortRev else "unknown";

        # There is no .git next to the installed package at runtime, so the
        # revision has to travel with it. Read by backend/main.py.
        versionOverlay = final: prev: {
          streetfight = prev.streetfight.overrideAttrs (old: {
            postInstall = (old.postInstall or "") + ''
              printf '%s' ${version} > "$out/${python.sitePackages}/backend/VERSION"
            '';
          });
        };

        pythonSet = (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope (lib.composeManyExtensions [
          pyproject-build-systems.overlays.wheel
          pyprojectOverlay
          versionOverlay
        ]);

        # Just enough to run the backend: what the deployed container needs, and
        # deliberately free of pytest and the dev group.
        backendEnv = pythonSet.mkVirtualEnv "streetfight-env" workspace.deps.default;

        # Everything the test suite needs as well.
        devEnv = pythonSet.mkVirtualEnv "streetfight-dev-env" workspace.deps.all;

        texDeps = with pkgs; (texlive.combine {
          inherit (texlive) scheme-small;
        });

        # Everything the test suite and the linters need, but no TeX. This is
        # what CI enters, so a test run no longer drags in a TeX distribution.
        ciReqs = [
          pkgs.nodejs
          devEnv
          pkgs.uv
          pkgs.pre-commit
          pkgs.black
          pkgs.caddy
        ];

        # The full shell additionally carries TeX, which only the map/PDF
        # generation scripts need.
        reqs = ciReqs ++ [ texDeps ];

        # uv must not fetch its own interpreter or silently re-sync the venv
        # Nix just built.
        uvEnv = {
          UV_NO_SYNC = "1";
          UV_PYTHON = python.interpreter;
          UV_PYTHON_DOWNLOADS = "never";
        };

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
          flake-utils.lib.mkApp
            {
              drv = (pkgs.writeShellScriptBin "script" ''
                export PATH=${pkgs.lib.makeBinPath [ backendEnv ]}:$PATH

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
          env = uvEnv;
        };

        devShells = {
          default = pkgs.mkShell {
            name = "devShell";
            buildInputs = reqs;
            env = uvEnv;
          };
          # Same as the default shell without TeX — used by CI.
          ci = pkgs.mkShell {
            name = "ciShell";
            buildInputs = ciReqs;
            env = uvEnv;
          };
        };

        apps = {
          inherit loadDocker;
          default = loadDocker;
          frontend = frontendApp;
          backend = backendApp;
        };

        packages = {
          inherit backendEnv devEnv frontendBuild frontendBuildWithCaddy;
          backendPackage = pythonSet.streetfight;
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

      # `.#nixosConfigurations.streetfight-cloud` is the public cloud VM (a
      # DigitalOcean droplet): same deployment-agnostic service module, but
      # installed as a whole NixOS host by nixos-anywhere, with Caddy
      # terminating TLS itself (`hostname`) since there is no border router in
      # front of it. Thereafter it redeploys itself from master on a timer
      # (./nix/auto-deploy.nix); `nixos-rebuild --target-host` remains the
      # manual override. See docs/deployment_droplet.md.
      cloudHost = {
        nixosConfigurations.streetfight-cloud = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            disko.nixosModules.disko
            ./nix/disko-cloud.nix
            ./nix/cloud-host.nix
            ./nix/auto-deploy.nix
            streetfightModule
            {
              services.streetfight = {
                enable = true;
                backend = perSystem.packages.x86_64-linux.backendEnv;
                frontend = perSystem.packages.x86_64-linux.frontendBuild;
                hostname = "streetfight.houseabsolute.co.uk";
              };
              services.streetfight-autodeploy.enable = true;
            }
          ];
        };
      };
    in
    lib.foldl lib.recursiveUpdate perSystem [
      lxcTemplate
      cloudHost
      { nixosModules.streetfight = streetfightModule; }
    ];
}
