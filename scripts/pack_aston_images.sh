#!/bin/bash
# Repack the two fastboot images from what is already built in the WSL tree and copy them,
# with their inputs, into the Windows workspace's out/.
#
#   boot-aston-uefi.img   shim + patched UEFI FD + aston.dtb          (first test)
#   boot-aston-xnu.img    the same + XNUP payload (loader.efi + usb)  (resident loader)
set -euo pipefail
H="$HOME/hackios/hackios-os"
MU="$HOME/hackios/Mu-Silicium"
OUT="/mnt/c/Users/96943/Desktop/ios/out"
PORT="/mnt/c/Users/96943/Desktop/ios/port"
FD="$MU/Build/astonPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd"

mkdir -p "$OUT"
[ -f "$FD" ] || { echo "pack_aston: no $FD" >&2; exit 1; }
cp -f "$MU/BootShim/BootShim.bin"      "$OUT/BootShim-aston.bin"
cp -f "$MU/Resources/DTBs/aston.dtb"   "$OUT/aston.dtb"
cp -f "$MU/Resources/ramdisk"          "$OUT/ramdisk"
cp -f "$FD"                            "$OUT/SILICIUM_UEFI-aston.fd"

python3 "$PORT/mkboot-aston.py" --fd "$OUT/SILICIUM_UEFI-aston.fd" \
	-o "$OUT/boot-aston-uefi.img"

if [ -f "$H/xnuloader/usb-payload.bin" ]; then
	python3 "$PORT/mkboot-aston.py" --fd "$OUT/SILICIUM_UEFI-aston.fd" \
		-p "$H/xnuloader/usb-payload.bin" -o "$OUT/boot-aston-xnu.img"
fi
ls -l "$OUT"/*.img
