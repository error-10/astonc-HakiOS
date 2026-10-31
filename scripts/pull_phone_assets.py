#!/usr/bin/env python3
"""Harvest the hardware assets a HakiOS port needs from the phone's Android side.

Read-only: only `adb shell ls`, `adb shell cat` and `adb pull`.  Nothing is written to the phone.

What is taken, and why:

  GPU      the Adreno 740's GMU / SQE microcode and the zap shader.  GX is owned by the GMU, so
           without its firmware there is no way past the power domain.
  battery  the BQ28Z610 fuel gauge calibration plus every power_supply reading -- that is what
           turns the loader's voltage guess into a real percentage.
  Wi-Fi    the QCA6490's firmware and board files, needed once the PCIe link comes up.
  fdt      the real device tree: soc.args, PMIC SIDs, I2C buses.

Usage:  python scripts\\pull_phone_assets.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'fw', 'ace3')
IDX = os.path.join(OUT, 'index')
FIL = os.path.join(OUT, 'files')
for d in (IDX, FIL):
    os.makedirs(d, exist_ok=True)


def adb(*args, timeout=120):
    try:
        r = subprocess.run(['adb'] + list(args), capture_output=True, timeout=timeout)
        return r.stdout.decode('utf-8', 'replace')
    except Exception as e:
        return 'ERR %s' % e


dev = adb('devices')
if '\tdevice' not in dev:
    print('no adb device; boot Android, enable USB debugging, then run again')
    print(dev)
    sys.exit(1)

adb('root')
adb('wait-for-device')

# ---- 1. an index of what is actually on the phone ------------------------------------------------
probes = {
    'vendor_firmware.txt': 'ls -l /vendor/firmware',
    'firmware_mnt_image.txt': 'ls -l /vendor/firmware_mnt/image',
    'vendor_etc_firmware.txt': 'ls -l /vendor/etc/firmware',
    'vendor_etc_wifi.txt': 'ls -l /vendor/etc/wifi',
    'power_supply.txt': 'ls /sys/class/power_supply/',
    'soc.txt': 'getprop ro.soc.model; getprop ro.board.platform; getprop ro.build.display.id',
    'gpu_sysfs.txt': 'ls /sys/class/kgsl/kgsl-3d0/ ; cat /sys/class/kgsl/kgsl-3d0/gpu_model',
}
for name, cmd in probes.items():
    text = adb('shell', cmd)
    with open(os.path.join(IDX, name), 'w', encoding='utf-8') as f:
        f.write(text)
    print('index %-24s %6d bytes' % (name, len(text)))

# every readable file of the battery node, one per line
bat = adb('shell', 'for f in /sys/class/power_supply/*/*; do echo -n "$f="; cat "$f" 2>/dev/null; echo; done')
with open(os.path.join(IDX, 'power_supply_all.txt'), 'w', encoding='utf-8') as f:
    f.write(bat)
print('index %-24s %6d bytes' % ('power_supply_all.txt', len(bat)))

# ---- 2. the real device tree ---------------------------------------------------------------------
fdt = os.path.join(FIL, 'fdt')
if not os.path.exists(fdt):
    adb('pull', '/sys/firmware/fdt', fdt)
print('fdt %s' % ('ok' if os.path.exists(fdt) else 'MISSING (needs root)'))

# ---- 3. the files themselves ---------------------------------------------------------------------
GPU = ['a740_gmu.bin', 'a740_sqe.fw', 'a740_aqe.fw', 'a740_zap.mdt'] + \
      ['a740_zap.b%02d' % i for i in range(10)] + ['a740_zap.mbn', 'a740_zap.bin'] + \
      ['gen70000_gmu.bin', 'gen70000_sqe.fw', 'gen70000_zap.mbn']
BATT = ['bq28z610.bin', 'bq28z610_b0.bin', 'bq28z610_0.bin', 'bq28z610_1.bin']
WIFI = ['bdwlan.bin'] + ['bdwlan.b%d' % i for i in range(16)] + \
       ['amss.bin'] + ['amss.b%d' % i for i in range(8)] + \
       ['m3.bin', 'regdb.bin', 'WCNSS_qcom_cfg.ini', 'WCNSS_qcom_wlan_nv.bin', 'wlan_mac.bin']

got = 0
for base in ('firmware_mnt/image', 'firmware', 'etc/firmware'):
    for name in GPU + BATT + WIFI:
        src = '/vendor/%s/%s' % (base, name)
        dst = os.path.join(FIL, '%s__%s' % (base.replace('/', '_'), name))
        if os.path.exists(dst):
            continue
        adb('pull', src, dst, timeout=180)
        if os.path.exists(dst):
            sz = os.path.getsize(dst)
            if sz == 0:
                os.remove(dst)
                continue
            got += 1
            print('ok   %-46s %9d' % (src, sz))

print('\n%d files -> %s' % (got, FIL))
print('index in %s (read firmware_mnt_image.txt first: the names are what matter)' % IDX)
