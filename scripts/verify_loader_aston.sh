#!/bin/bash
# Verify the aston loader patch: watchdog guard, platform pick, payload, and copy out/.
set -euo pipefail
HS="$HOME/hackios/hackios-os"
OUT="/mnt/c/Users/96943/Desktop/ios/out"
cd "$HS"
echo "== wdt_arm guard"
grep -n -A3 '^wdt_arm(void)' xnuloader/loader.c | head -12
echo "== platform pick"
grep -n 'BAB00000' -A3 -B1 xnuloader/loader.c
echo "== watchdog armed on phones"
grep -n 'PLAT == &platform_qemu_virt' -A3 xnuloader/loader.c | head -8
echo "== copy loader to out"
cp -f xnuloader/loader.efi "$OUT/loader-aston.efi"
ls -l "$OUT/loader-aston.efi"
echo "== payload entries"
python3 /mnt/c/Users/96943/Desktop/ios/port/inspect_bootimg.py "$OUT/boot-aston-xnu.img"
