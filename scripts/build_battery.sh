#!/bin/bash
# Copy the battery sources into the XNU build tree and rebuild the kernel.
#
# Why this script exists: xnu-build.sh compiles xnu-src/xnu-8796.121.2, not xnu/files.
# Editing xnu/files and running the build silently produces the old kernel -- that has already
# cost a full test cycle once.  Every edit under xnu/files needs this copy first.
set -e
HS=/home/chenyu/hackios/hackios-os
X=$HS/xnu-src/xnu-8796.121.2
OUT=/mnt/c/Users/96943/Desktop/ios

cp "$HS/xnu/files/bsd/dev/hakios.battery.c"        "$X/bsd/dev/"
cp "$HS/xnu/files/iokit/Kernel/hakios.battery.cpp" "$X/iokit/Kernel/"

grep -c 'has not moved' "$X/bsd/dev/hakios.battery.c"

cd "$HS"
./xnu-build.sh -j8 -k > "$OUT/logs/kernel-batt2.log" 2>&1 || true

echo "errors:"
grep -E 'hakios\.battery\.(c|cpp):[0-9]+:[0-9]+: error' "$OUT/logs/kernel-batt2.log" | head -10 || true

cp "$X/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837" "$OUT/out/mach.development.bcm2837"
ls -l "$OUT/out/mach.development.bcm2837"
