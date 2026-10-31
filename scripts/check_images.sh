#!/usr/bin/env bash
# Parse the boot image headers we produced and print what ABL will see.
OUT=/mnt/c/Users/96943/Desktop/ios/out
CHK=/mnt/c/Users/96943/Desktop/ios/port/check_boot.py
for f in boot-aston-uefi.img boot-aston-xnu.img boot-aston-full.img; do
  python3 "$CHK" "$OUT/$f"
  echo
done
