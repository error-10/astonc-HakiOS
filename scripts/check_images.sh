#!/usr/bin/env bash
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}
# Parse the boot image headers we produced and print what ABL will see.
OUT=$ROOT/out
CHK=$ROOT/port/check_boot.py
for f in boot-aston-uefi.img boot-aston-xnu.img boot-aston-full.img; do
  python3 "$CHK" "$OUT/$f"
  echo
done
