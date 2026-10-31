#!/usr/bin/env bash
set -uo pipefail
cd /mnt/c/Users/96943/Desktop/ios/repos/astonc-HakiOS/scripts || exit 1
fail=0
for f in *.sh; do
  if ! bash -n "$f" 2>/tmp/err; then echo "SYNTAX FAIL $f"; cat /tmp/err; fail=1; fi
done
cd ../port || exit 1
for f in *.py; do
  if ! python3 -m py_compile "$f" 2>/tmp/err2; then echo "PY FAIL $f"; cat /tmp/err2; fail=1; fi
done
rm -rf __pycache__
echo "checked scripts+port, fail=$fail"
head -8 /mnt/c/Users/96943/Desktop/ios/repos/astonc-HakiOS/scripts/build_uefi_aston.sh
