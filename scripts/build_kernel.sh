#!/bin/bash
# Build the XNU kernel from xnu/files.
#
# xnu-build.sh compiles xnu-src/xnu-8796.121.2 -- NOT xnu/files.  Every edit under xnu/files has to
# be copied in first, or the build happily produces a kernel without it (this has silently cost a
# whole test cycle before).  So: copy the port's sources, then build, then report.
#
# usage: bash scripts/build_kernel.sh [logname]
set -e
HS=/home/chenyu/hackios/hackios-os
X=$HS/xnu-src/xnu-8796.121.2
OUT=/mnt/c/Users/96943/Desktop/ios
LOG=$OUT/logs/${1:-kernel.log}

mkdir -p "$OUT/logs"

# the port's own sources: kernel side C, its headers, and the iokit side
cp "$HS"/xnu/files/bsd/dev/hakios.*.c        "$X/bsd/dev/"        2>/dev/null || true
cp "$HS"/xnu/files/bsd/sys/hakios.*.h        "$X/bsd/sys/"        2>/dev/null || true
cp "$HS"/xnu/files/iokit/Kernel/hakios.*.cpp "$X/iokit/Kernel/"   2>/dev/null || true
cp "$HS"/xnu/files/iokit/Kernel/hakios.*.h   "$X/iokit/Kernel/"   2>/dev/null || true

cd "$HS"
./xnu-build.sh -j8 -k > "$LOG" 2>&1 || true

echo "errors:"
grep -E 'hakios\.[a-z_]+\.(c|cpp):[0-9]+:[0-9]+: error' "$LOG" | head -20 || true
if grep -q '^BUILD FAILED' "$LOG" 2>/dev/null; then
	echo "build reported failure"
fi

cp "$X/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837" "$OUT/out/mach.development.bcm2837"
ls -l "$OUT/out/mach.development.bcm2837"
