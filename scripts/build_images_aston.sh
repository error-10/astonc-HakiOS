#!/bin/bash
# Build the iOS user-space images (root.apfs, system.apfs) and drop them into the Windows
# workspace's out/ directory. Needs sysimage/ to be fetched already (make fetch).
#
#   IMAGE_OPTS  passed to userland/build.sh (default REST=1: the whole stock job set)
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}
H="$HOME/hackios/hackios-os"
OUT="$ROOT/out"
OPTS="${IMAGE_OPTS:-REST=1}"

cd "$H"
mkdir -p logs "$OUT"
if [ ! -f sysimage/rootfs.dmg ] && [ ! -f sysimage/.done-rootfs ]; then
	echo "build_images_aston: sysimage/ is not fetched -- run 'make fetch' first" >&2
	exit 1
fi
echo "== images: $OPTS userland/build.sh  ($(date +%T))"
env $OPTS ./userland/build.sh 2>&1 | tee logs/images.log
for f in userland/root.apfs userland/system.apfs; do
	[ -f "$f" ] || { echo "build_images_aston: $f was not produced" >&2; exit 1; }
	cp -f "$f" "$OUT/"
	ls -l "$OUT/$(basename "$f")"
done
echo "== images done ($(date +%T))"
