#!/usr/bin/env bash
# Build the HakiOS xnuloader for OnePlus Ace 3 (aston):
#   - patch xnuloader/loader.c with the platform_aston hunks (port/patch_hackios_loader.py)
#   - make xnuloader/identity.h (iPhone X identity, 34 KB DeviceTree member out of the IPSW)
#   - build loader.efi and the XNUP payload
#   - repack out/boot-aston-xnu.img (UEFI FD + payload)
#
# Run as: wsl -d Ubuntu -u root -- bash -lc "sed -i 's/\r$//' <this>; bash <this>"
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}

HS=$H/hackios-os
PORT=$ROOT/port
OUT=$ROOT/out
mkdir -p "$H/logs" "$OUT"
cd "$H"

say() { echo "=== $(date +%H:%M:%S) $* ==="; }

say "git safe.directory"
git config --global --add safe.directory "$HS" || true

say "patch xnuloader/loader.c"
python3 "$PORT/patch_hackios_loader.py" "$HS/xnuloader/loader.c"
grep -n "platform_aston\|gic_redist_size" "$HS/xnuloader/loader.c" | head -8

say "xnuloader/identity.h"
if [ ! -f "$HS/xnuloader/identity.h" ]; then
  python3 "$HS/sysimage/fetch-from-ipsw.py" Firmware/all_flash/DeviceTree.d22ap.im4p /tmp/dt.im4p
  python3 "$HS/xnuloader/im4p.py" /tmp/dt.im4p /tmp/dt.lzfse
  "$H/venv/bin/python3" - <<'PY'
import lzfse
open('/tmp/dt.bin', 'wb').write(lzfse.decompress(open('/tmp/dt.lzfse', 'rb').read()))
PY
  python3 "$HS/xnuloader/mkidentity.py" /tmp/dt.bin > "$HS/xnuloader/identity.h"
  wc -c "$HS/xnuloader/identity.h"
else
  echo "identity.h already present"
fi

say "build loader.efi"
cd "$HS"
./xnuloader/build.sh 2>&1 | tail -5
ls -l xnuloader/loader.efi

say "build the XNUP payload (loader resident, commands over USB -- same as xl enter)"
python3 "$HS/xnuloader/mkpayload.py" -o "$HS/xnuloader/usb-payload.bin" loader.efi="$HS/xnuloader/loader.efi" --usb
ls -l "$HS/xnuloader/usb-payload.bin"

say "repack boot-aston-xnu.img"
python3 "$PORT/mkboot-aston.py" --fd "$OUT/SILICIUM_UEFI-aston.fd" \
        --payload "$HS/xnuloader/usb-payload.bin" --out "$OUT/boot-aston-xnu.img"

ls -l "$OUT"
echo READY_LOADER_ASTON
