#!/usr/bin/env bash
# Stage the port sources into the publication checkout (repos/astonc-HakiOS).
set -euo pipefail
R=/mnt/c/Users/96943/Desktop/ios
D=$R/repos/astonc-HakiOS
mkdir -p "$D/port" "$D/scripts" "$D/docs"
cp -r "$R/port/." "$D/port/"
cp "$R/STATUS.md" "$D/docs/STATUS.md"
for f in rebuild_aston_all.sh build_uefi_aston.sh build_loader_aston.sh build_kernel_aston.sh \
         build_payload_aston.sh build_images_aston.sh install_touch_aston.sh build_port_aston.sh \
         check_images.sh check_tools.sh panic_sym.sh sym_at.sh disasm.sh fetch.js; do
  if [ -f "$R/scripts/$f" ]; then cp "$R/scripts/$f" "$D/scripts/"; else echo "missing $f"; fi
done
echo "staged:"; find "$D" -maxdepth 2 -mindepth 1 -not -path '*/.git/*' | sort | sed -n '1,40p'
du -sh "$D"
