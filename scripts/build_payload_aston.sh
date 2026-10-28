#!/usr/bin/env bash
# Build the XNUP payloads for the aston port and repack the boot images (header v4):
#   out/boot-aston-xnu.img   loader resident (usb), waits for `fastboot stage` runs   [build_loader_aston.sh]
#   out/boot-aston-auto.img  all-in-one: the loader boots the kernel by itself, no USB needed
#   out/boot-aston-full.img  same as auto but keeps the old name people already have
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}
HS=$H/hackios-os
PORT=$ROOT/port
OUT=$ROOT/out
K=$HS/xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837
PY=$H/venv/bin/python3
SOC_ARGS=${SOC_ARGS:-$ROOT/port/devices/oneplus-aston/soc.args}

# First bring-up cmdline. Keep it small: every flag is a driver the kernel skips or starts,
# and a wrong one is a panic we have to tell apart from a wrong address. The soc_* block
# describes this SoC's memory map to the drivers (see devices/<name>/soc.args upstream).
CMDLINE=${CMDLINE:-"-v hv_wdt_pet=1 bootcpu=7 cpus=8 ufs=2"}

if [ ! -f "$K" ]; then
  echo "kernel missing: $K" >&2
  exit 1
fi
if [ ! -f "$HS/xnuloader/loader.efi" ]; then
  echo "loader.efi missing: build it with scripts/build_loader_aston.sh" >&2
  exit 1
fi

SOC=""
if [ -f "$SOC_ARGS" ]; then
  # comments and blank lines dropped: the command line is one string
  SOC=$(sed 's/#.*//' "$SOC_ARGS" | tr '\n' ' ' | tr -s ' ' | sed 's/^ //; s/ $//')
  echo "soc.args: $SOC"
fi
FULL_CMDLINE="$CMDLINE $SOC"

echo "kernel: $(stat -c%s "$K") bytes"
"$PY" "$HS/xnuloader/mkpayload.py" -o "$HS/xnuloader/aston-payload.bin" \
  --cmdline "$FULL_CMDLINE" \
  loader.efi="$HS/xnuloader/loader.efi" \
  kernel="$K"

for name in boot-aston-auto.img boot-aston-full.img; do
  "$PY" "$PORT/mkboot-aston.py" --fd "$OUT/SILICIUM_UEFI-aston.fd" \
    --payload "$HS/xnuloader/aston-payload.bin" --out "$OUT/$name"
done
ls -l "$OUT"
echo READY_PAYLOAD_ASTON
