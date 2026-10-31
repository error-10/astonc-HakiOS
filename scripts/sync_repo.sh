#!/bin/bash
# Bring the working tree (WSL build tree + this repo's helper scripts) into the repo, so that what
# we have learned is in git and not only on this laptop.
#
# Sources are copied as they are; the files we changed inside upstream HakiOS are exported as one
# patch, so the repo stays readable and the changes remain reviewable against upstream.
set -e

IOS=/mnt/c/Users/96943/Desktop/ios
REPO=$IOS/repos/astonc-HakiOS
SRC=/home/chenyu/hackios/hackios-os
UP=$IOS/repos/hackios-xnu-kernel

mkdir -p "$REPO/port/kernel" "$REPO/port/loader" "$REPO/scripts"

# 1. files that are entirely ours
for f in hakios.aston_wifi.c hakios.aston_pcie_phy_seq.h hakios.a740.c \
         hakios.aston_touch.c hakios.aston_touch_hw.h; do
	cp "$SRC/xnu/files/bsd/dev/$f" "$REPO/port/kernel/$f"
	echo "copied $f"
done
cp "$SRC/xnu/files/iokit/Kernel/hakios.gpu.cpp" "$REPO/port/kernel/hakios.gpu.cpp" 2>/dev/null || true

# 2. changes we made inside upstream files, as one patch
: > "$REPO/port/kernel/upstream.patch"
for f in bsd/dev/hakios.adsp.c bsd/dev/hakios.battery.c bsd/dev/hakios.camera.c \
         bsd/dev/hakios.cpufreq.c bsd/dev/hakios.goodix.c bsd/dev/hakios.input.c \
         bsd/dev/hakios.mpss.c bsd/dev/hakios.wifi.c bsd/sys/hakios.input.h \
         iokit/Kernel/hakios.battery.cpp; do
	if [ -f "$UP/xnu/files/$f" ]; then
		diff -u "$UP/xnu/files/$f" "$SRC/xnu/files/$f" \
			--label "a/xnu/files/$f" --label "b/xnu/files/$f" >> "$REPO/port/kernel/upstream.patch" || true
	fi
done
echo "patch: $(wc -l < "$REPO/port/kernel/upstream.patch") lines"

# 3. the small scripts that reproduce today's work
cp "$IOS"/scripts/*.py "$REPO/scripts/" 2>/dev/null || true
cp "$IOS"/scripts/*.sh "$REPO/scripts/" 2>/dev/null || true
cp "$IOS/port/hackios-aston.py" "$REPO/port/" 2>/dev/null || true
cp "$IOS/port/cycle.py" "$REPO/port/" 2>/dev/null || true
echo "scripts: $(ls "$REPO/scripts" | wc -l) files"
