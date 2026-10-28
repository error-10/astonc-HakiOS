#!/usr/bin/env bash
# Rebuild the whole OnePlus Ace 3 (astonc/SM8550) HakiOS chain from this repo's sources.
#
# Each step below is the same script that has already been run and verified on this machine
# (2026-10-28); this file only chains them in the right order and fails fast. Run it inside
# WSL (Ubuntu), from the repo root:
#
#   wsl.exe -d Ubuntu -u chenyu -- bash -lc 'bash scripts/rebuild_aston_all.sh'
#
# Inputs: ~/hackios/{hackios-os,Mu-Silicium,theos,venv}, an iOS 16.5 IPSW already fetched with
# `make fetch` (only needed for the userland images), phone only for `fastboot boot` afterwards.
#
# Outputs (out/):
#   SILICIUM_UEFI-aston.fd        patched Mu-Silicium UEFI firmware
#   boot-aston-uefi.img           UEFI only, first smoke test
#   boot-aston-xnu.img            UEFI + loader (USB resident), used for `ramdisk`/`run`
#   boot-aston-auto.img / -full   UEFI + loader + kernel + cmdline, boots by itself
#   loader-aston.efi, mach.development.bcm2837
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

step() { printf '\n=== %s ===\n' "$1"; }

step '1/5 UEFI (Mu-Silicium astonPkg + our XnuLoader/BootManager/MemoryMap/BootShim)'
bash scripts/build_uefi_aston.sh

step '2/5 xnuloader (platform_aston, PAYLOAD_BASE=0xE2000000, oem readlog) + boot-aston-xnu.img'
bash scripts/build_loader_aston.sh

step '3/5 XNU kernel (hakios.aston_touch.c included)'
bash scripts/install_touch_aston.sh
bash scripts/build_kernel_aston.sh

step '4/5 all-in-one boot images with the fresh kernel'
CMDLINE=${CMDLINE:-'-v hv_wdt_pet=1 bootcpu=7 cpus=8 ufs=2 aston_touch=1 aston_touch_ldo=1'} \
  bash scripts/build_payload_aston.sh

step '5/5 iOS 16.5 userland images (only if out/system.apfs is missing)'
if [ ! -f "$ROOT/out/system.apfs" ]; then
  bash scripts/build_images_aston.sh
else
  echo "out/system.apfs exists, skipped (delete it to rebuild)"
fi

echo
echo 'REBUILD_ASTON_ALL_OK'
ls -l "$ROOT/out" | sed -n '1,40p'
