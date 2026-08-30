#!/usr/bin/env bash
#
# Deploy streetfight to live (the droplet) or staging (the home-lab LXC).
#
# Both deploys are the same act, and neither workflow has any route into the
# box it deploys: all they do is force a branch ref to the revision you chose.
# The target polls that ref and switches to it - `nix/auto-deploy.nix` on the
# droplet, cattle-deploy on the hypervisor at home. So this script is a wrapper
# around two `gh workflow run` calls, and its whole value is remembering which
# workflow takes which argument, resolving the ref to a revision so you can see
# what you actually asked for, and knowing that live is worth confirming and
# staging is not.
#
# Merging to master deploys nothing. This script is the deliberate act.
#
#   scripts/deploy.sh staging                  # put master on staging
#   scripts/deploy.sh staging my-branch        # try a PR head on a phone
#   scripts/deploy.sh live v1.2.3              # asks before it does it
#   scripts/deploy.sh live master --yes        # ...unless you say not to
#
# Full runbooks, which this does not replace:
#   docs/deployment_droplet.md   docs/deployment_staging.md

set -euo pipefail

ASSUME_YES=0
SKIP_BUILD_CHECK=false
NO_WAIT=0
TARGET=""
REF=""

# Positionals and flags in any order, so `deploy.sh staging --yes` means the
# default ref rather than a branch called "--yes".
for arg in "$@"; do
    case "$arg" in
    --yes | -y) ASSUME_YES=1 ;;
    --skip-build-check) SKIP_BUILD_CHECK=true ;;
    --no-wait) NO_WAIT=1 ;;
    -*)
        echo "unknown option: $arg" >&2
        exit 2
        ;;
    *)
        if [ -z "$TARGET" ]; then
            TARGET="$arg"
        elif [ -z "$REF" ]; then
            REF="$arg"
        else
            echo "unexpected argument: $arg" >&2
            exit 2
        fi
        ;;
    esac
done
REF="${REF:-master}"

case "$TARGET" in
live)
    WORKFLOW=deploy.yml
    BRANCH=live
    HOSTNAME=streetfight.houseabsolute.co.uk
    ;;
staging)
    WORKFLOW=deploy-staging.yml
    BRANCH=staging
    HOSTNAME=streetfight-staging.i.houseabsolute.co.uk
    ;;
*)
    echo "usage: scripts/deploy.sh <live|staging> [ref] [--yes] [--skip-build-check] [--no-wait]" >&2
    exit 2
    ;;
esac

if ! command -v gh >/dev/null 2>&1; then
    cat >&2 <<EOF
gh is not installed, so this script cannot trigger the workflow.

Run it from the Actions tab instead - "$( [ "$TARGET" = live ] && echo 'Deploy to droplet' || echo 'Deploy to staging' )"
-> Run workflow -> ref=$REF. An agent with the GitHub MCP tools can use
actions_run_trigger on $WORKFLOW with the same input.
EOF
    exit 1
fi

# Resolve for display only: the workflow re-resolves the ref itself, and the
# point here is to show which revision you are actually asking for.
REV="$(git rev-parse --short "$REF" 2>/dev/null || echo "not resolvable locally")"

echo "target      $TARGET  ($HOSTNAME)"
echo "ref         $REF  -> $REV"
echo "moves       refs/heads/$BRANCH"
[ "$SKIP_BUILD_CHECK" = true ] && echo "build check SKIPPED (the box will build it itself, slowly)"

if [ "$TARGET" = live ] && [ "$ASSUME_YES" -ne 1 ]; then
    echo
    echo "This is the live game. Players' join links point at it."
    printf 'Type the word live to deploy: '
    read -r reply
    [ "$reply" = live ] || {
        echo "aborted"
        exit 1
    }
fi

gh workflow run "$WORKFLOW" -f ref="$REF" -f skip_build_check="$SKIP_BUILD_CHECK"
echo "dispatched."

if [ "$NO_WAIT" -eq 1 ]; then
    exit 0
fi

# `gh workflow run` does not report the run id, and the run takes a moment to
# appear. Give it one.
sleep 5
RUN_ID="$(gh run list --workflow "$WORKFLOW" --limit 1 --json databaseId --jq '.[0].databaseId')"
[ -n "$RUN_ID" ] && gh run watch "$RUN_ID" --exit-status || true

if [ "$TARGET" = live ]; then
    # deploy.yml polls /api/get_version itself, so by here the droplet has it.
    echo
    echo "deployed revision now reported by the droplet:"
    curl -sf "https://$HOSTNAME/api/get_version" || echo "  (could not reach $HOSTNAME)"
else
    cat <<EOF

Staging answers on a private address, so nothing here can confirm it landed.
It takes about 15-25 minutes. Look at:
  - the "Build images" run on the staging branch (publishes the release asset)
  - journalctl -u cattle-deploy -f    on homeserver
  - curl -s https://$HOSTNAME/api/get_version   from the LAN or the tailnet
EOF
fi
