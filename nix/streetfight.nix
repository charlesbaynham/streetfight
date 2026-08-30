# NixOS module for the Street Fight game server.
#
# (deploy mechanism bump)
#
# This describes the service only; it knows nothing about Proxmox or LXC, so it
# can equally be imported into a VM or a bare-metal host. The LXC-specific parts
# live in ./lxc.nix.
#
# Everything the service writes lives under `stateDir`, which under the "cattle"
# deployment model is a Proxmox mountpoint rather than part of the rootfs: the
# container is replaced wholesale on every deploy, and anything written inside
# the rootfs is expected to die with it.
{ config, lib, pkgs, ... }:

let
  cfg = config.services.streetfight;

  # The backend reads its secrets from the environment. Both SECRET_KEY and
  # ADMIN_PASSWORD fall back to weak built-in defaults with only a log warning
  # (backend/main.py, backend/admin_auth.py), so a container that is missing
  # them comes up *insecure* rather than failing. Behind a public ingress that
  # is the wrong failure mode, so refuse to start instead.
  preflight = pkgs.writeShellScript "streetfight-preflight" ''
    set -u
    fail() { echo "streetfight: $1" >&2; exit 1; }

    for var in SECRET_KEY ADMIN_PASSWORD WEBSITE_URL; do
      if [ -z "''${!var:-}" ]; then
        fail "$var is not set. It must be defined in ${cfg.environmentFile}."
      fi
    done

    # Reject the placeholder values shipped in the repo's .env files, which are
    # public and therefore worthless as secrets.
    case "$SECRET_KEY" in
      none|not-so-secret) fail "SECRET_KEY is still a well-known placeholder." ;;
    esac
    case "$ADMIN_PASSWORD" in
      password) fail "ADMIN_PASSWORD is still a well-known placeholder." ;;
    esac
  '';

  # One site definition whichever way TLS is handled; only the virtualHost
  # address differs (see `services.caddy` below).
  siteConfig = ''
    handle /api/* {
      reverse_proxy 127.0.0.1:${toString cfg.backendPort}
    }

    handle /docs* {
      reverse_proxy 127.0.0.1:${toString cfg.backendPort}
    }

    handle /openapi.json {
      reverse_proxy 127.0.0.1:${toString cfg.backendPort}
    }

    handle {
      root * ${cfg.frontend}

      encode gzip zstd

      # Make the HTML file extension optional
      try_files {path} /index.html
      file_server
    }
  '';
in
{
  options.services.streetfight = {
    enable = lib.mkEnableOption "the Street Fight game server";

    backend = lib.mkOption {
      type = lib.types.package;
      description = ''
        Python environment containing the `backend` package and its runtime
        dependencies. Must provide `bin/python`.
      '';
    };

    frontend = lib.mkOption {
      type = lib.types.package;
      description = "Built React frontend, served as static files by Caddy.";
    };

    stateDir = lib.mkOption {
      type = lib.types.path;
      default = "/data";
      description = ''
        Directory holding all state that must survive redeployment. Under the
        cattle deployment it is a Proxmox mountpoint, declared outside this
        flake (the cattle module refuses to finish booting if it is not one);
        under the cloud host it is an ordinary directory on the root disk,
        which is why that host is not disposable (see nix/cloud-host.nix).
      '';
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 80;
      description = ''
        Port Caddy listens on when TLS is terminated upstream by the border
        router: plain HTTP, no ACME. Unused when
        {option}`services.streetfight.hostname` is set - Caddy then owns 80
        and 443 itself.
      '';
    };

    hostname = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "streetfight.example.com";
      description = ''
        Public hostname to serve with automatic TLS. When set, Caddy serves
        `https://<hostname>` with Let's Encrypt certificates (and the usual
        HTTP-to-HTTPS redirect on 80), for a host with no border router in
        front of it - a public cloud VM. DNS for the name must resolve
        directly to this host (not through a proxy) so the ACME HTTP
        challenge can arrive. When null, behaviour is unchanged: plain HTTP
        on {option}`services.streetfight.port`, TLS somebody else's job.
      '';
    };

    backendPort = lib.mkOption {
      type = lib.types.port;
      default = 8000;
      description = "Loopback port the FastAPI backend listens on.";
    };

    websiteUrl = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "https://streetfight.example.com";
      description = ''
        Public URL of the site, used for CORS and baked into the QR codes that
        `qr_gen` produces. When null it must instead be supplied as WEBSITE_URL
        in {option}`services.streetfight.environmentFile`, which is usually
        what you want: it is deployment configuration rather than a property of
        the build.
      '';
    };

    logLevel = lib.mkOption {
      type = lib.types.str;
      default = "INFO";
      description = "Level for the Python logging module. Note capitals.";
    };

    sampleGame = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Build the deterministic sample game at start-up if the database does
        not already hold it (MAKE_DEBUG_ENTRIES). Idempotent, so it is safe to
        leave on: `reset_db.make_debug_entries_if_wanted` returns early once
        the game is there. For a staging deployment; never for a host carrying
        a real game.
      '';
    };

    environmentFile = lib.mkOption {
      type = lib.types.path;
      default = "${cfg.stateDir}/secrets/streetfight.env";
      defaultText = lib.literalExpression ''"''${config.services.streetfight.stateDir}/secrets/streetfight.env"'';
      description = ''
        systemd EnvironmentFile supplying at least SECRET_KEY and
        ADMIN_PASSWORD. It deliberately lives on the persistent mountpoint
        rather than in the rootfs, so it survives container replacement.

        This file is *required*: the unit fails to start if it is absent, which
        is intended. Note that rotating SECRET_KEY invalidates every QR code
        already printed, since item payloads are signed with it.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.streetfight = {
      isSystemUser = true;
      group = "streetfight";
      home = cfg.stateDir;
      description = "Street Fight game server";
    };
    users.groups.streetfight = { };

    # The mountpoint itself is created by Proxmox; these are the subdirectories
    # the app expects to find inside it. The sqlite database bootstraps its own
    # schema on first boot (backend/database.py), so an empty mountpoint is a
    # valid starting state and no init step is needed.
    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir}                  0750 streetfight streetfight -"
      "d ${cfg.stateDir}/db               0750 streetfight streetfight -"
      "d ${cfg.stateDir}/logs             0750 streetfight streetfight -"
      "d ${cfg.stateDir}/logs/images      0750 streetfight streetfight -"
      "d ${cfg.stateDir}/processed_shots  0750 streetfight streetfight -"
      "d ${cfg.stateDir}/secrets          0700 streetfight streetfight -"
    ];

    systemd.services.streetfight-backend = {
      description = "Street Fight backend (FastAPI)";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];

      environment = {
        # Four slashes total: sqlite:/// plus an absolute path.
        DATABASE_URL = "sqlite:///${cfg.stateDir}/db/data.db";
        POSTPROCESS_OUTPUT_DIR = "${cfg.stateDir}/processed_shots";
        LOG_LEVEL = cfg.logLevel;
        PYTHONUNBUFFERED = "1";
      } // lib.optionalAttrs (cfg.websiteUrl != null) {
        WEBSITE_URL = cfg.websiteUrl;
      } // lib.optionalAttrs cfg.sampleGame {
        MAKE_DEBUG_ENTRIES = "1";
      };

      serviceConfig = {
        User = "streetfight";
        Group = "streetfight";
        # backend/main.py writes ./logs/backend.log relative to the working
        # directory, and image_processing.py dumps debug images to ./logs/images.
        WorkingDirectory = cfg.stateDir;
        # Leading "-" so a missing file is not a systemd-level load failure:
        # the unit still refuses to start, but the preflight check below is what
        # reports it, and it can say which variables are wanted and where.
        EnvironmentFile = "-${cfg.environmentFile}";
        ExecStartPre = preflight;
        ExecStart = "${cfg.backend}/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port ${toString cfg.backendPort}";
        Restart = "always";
        RestartSec = 5;

        # The security boundary for this estate is the border router, not the
        # service container, so this is modest hardening rather than a sandbox.
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ cfg.stateDir ];
      };
    };

    services.caddy = {
      enable = true;
      # Mirrors the repo's Caddyfile. The virtualHost address decides the TLS
      # story, exactly as SITE_ADDRESS does there: a bare `:port` is plain
      # HTTP (border router terminates TLS, and Caddy's data/config
      # directories carry nothing worth persisting), while a hostname makes
      # Caddy do ACME itself - in which case /var/lib/caddy holds the
      # certificates and is worth keeping.
      virtualHosts.${
        if cfg.hostname != null then cfg.hostname else ":${toString cfg.port}"
      }.extraConfig =
        siteConfig;
    };

    networking.firewall.allowedTCPPorts =
      if cfg.hostname != null then [ 80 443 ] else [ cfg.port ];
  };
}
