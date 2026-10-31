#!/usr/bin/env bash
# Build Mu-Silicium UEFI for OnePlus Ace 3 (astonPkg) and pack a `fastboot boot` image.
# Run as: wsl -d Ubuntu -- bash -lc "sed -i 's/\r$//' <this>; bash <this>"
set -euo pipefail

H=/home/chenyu/hackios
MU=$H/Mu-Silicium
OUT=/mnt/c/Users/96943/Desktop/ios/out
mkdir -p "$H/logs" "$OUT"
cd "$H"

say() { echo "=== $(date +%H:%M:%S) $* ==="; }

say "git safe.directory (we run as root, the tree is owned by chenyu)"
git config --global --add safe.directory "$MU" || true
git config --global --add safe.directory "$H/hackios-os" || true

say "check submodules"
git -C "$MU" submodule status --recursive 2>/dev/null | awk '$1 ~ /^-/ {print "MISSING " $2}' | head -20 || true

say "venv + pip"
if [ ! -x "$H/venv/bin/python3" ]; then python3 -m venv "$H/venv"; fi
"$H/venv/bin/pip" -q install -r "$MU/pip-requirements.txt"
"$H/venv/bin/pip" -q install lzfse

say "mu_nasm without Mono"
D=$MU/Mu_Basecore/BaseTools/Bin/mu_nasm_extdep
mkdir -p "$D/Linux-x86-64"
printf 'version: 20016.1.1\n' > "$D/extdep_state.yaml"
ln -sf /usr/bin/nasm "$D/Linux-x86-64/nasm"
ln -sf /usr/bin/nasm "$D/Linux-x86-64/ndisasm"

say "stuart setup + update (external dependencies: onecrypto-bin, Mu-Basetools, ...)"
cd "$MU"
set +e
"$H/venv/bin/python3" Platforms/OnePlus/astonPkg/DeviceBuild.py --setup -t RELEASE 2>&1 | tee "$H/logs/setup.log" | tail -5
SETUP=${PIPESTATUS[0]}
"$H/venv/bin/python3" Platforms/OnePlus/astonPkg/DeviceBuild.py --update -t RELEASE 2>&1 | tee "$H/logs/update.log" | tail -15
UPD=${PIPESTATUS[0]}
set -e
echo "setup rc=$SETUP update rc=$UPD"

say "build UEFI astonPkg RELEASE"
cd "$MU"
"$H/venv/bin/python3" build_uefi.py -d aston -r RELEASE 2>&1 | tee "$H/logs/uefi-aston.log"
FD=$MU/Build/astonPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd
ls -l "$FD"
cp -f "$FD" "$OUT/SILICIUM_UEFI-aston.fd"

say "build BootShim"
cd "$MU/BootShim"
rm -f BootShim.elf BootShim.bin
make REQUIRES_KERNEL_HEADER=1 FD_BASE=0xA7100000 FD_SIZE=0x300000 \
     CFLAGS=--target=aarch64-linux-gnu

say "pack boot.img (header v4)"
python3 /mnt/c/Users/96943/Desktop/ios/port/mkboot-aston.py --fd "$FD" --out "$OUT/boot-aston-uefi.img"
ls -l "$OUT"
echo READY_UEFI
