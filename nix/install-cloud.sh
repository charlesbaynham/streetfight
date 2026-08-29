set -euo pipefail

FLAKE_ATTR=streetfight-cloud
NET_FILE=nix/cloud-net.json

target=""
secrets=""
skip_vm_test=0
assume_yes=0

usage() {
  cat >&2 <<'USAGE'
Install Street Fight onto a stock NixOS-anywhere-able droplet. DESTRUCTIVE:
it reformats the target's disk.

  nix run .#install-cloud -- --target root@<ip> --secrets <file> [options]

  --target root@<ip>   The stock droplet, reachable by SSH as root.
  --secrets <file>     The streetfight.env to install at /data/secrets/.
                       See nix/streetfight.env.example.
  --skip-vm-test       Skip booting the built image locally first. Don't:
                       it is the check that caught nothing twice and would
                       have caught both dark installs.
  --yes                Don't prompt before the destructive step.
USAGE
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --target) target=${2:?--target needs a value}; shift 2 ;;
    --secrets) secrets=${2:?--secrets needs a value}; shift 2 ;;
    --skip-vm-test) skip_vm_test=1; shift ;;
    --yes) assume_yes=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done

[ -n "$target" ] || usage
[ -n "$secrets" ] || usage
[ -e flake.nix ] || { echo "run this from the repo root" >&2; exit 1; }

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Checking $secrets"
[ -f "$secrets" ] || { echo "no such file: $secrets" >&2; exit 1; }
# The same contract nix/streetfight.nix's preflight enforces at boot. Checking
# it here means a bad secrets file costs a message, not a destroyed droplet.
for var in SECRET_KEY ADMIN_PASSWORD WEBSITE_URL; do
  value=$(sed -n "s/^$var=//p" "$secrets" | tail -1)
  case "$value" in
    "") echo "$var is missing from $secrets" >&2; exit 1 ;;
    none|not-so-secret|password)
      echo "$var is still the placeholder from streetfight.env.example" >&2
      exit 1 ;;
  esac
done
want_url=$(nix eval --raw ".#nixosConfigurations.$FLAKE_ATTR.config.services.streetfight.hostname")
have_url=$(sed -n 's/^WEBSITE_URL=//p' "$secrets" | tail -1)
case "$have_url" in
  *"$want_url"*) ;;
  *) echo "WEBSITE_URL ($have_url) does not name the host Caddy will get a" >&2
     echo "certificate for ($want_url); join links would point elsewhere." >&2
     exit 1 ;;
esac
echo "ok - SECRET_KEY, ADMIN_PASSWORD, WEBSITE_URL present and non-placeholder"

step "Capturing the droplet's network configuration"
# DigitalOcean gives no DHCP, so the installed system needs these literals or
# it boots with no addresses and is unreachable - which is exactly how the
# first two installs died. Read them off the stock droplet rather than
# trusting whatever the last install left in the repo.
if ! probe=$(ssh -o StrictHostKeyChecking=accept-new "$target" \
  "ip -j -4 route show default && echo --- && ip -j -4 addr show"); then
  echo "could not reach $target over SSH - is the key authorised on it?" >&2
  exit 1
fi

read -r iface addr prefix gw < <(
  printf '%s\n' "$probe" |
  python3 -c '
import ipaddress, json, sys
routes, addrs = sys.stdin.read().split("---")
default = json.loads(routes)[0]
iface, gw = default["dev"], default["gateway"]
for link in json.loads(addrs):
    if link["ifname"] != iface:
        continue
    for a in link["addr_info"]:
        if a["family"] == "inet" and not ipaddress.ip_address(a["local"]).is_private:
            print(iface, a["local"], a["prefixlen"], gw)
            sys.exit()
sys.exit(f"no public IPv4 found on {iface}")
'
)
if [ -z "${addr:-}" ]; then
  echo "could not read a public IPv4 address off $target" >&2
  exit 1
fi
echo "$iface: $addr/$prefix via $gw"

python3 - "$NET_FILE" "$iface" "$addr" "$prefix" "$gw" "${target#*@}" <<'PY'
import datetime, json, pathlib, sys
path, iface, addr, prefix, gw, host = sys.argv[1:]
old = json.loads(pathlib.Path(path).read_text()) if pathlib.Path(path).exists() else {}
new = {
    "interface": iface,
    "address": addr,
    "prefixLength": int(prefix),
    "gateway": gw,
    "nameservers": old.get("nameservers", ["1.1.1.1", "8.8.8.8"]),
    "capturedFrom": host,
    "capturedAt": datetime.date.today().isoformat(),
}
pathlib.Path(path).write_text(json.dumps(new, indent=2) + "\n")
changed = {k for k in ("interface", "address", "prefixLength", "gateway") if old.get(k) != new[k]}
print(f"rewrote {path}" + (f" (changed: {', '.join(sorted(changed))})" if changed else " (unchanged)"))
PY

# Nix only sees tracked files, so an uncommitted capture would be invisible to
# the very build it is meant to configure - and the install would bake the
# previous droplet's address in.
if [ -d .git ] && ! git diff --quiet -- "$NET_FILE" 2>/dev/null; then
  git add "$NET_FILE"
  echo "staged $NET_FILE (nix reads tracked files only) - commit it after the install"
fi

step "Checking the disk"
want_disk=$(nix eval --raw ".#nixosConfigurations.$FLAKE_ATTR.config.disko.devices.disk.main.device")
disks=$(ssh "$target" 'lsblk -dno PATH,SIZE,TYPE')
if ! printf '%s\n' "$disks" | grep -q "^$want_disk "; then
  echo "disko formats $want_disk, which the droplet does not have. It has:" >&2
  printf '%s\n' "$disks" >&2
  echo "Fix nix/disko-cloud.nix before installing." >&2
  exit 1
fi
echo "ok - $want_disk is present"

step "Assembling the extra-files tree"
extra=$(mktemp -d)
trap 'rm -rf "$extra"' EXIT
install -d -m 0755 "$extra/data"
install -d -m 0700 "$extra/data/secrets"
install -m 0600 "$secrets" "$extra/data/secrets/streetfight.env"
echo "$extra/data/secrets/streetfight.env (0600 in a 0700 directory)"

if [ "$skip_vm_test" -eq 0 ]; then
  step "Booting the built image locally (--vm-test)"
  # Runs under plain TCG without KVM - slow, not broken. It boots the actual
  # installed disk, which is the only check that catches a system that
  # installs cleanly and then never comes up.
  nixos-anywhere --flake ".#$FLAKE_ATTR" --vm-test
fi

step "Installing onto $target"
echo "This REFORMATS the disk on ${target#*@}. It cannot be undone."
if [ "$assume_yes" -eq 0 ]; then
  printf 'Type the target address to continue: '
  read -r confirm
  [ "$confirm" = "${target#*@}" ] || { echo "aborted" >&2; exit 1; }
fi
nixos-anywhere --flake ".#$FLAKE_ATTR" --extra-files "$extra" "$target"

step "Done"
cat <<DONE
Still to do by hand:
  - Point DNS at ${target#*@}, DNS-only (grey cloud), or ACME cannot complete.
  - Commit $NET_FILE.
  - Check https://$want_url loads with a padlock, and that
    /api/get_version reports a revision rather than "unknown".
Auto-deploy takes over from there; see docs/deployment_droplet.md.
DONE
