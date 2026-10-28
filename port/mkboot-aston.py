#!/usr/bin/env python3
"""Pack the aston boot chain into an Android boot image (header v4), portable across the
WSL build host and the Windows host that drives fastboot.

  kernel = gzip(BootShim + UEFI FD [+ XNUP payload]) + aston.dtb

BootShim copies the FD to 0xA7100000 (the UEFI FD window in the phone's own memory map)
and, when built with the payload patch, the XNUP container to PAYLOAD_BASE (0xE2000000 —
*not* 0xF0000000: aston's Trusted VM lives at 0xF3800000).

Every path can be overridden with an environment variable so the same script works from
the WSL tree and from the Windows checkout (out/ holds BootShim-aston.bin, aston.dtb and
the ramdisk stub exactly for this).

usage: mkboot-aston.py --fd PATH/to/SILICIUM_UEFI.fd [--payload p.bin] [--out boot.img]
"""
import argparse
import gzip
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(HERE)                       # .../ios
REPOS = os.path.join(WORKSPACE, 'repos')
MU = os.environ.get('MU_DIR', os.path.join(REPOS, 'Mu-Silicium'))

FD_BASE, FD_SIZE = 0xA7100000, 0x300000
PAYLOAD_BASE, PAYLOAD_MAX = 0xE2000000, 0x04000000
# The boot image parameters are the ones Mu-Silicium's own Resources/Configs/aston.toml
# declares for this device ([boot_image]: header_version 4, os_version 16.0.0, patch 2026-06;
# [boot_image_kernel]: kernel_compression gzip, append_dtb true) -- keep them in step.
HEADER_VERSION = os.environ.get('BOOT_HEADER', '4')
OS_VERSION = os.environ.get('BOOT_OS_VERSION', '16.0.0')
OS_PATCH = os.environ.get('BOOT_OS_PATCH', '2026-06')


def find(name, env, *candidates):
    p = os.environ.get(env)
    if p:
        return p
    for c in candidates:
        if os.path.isfile(c):
            return c
    sys.exit(f'{name} not found; set {env} or build it (tried: {", ".join(candidates)})')


ap = argparse.ArgumentParser()
ap.add_argument('--fd', required=True)
ap.add_argument('-p', '--payload')
ap.add_argument('-o', '--out', default=os.path.join(WORKSPACE, 'out', 'boot-aston.img'))
ap.add_argument('--dtb')
ap.add_argument('--shim')
ap.add_argument('--ramdisk')
ap.add_argument('--mkbootimg')
args = ap.parse_args()

shim = open(find('BootShim.bin', 'SHIM',
                 os.path.join(WORKSPACE, 'out', 'BootShim-aston.bin'),
                 os.path.join(MU, 'BootShim/BootShim.bin')), 'rb').read()
dtb = open(args.dtb or find('aston.dtb', 'DTB',
                            os.path.join(WORKSPACE, 'out', 'aston.dtb'),
                            os.path.join(MU, 'Resources/DTBs/aston.dtb')), 'rb').read()
ramdisk = args.ramdisk or find('ramdisk', 'RAMDISK',
                               os.path.join(WORKSPACE, 'out', 'ramdisk'),
                               os.path.join(MU, 'Resources/ramdisk'))
mkbootimg = args.mkbootimg or find('mkbootimg.py', 'MKBOOTIMG',
                                   os.path.join(MU, 'Resources/Scripts/mkbootimg.py'))

fd = open(args.fd, 'rb').read()
if len(fd) > FD_SIZE:
    sys.exit(f'FD is {len(fd):#x} > FD_SIZE {FD_SIZE:#x}; BootShim would not copy all of it')

blob = shim + fd
if args.payload:
    data = open(args.payload, 'rb').read()
    if data[:4] != b'XNUP' or len(data) > PAYLOAD_MAX - 0x1000:
        sys.exit('payload is not XNUP or is bigger than the reserved window')
    blob += data
    print(f'payload: {len(data)} bytes, bytesum={sum(data) & 0xffffffff:08x}')
blob += b'\0' * (-len(blob) % 16)

tmp = args.out + '.kernel~'
open(tmp, 'wb').write(gzip.compress(blob, 6) + dtb)
cmd = [sys.executable, mkbootimg, '--kernel', tmp,
       '--ramdisk', ramdisk, '--header_version', HEADER_VERSION,
       '--base', '0x0', '--os_version', OS_VERSION, '--os_patch_level', OS_PATCH,
       '-o', args.out]
try:
    subprocess.check_call(cmd)
finally:
    os.unlink(tmp)

print(f'{args.out}: {os.path.getsize(args.out)} bytes '
      f'(shim {len(shim)}, fd {len(fd)}, uncompressed {len(blob)}, dtb {len(dtb)}, header v{HEADER_VERSION})')
