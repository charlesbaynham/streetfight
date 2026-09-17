#!/usr/bin/env bash
# Rebuild the reference bundle for the Westminster map redraw (roadmap #12,
# milestone M0.6). Run from the repo root; writes back into this directory.
#
# The framing is sized to the markers rather than pinned to one of them
# (changed 17 Sept 2026, at Charles's request). The crop used to be symmetric
# about House Absolute, which forced 650 m because Big Ben is 537 m north of
# it; nothing needs House Absolute at the centre, so the centre is now the
# geometric middle of the nineteen pubs, Big Ben, Parliament, the Abbey and
# House Absolute. That fits everything within 458 m, so 575 m gives every
# marker at least 117 m of drawing room and makes the crop 1150 x 1150 m,
# against 1300 before -- which is a quarter less ground for the same paper,
# and the whole reason to redraw. It also lands on Kingston's 1153 m, the size
# this hand-drawn style is tuned for.
#
# Nothing stands at that centre (the nearest pub is 105 m away), so
# --centre-label is empty: the builder draws a crosshair there instead of a
# marker and the prompt tells the model to preserve it without drawing it.
# House Absolute becomes an ordinary landmark.
#
# The venue's reference points ARE the crop corners, so they must be updated
# to match (see README.md) when the drawing lands -- and a drawing that
# re-crops is unusable however good it looks. Do not change --centre or
# --half-span without changing them together.
#
# The pubs are passed in rather than searched for: they are the nineteen
# Charles chose (backend/venues.py), with OpenStreetMap's coordinates, and a
# nearest-N search would return a different set. Names are how people say them
# - which is what should be written on a hand-drawn map - so the `Venue`
# snippet the script prints at the end is NOT to be pasted over venues.py: the
# landmark keys there are already right and other code names them.
set -euo pipefail

out="$(cd "$(dirname "$0")" && pwd)"

uv run python .claude/skills/draw-venue-map/scripts/build_venue_map.py \
    --name westminster \
    --centre 51.497681,-0.131209 \
    --half-span 575 \
    --centre-label "" \
    --landmark "House Absolute:51.4958738,-0.1309233" \
    --landmark "Big Ben:51.50073,-0.12462" \
    --landmark "Westminster Abbey:51.49940,-0.12764" \
    --landmark "Parliament:51.49900,-0.12460" \
    --pub "Royal Oak:51.494215,-0.132538:2 Regency Street" \
    --pub "The Loose Box:51.494706,-0.131336:51 Horseferry Road" \
    --pub "White Horse:51.495027,-0.130857:86 Horseferry Road" \
    --pub "Barley Mow:51.495077,-0.131687:104 Horseferry Road" \
    --pub "Marquis of Granby:51.495177,-0.127175:41 Romney Street" \
    --pub "Windsor Castle:51.495169,-0.137798:23 Francis Street" \
    --pub "The Greencoat Boy:51.496300,-0.135863:Greencoat Place" \
    --pub "The Speaker:51.496905,-0.132260:46 Great Peter Street" \
    --pub "Grafton Arms:51.497468,-0.134108:2 Strutton Ground" \
    --pub "Munich Cricket Club:51.498199,-0.132467:1 Abbey Orchard Street" \
    --pub "Buckingham Arms:51.499159,-0.136793:62 Petty France" \
    --pub "The Feathers:51.499240,-0.132990:18-20 Broadway" \
    --pub "Adam and Eve:51.499460,-0.135622:81 Petty France" \
    --pub "Sanctuary House:51.499520,-0.131822:33 Tothill Street" \
    --pub "Blue Boar:51.499544,-0.132180:41-47 Tothill Street" \
    --pub "The Old Star:51.499940,-0.133724:66 Broadway" \
    --pub "Westminster Arms:51.500555,-0.129813:9 Storey's Gate" \
    --pub "Two Chairmen:51.500631,-0.131621:39 Dartmouth Street" \
    --pub "St Stephen's Tavern:51.501146,-0.125595:10 Bridge Street" \
    --out "$out"
