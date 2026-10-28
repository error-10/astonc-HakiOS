#!/usr/bin/env bash
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}
# Build the HakiOS XNU kernel (arm64, BCM2837 development config) for the aston port.
# Run as the normal WSL user (not root): theos lives in that user's home and setup.sh
# resolves THEOS as ~/theos.
set -uo pipefail
HS=$H/hackios-os
L=$H/logs
mkdir -p "$L"
cd "$HS" || exit 1
export THEOS=${THEOS:-$HOME/theos}

echo "=== $(date +%H:%M:%S) xnu-deps/setup.sh ==="
./xnu-deps/setup.sh >"$L/xnu-deps.log" 2>&1
echo "deps rc=$?"
tail -5 "$L/xnu-deps.log"

echo "=== $(date +%H:%M:%S) xnu-build.sh ==="
./xnu-build.sh -j"$(nproc)" -k >"$L/xnu-build.log" 2>&1
echo "build rc=$?"
tail -15 "$L/xnu-build.log"

K=$HS/xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837
ls -l "$K" 2>/dev/null && echo KERNEL_OK || echo KERNEL_MISSING
