#!/usr/bin/env bash
# Final offline validation of the whole boot chain under QEMU with our loader.
#
# What was wrong: the loader places the resident root image at win_base + 0x08000000.
# QEMU preloads the system image at RD_ADDR=0xFC000000, which only matches when the
# kernel window base is 0xF4000000 (payload at 0xF0000000). With our loader the
# payload sits at 0xE2000000 -> window base 0xE6000000 -> the resident image must be
# preloaded at 0xEE000000. Otherwise the kernel mounts a garbage md0 and the exec of
# launchd fails with ENOEXEC (this was the panic seen at 11:20).
set -uo pipefail
H=/home/chenyu/hackios
HS=$H/hackios-os
cd "$HS"

python3 - <<'PY'
base = "/home/chenyu/hackios/hackios-os/qemu/"
src = open(base + "run-ios-aston.sh").read()
assert "RD_ADDR=0xFC000000" in src
for name, kernel in (("run-ios-hybrid3.sh", "prebuilt/mach.development.bcm2837"),
                     ("run-ios-own3.sh", None)):
    s = src.replace("RD_ADDR=0xFC000000", "RD_ADDR=0xEE000000", 1)
    if kernel:
        s = s.replace("K=xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837",
                      "K=" + kernel, 1)
    open(base + name, "w").write(s)
print("run scripts written")
PY
chmod +x qemu/run-ios-hybrid3.sh qemu/run-ios-own3.sh

run_one() {
  local script=$1 inst=$2 log=$3
  rm -rf qemu/esp qemu/ram.img
  QEMU_INSTANCE=$inst ./qemu/$script 60 > "logs/$log" 2>&1
  echo "=== $log"
  grep -n 'largest free block\|resident image at pa\|Darwin Kernel Version\|launchd.ios\|SpringBoard\|panic(' "logs/$log" | head -12
}

run_one run-ios-hybrid3.sh 5 qemu-hybrid3.log
run_one run-ios-own3.sh 6 qemu-own3.log
echo DONE_QEMU_VALIDATE
