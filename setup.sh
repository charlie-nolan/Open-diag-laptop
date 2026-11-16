#!/usr/bin/env bash
# Downloads the app (open-diag-cyberdeck) into ~/open-diag-cyberdeck at the version the laptop guide was tested with
# (CORE_VERSION, a commit id), or updates an existing copy to it. Safe to run again. Nothing else is installed here:
# the guide's section 6 does the Python packages.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEST=${1:-$HOME/open-diag-cyberdeck}
REPO=https://github.com/charlie-nolan/open-diag-cyberdeck.git
VER=$(tr -d ' \n' < "$HERE/CORE_VERSION")
if [ -d "$DEST/.git" ]; then
    echo "Updating $DEST to $VER"
    git -C "$DEST" fetch --quiet origin
else
    echo "Downloading open-diag-cyberdeck into $DEST"
    git clone --quiet "$REPO" "$DEST"
fi
if [ -n "$(git -C "$DEST" status --porcelain --untracked-files=no)" ]; then
    echo "$DEST has local changes to its files; leaving it as it is." >&2
    exit 1
fi
git -C "$DEST" -c advice.detachedHead=false checkout --quiet "$VER"
echo "Done: $DEST is at $(git -C "$DEST" log -1 --format='%h %s')"
echo "Next: guide section 6 (docs/LAPTOP_GUIDE.md), from inside $DEST"
