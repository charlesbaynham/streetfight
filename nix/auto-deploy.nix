# Pull-based auto-deploy for the cloud droplet: the host reaches out on a
# timer, so nothing on the internet holds credentials into it. Imported only
# by `streetfight-cloud` - the LXC has its own redeploy path in
# nix-proxmox-cattle.
{ config, lib, pkgs, ... }:

let
  cfg = config.services.streetfight-autodeploy;

  stateDir = "/var/lib/streetfight-autodeploy";
  successFile = "${stateDir}/last-success";
  failureFile = "${stateDir}/last-failure";

  deploy = pkgs.writeShellApplication {
    name = "streetfight-autodeploy";
    # git is needed twice over: for the ls-remote gate, and because the flake
    # takes `cattle` as a git+https input, which nix cannot fetch without a
    # git binary even when evaluating a configuration that never uses it.
    runtimeInputs = [ pkgs.git pkgs.curl pkgs.nixos-rebuild ];
    text = ''
      target=$(git ls-remote ${lib.escapeShellArg cfg.repository} \
        "refs/heads/${cfg.branch}" | cut -f1)
      if [ -z "$target" ]; then
        echo "could not resolve ${cfg.branch} at ${cfg.repository}" >&2
        exit 1
      fi

      # Remembering the last failure as well as the last success is what stops
      # a broken commit redeploying itself every tick; the next commit retries.
      for memo in ${successFile} ${failureFile}; do
        [ "$(cat "$memo" 2>/dev/null)" = "$target" ] && exit 0
      done

      echo "deploying $target"
      if ! nixos-rebuild switch --flake "${cfg.flakePrefix}/$target#${cfg.configuration}"; then
        echo "$target" > ${failureFile}
        echo "rebuild failed; not retrying until a new commit lands" >&2
        exit 1
      fi

      # The backend directly, not through Caddy: with services.streetfight
      # .hostname set, Caddy serves exactly one vhost, for that name, so a
      # request to 127.0.0.1 matches nothing.
      reported=$(curl -fsS --max-time 30 --retry 5 --retry-delay 3 --retry-all-errors \
        "http://127.0.0.1:${toString config.services.streetfight.backendPort}/api/get_version" \
        | sed -n 's/.*"version" *: *"\([^"]*\)".*/\1/p')

      # The flake stamps backend/VERSION from self.shortRev, so what is running
      # should name the commit we asked for. An empty reading is a failure, not
      # a vacuous prefix match.
      if [ -z "$reported" ] || [ "''${target#"$reported"}" = "$target" ]; then
        echo "$target" > ${failureFile}
        echo "health check reported '$reported', wanted a prefix of $target" >&2
        exit 1
      fi

      echo "$target" > ${successFile}
      echo "deployed $target, backend reports $reported"
    '';
  };
in
{
  options.services.streetfight-autodeploy = {
    enable = lib.mkEnableOption "polling GitHub for new Street Fight commits and deploying them";

    repository = lib.mkOption {
      type = lib.types.str;
      default = "https://github.com/charlesbaynham/streetfight";
      description = "Repository polled for new commits.";
    };

    flakePrefix = lib.mkOption {
      type = lib.types.str;
      default = "github:charlesbaynham/streetfight";
      description = ''
        Flake reference the observed revision is appended to. Separate from
        {option}`repository` because nix wants a flake URL where git wants a
        clone URL.
      '';
    };

    branch = lib.mkOption {
      type = lib.types.str;
      default = "master";
      description = "Branch whose head is deployed.";
    };

    configuration = lib.mkOption {
      type = lib.types.str;
      default = "streetfight-cloud";
      description = "Attribute of `nixosConfigurations` to switch to.";
    };

    interval = lib.mkOption {
      type = lib.types.str;
      default = "2min";
      description = ''
        Timer interval. Short is affordable because the ls-remote gate costs
        one request when nothing has changed.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    # nixos-rebuild --flake needs both features, and neither is on by default.
    # The substituters are spelled out in full because assigning these options
    # replaces their defaults rather than adding to them - drop cache.nixos.org
    # and every deploy builds nixpkgs from source. The flake's own nixConfig
    # cannot serve here: it only applies once accepted at a prompt, which a
    # systemd service never sees.
    nix.settings = {
      experimental-features = [ "nix-command" "flakes" ];
      substituters = [
        "https://cache.nixos.org/"
        "https://streetfight.cachix.org"
      ];
      trusted-public-keys = [
        "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
        "streetfight.cachix.org-1:KzTe/3Xxx4mgAPgJzfScKkIoinUwN/VZFPo34B5vtsc="
      ];
    };

    systemd.services.streetfight-autodeploy = {
      description = "Deploy the head of ${cfg.branch} if it has changed";
      # The switch this unit performs would otherwise restart the unit
      # itself whenever this module changes, killing the deploy after it had
      # applied but before it could record the outcome - leaving the memo
      # empty and the next tick redeploying the same revision, forever.
      restartIfChanged = false;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.getExe deploy;
        StateDirectory = baseNameOf stateDir;
        # A deploy landing mid-game should degrade itself, not the backend.
        Nice = 19;
        IOSchedulingClass = "idle";
        MemoryHigh = "1G";
      };
    };

    systemd.timers.streetfight-autodeploy = {
      description = "Poll ${cfg.repository} for new commits";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "3min";
        OnUnitActiveSec = cfg.interval;
        RandomizedDelaySec = "30s";
        Persistent = true;
      };
    };
  };
}
