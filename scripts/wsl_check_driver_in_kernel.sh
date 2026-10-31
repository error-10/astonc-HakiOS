#!/usr/bin/env bash
cd /home/chenyu/hackios/hackios-os || exit 1
echo "--- conf/files entry:"
grep -n "aston_touch" xnu-src/xnu-8796.121.2/bsd/conf/files xnu/hakios.patch 2>/dev/null | head
echo "--- string in the built kernel:"
for s in "s3910: probe" "s3910: ready" "aston touch"; do
  printf '%-18s ' "$s"; grep -c "$s" /mnt/c/Users/96943/Desktop/ios/out/mach.development.bcm2837 || true
done
echo "--- kernel log ring size in loader context:"
grep -n "CTX_LOG_PA\|LOG_PA\|log_size\|LOG_SIZE" xnuloader/loader.c | head -20
