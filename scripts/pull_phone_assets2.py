#!/usr/bin/env python3
"""Second pass: the files whose names the first pass got wrong.

What the first pass taught us:
  * There is no a740_gmu.bin.  The GMU microcode ships as gmu_gen70200.bin (and gen70e00.bin);
    the SQE and zap shader are the a740_* ones we already took.
  * Wi-Fi firmware on this build is wlanmdsp.mbn in /vendor/firmware; the board files are not in
    firmware_mnt/image under their usual names.
  * The audio DSP's battery manager has its own jsn (battmgr.jsn) -- that is the firmware the
    accurate percentage would come from.

Read-only.
"""
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIL = os.path.join(ROOT, 'fw', 'ace3', 'files')
IDX = os.path.join(ROOT, 'fw', 'ace3', 'index')
os.makedirs(FIL, exist_ok=True)


def adb(*args, timeout=300):
    try:
        r = subprocess.run(['adb'] + list(args), capture_output=True, timeout=timeout)
        return r.stdout.decode('utf-8', 'replace')
    except Exception as e:
        return 'ERR %s' % e


TAKE = [
    # GPU
    '/vendor/firmware_mnt/image/gmu_gen70200.bin',
    '/vendor/firmware_mnt/image/gmu_gen70e00.bin',
    '/vendor/firmware/a740_zap.elf',
    # battery / DSP battery manager
    '/vendor/firmware_mnt/image/battmgr.jsn',
    '/vendor/firmware_mnt/image/adsp.mdt',
    '/vendor/firmware_mnt/image/adsp.b00',
    '/vendor/firmware_mnt/image/bq28z610.bin',
    # Wi-Fi / Bluetooth
    '/vendor/firmware/wlanmdsp.mbn',
    '/vendor/firmware_mnt/image/wlanmdsp.mbn',
    '/vendor/firmware_mnt/image/bdwlan.bin',
    '/vendor/firmware_mnt/image/amss.bin',
    '/vendor/firmware_mnt/image/m3.bin',
    '/vendor/firmware_mnt/image/regdb.bin',
    # where the board files might hide
    '/vendor/etc/firmware/wlan/qca6490/bdwlan.bin',
    '/vendor/etc/firmware/wlan/bdwlan.bin',
    '/mnt/vendor/persist/wlan/bdwlan.bin',
]

got = []
for src in TAKE:
    dst = os.path.join(FIL, src.replace('/', '__').lstrip('__'))
    if os.path.exists(dst):
        continue
    adb('pull', src, dst)
    if os.path.exists(dst):
        sz = os.path.getsize(dst)
        if sz == 0:
            os.remove(dst)
            continue
        got.append((src, sz))
        print('ok  %-58s %9d' % (src, sz))

# where else could the Wi-Fi board files live?
for name, cmd in {
    'wlan_dirs.txt': 'ls -d /vendor/firmware_mnt/image/*wlan* /vendor/firmware/*wlan* /vendor/etc/firmware/* 2>/dev/null | head -40',
    'wifi_module.txt': 'ls /vendor/lib/modules/ 2>/dev/null | head -60',
    'wifi_prop.txt': 'getprop | grep -i -E "wifi|wlan" | head -20',
}.items():
    text = adb('shell', cmd)
    with open(os.path.join(IDX, name), 'w', encoding='utf-8') as f:
        f.write(text)
    print('index %s (%d bytes)' % (name, len(text)))

print('\n%d files' % len(got))
