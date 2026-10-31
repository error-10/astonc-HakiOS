#!/bin/bash
# Make QEMU runner copies that place the XNUP payload where *our* aston loader expects it
# (0xE2000000 instead of upstream 0xF0000000) and use Ubuntu's AAVMF firmware paths.
set -euo pipefail
cd "$HOME/hackios/hackios-os/qemu"
sed -e 's|addr=0xF0000000|addr=0xE2000000|' \
    -e 's|/usr/share/edk2/aarch64/QEMU_EFI.fd|/usr/share/AAVMF/AAVMF_CODE.fd|' \
    -e 's|/usr/share/edk2/aarch64/QEMU_VARS.fd|/usr/share/AAVMF/AAVMF_VARS.fd|' \
    run.sh > run-aston.sh
chmod +x run-aston.sh
sed -e 's|qemu/run.sh|qemu/run-aston.sh|' run-ios.sh > run-ios-aston.sh
chmod +x run-ios-aston.sh
grep -n 'addr=0x' run-aston.sh
grep -n 'AAVMF' run-aston.sh
grep -n 'run-aston' run-ios-aston.sh
