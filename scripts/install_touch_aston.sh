#!/usr/bin/env bash
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}
# Install the aston touch driver into the HakiOS kernel tree (both the port's
# authoritative copies under xnu/files and the already-patched xnu-src tree).
set -uo pipefail
HS=$H/hackios-os
X=$HS/xnu-src/xnu-8796.121.2
SRC=$ROOT/port/kernel
DRV=hakios.aston_touch.c
HW=hakios.aston_touch_hw.h

set -e
echo "=== copying driver sources ==="
cp "$SRC/$DRV" "$HS/xnu/files/bsd/dev/$DRV"
cp "$SRC/$HW"  "$HS/xnu/files/bsd/dev/$HW"
cp "$SRC/$DRV" "$X/bsd/dev/$DRV"
cp "$SRC/$HW"  "$X/bsd/dev/$HW"

echo "=== hook into hakios.input.c / .h ==="
grep -q 'hakios_aston_touch_init' "$HS/xnu/files/bsd/sys/hakios.input.h" || \
    sed -i 's|^void hakios_goodix_init(void);.*$|&\nvoid hakios_aston_touch_init(void);       /* boot-arg aston_touch=1: OnePlus Ace 3 S3910 over bit-bang SPI */|' \
        "$HS/xnu/files/bsd/sys/hakios.input.h"
cp "$HS/xnu/files/bsd/sys/hakios.input.h" "$X/bsd/sys/hakios.input.h"

for f in "$HS/xnu/files/bsd/dev/hakios.input.c" "$X/bsd/dev/hakios.input.c"; do
    grep -q 'hakios_aston_touch_init' "$f" || \
        sed -i 's|^\thakios_goodix_init();$|&\n\thakios_aston_touch_init();|' "$f"
done

echo "=== register in bsd/conf/files ==="
for f in "$X/bsd/conf/files"; do
    grep -q 'hakios.aston_touch.c' "$f" || \
        sed -i 's|^bsd/dev/hakios.input.c\t\tstandard$|&\nbsd/dev/hakios.aston_touch.c\tstandard|' "$f"
    grep -n 'hakios.aston_touch' "$f"
done

# keep the patch (used by a fresh xnu/apply.sh) in sync: insert the line and bump the hunk count
P="$HS/xnu/hakios.patch"
if ! grep -q 'hakios.aston_touch.c' "$P"; then
    python3 - "$P" <<'EOF'
import sys
p = sys.argv[1]
text = open(p).read()
anchor = "+bsd/dev/hakios.input.c\t\tstandard\n"
assert anchor in text, "anchor not found in hakios.patch"
text = text.replace(anchor, anchor + "+bsd/dev/hakios.aston_touch.c\tstandard\n", 1)
text = text.replace("@@ -109,6 +109,41 @@", "@@ -109,6 +109,42 @@", 1)
open(p, "w").write(text)
print("patched hakios.patch")
EOF
fi

echo "=== done ==="
grep -n 'aston_touch' "$HS/xnu/files/bsd/dev/hakios.input.c" "$HS/xnu/files/bsd/sys/hakios.input.h" "$HS/xnu/hakios.patch" | head
