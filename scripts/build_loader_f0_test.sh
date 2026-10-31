#!/usr/bin/env bash
# Experiment: build our loader with PAYLOAD_BASE=0xF0000000 (like upstream) and run it
# under QEMU the same way the pristine prebuilt loader is run, to isolate whether the
# launchd ENOEXEC is caused by our loader code or by the payload/window placement.
set -euo pipefail

H=/home/chenyu/hackios
HS=$H/hackios-os
cd "$HS"

# 1. switch the define in the patched loader.c
sed -i 's|^#define PAYLOAD_BASE        0xE2000000ULL|#define PAYLOAD_BASE        0xF0000000ULL|' xnuloader/loader.c
grep -n "define PAYLOAD_BASE" xnuloader/loader.c

# 2. rebuild loader.efi
./xnuloader/build.sh 2>&1 | tail -3
cp xnuloader/loader.efi xnuloader/loader-f0.efi
ls -l xnuloader/loader-f0.efi

# 3. run scripts: loader from xnuloader/loader-f0.efi, payload at 0xF0000000
python3 - <<'PY'
base = "/home/chenyu/hackios/hackios-os/qemu/"
s = open(base + "run-up.sh").read()
s = s.replace("L=../prebuilt/loader.efi; [ -f $L ] || L=../prebuilt/loader.efi",
              "L=../xnuloader/loader-f0.efi; [ -f $L ] || L=../prebuilt/loader.efi", 1)
open(base + "run-up-f0.sh", "w").write(s)

s = open(base + "run-ios-up.sh").read()
s = s.replace("exec qemu/run-up.sh", "exec qemu/run-up-f0.sh", 1)
open(base + "run-ios-f0.sh", "w").write(s)
print("run scripts written")
PY
chmod +x qemu/run-up-f0.sh qemu/run-ios-f0.sh

# 4. run it
rm -rf qemu/esp
QEMU_INSTANCE=4 ./qemu/run-ios-f0.sh 60 > logs/qemu-f0.log 2>&1 || true
echo "rc=$?"
grep -n 'largest free block\|phys window\|return slot\|jumping to\|launchd\|panic' logs/qemu-f0.log | head -12

# 5. restore the define
sed -i 's|^#define PAYLOAD_BASE        0xF0000000ULL|#define PAYLOAD_BASE        0xE2000000ULL|' xnuloader/loader.c
grep -n "define PAYLOAD_BASE" xnuloader/loader.c
echo DONE_F0_TEST
