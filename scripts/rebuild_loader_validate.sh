#!/usr/bin/env bash
# Rebuild loader.efi with PAYLOAD_BASE=0xE2000000 (the f0 experiment left the f0 build in place),
# then run the two corrected-RD_ADDR QEMU tests: our loader + prebuilt kernel, then our loader + our kernel.
set -uo pipefail
H=/home/chenyu/hackios
HS=$H/hackios-os
OUT=/mnt/c/Users/96943/Desktop/ios/out
cd "$HS"

grep -n "define PAYLOAD_BASE" xnuloader/loader.c
./xnuloader/build.sh 2>&1 | tail -3
ls -l xnuloader/loader.efi
cp xnuloader/loader.efi "$OUT/loader-aston.efi"
cp xnuloader/loader.efi xnuloader/loader-f0.efi.bak 2>/dev/null || true

run_one() {
  local script=$1 inst=$2 log=$3
  rm -rf qemu/esp qemu/ram.img
  QEMU_INSTANCE=$inst ./qemu/$script 60 > "logs/$log" 2>&1
  echo "=== $log"
  grep -n 'payload at\|largest free block\|resident image at pa\|Darwin Kernel Version\|launchd.ios\|SpringBoard\|panic(' "logs/$log" | head -14
}

run_one run-ios-hybrid3.sh 8 qemu-hybrid3.log
run_one run-ios-own3.sh 9 qemu-own3.log
echo DONE_REBUILD_VALIDATE
