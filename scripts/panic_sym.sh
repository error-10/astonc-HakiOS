#!/bin/bash
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}
# Resolve kernel panic addresses against the unstripped Mach-O kernel.
# usage: panic_sym.sh <kernel-file> <text-base-hex> <addr-hex> [...]
set -e
K="$1"; BASE="$2"; shift 2
TMP=/tmp/kernel_symbols.txt
llvm-nm -n --defined-only "$K" > "$TMP"
echo "symbols: $(wc -l < "$TMP")"
for a in "$@"; do
  python3 - "$TMP" "$BASE" "$a" <<'PY'
import sys
path, base, addr = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
want = addr
best = None
with open(path) as f:
    for line in f:
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            v = int(parts[0], 16)
        except ValueError:
            continue
        if v <= want and (best is None or v > best[0]):
            best = (v, line.strip())
print(hex(addr), "offset", hex(want), "->", best[1] if best else "none",
      ("(+" + hex(want - best[0]) + ")") if best else "")
PY
done
