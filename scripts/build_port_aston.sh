#!/usr/bin/env bash
# Build the HakiOS OnePlus Ace 3 (aston) UEFI chain inside WSL:
#   patched Mu-Silicium astonPkg  ->  out/SILICIUM_UEFI-aston.fd
#   BootShim (payload copy enabled) -> Mu-Silicium/BootShim/BootShim.bin
#   out/boot-aston-uefi.img      (no payload: UEFI + diagnostics only)
#   out/boot-aston-xnu.img       (with XNUP payload: UEFI -> XnuLoader -> xnuloader -> XNU)
#
# Run as: wsl -d Ubuntu -u root -- bash -lc "sed -i 's/\r$//' <this>; bash <this>"
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}

MU=$H/Mu-Silicium
PORT=$ROOT/port
OUT=$ROOT/out
mkdir -p "$H/logs" "$OUT"
cd "$H"

say() { echo "=== $(date +%H:%M:%S) $* ==="; }

say "git safe.directory (we run as root, the tree is owned by chenyu)"
git config --global --add safe.directory "$MU" || true
git config --global --add safe.directory "$H/hackios-os" || true

say "install port files into Mu-Silicium"
cp -r "$PORT/devices/oneplus-aston/uefi/files/." "$MU/"
git -C "$MU" --no-pager status --porcelain | head -10 || true

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

say "build UEFI astonPkg RELEASE (patched)"
cd "$MU"
"$H/venv/bin/python3" build_uefi.py -d aston -r RELEASE 2>&1 | tee "$H/logs/uefi-aston.log" | tail -30
grep -E "^PROGRESS - (Success|Failed)|Return Code" "$H/logs/uefi-aston.log" | tail -3
FD=$MU/Build/astonPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd
ls -l "$FD"
cp -f "$FD" "$OUT/SILICIUM_UEFI-aston.fd"

say "build BootShim (payload copy to 0xE2000000 enabled)"
cd "$MU/BootShim"
rm -f BootShim.elf BootShim.bin
make REQUIRES_KERNEL_HEADER=1 FD_BASE=0xA7100000 FD_SIZE=0x300000 \
     CFLAGS="--target=aarch64-linux-gnu -DPAYLOAD_BASE=0xE2000000"
ls -l BootShim.bin

say "pack boot-aston-uefi.img (header v4, no payload)"
python3 "$PORT/mkboot-aston.py" --fd "$FD" --out "$OUT/boot-aston-uefi.img"

PAYLOAD=$H/hackios-os/xnuloader/usb-payload.bin
if [ -f "$PAYLOAD" ]; then
  say "pack boot-aston-xnu.img (header v4, payload $(stat -c%s "$PAYLOAD") bytes)"
  python3 "$PORT/mkboot-aston.py" --fd "$FD" --payload "$PAYLOAD" --out "$OUT/boot-aston-xnu.img"
else
  say "no $PAYLOAD yet, skipping boot-aston-xnu.img"
fi

ls -l "$OUT"
echo READY_PORT_UEFI
