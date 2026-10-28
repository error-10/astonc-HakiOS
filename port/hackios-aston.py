#!/usr/bin/env python3
"""Drive the HakiOS port on a OnePlus Ace 3 (aston) from the host, over fastboot.

Nothing here writes to the phone's flash: `fastboot boot` puts the UEFI+payload image in
RAM, and the resident XNU loader (which answers fastboot commands over USB) takes the
kernel and log back and forth with `stage` / `oem run` / `get_staged`.

Commands
  status                 show fastboot state and what is in out/
  boot-uefi              boot out/boot-aston-uefi.img   (UEFI only, no loader: first test)
  boot-loader            boot out/boot-aston-xnu.img   (UEFI + XNU loader in USB mode)
  boot-auto              boot out/boot-aston-auto.img  (one shot: the loader starts the kernel alone)
  ramdisk [FILE|none]    upload the resident system image (default out/system.apfs) to RAM
  payload [--secs N] [--root FILE] [--ramdisk FILE] [--cmdline "..."]
                         build out/run-payload.bin for the loader
  run     [--secs N] [--root FILE] [--ramdisk FILE] [--cmdline "..."] [--follow N]
                         boot the loader if needed, stage the payload, `oem run`, fetch the log
  log                    fetch the loader/kernel log to out/loader.log
  reboot                 cold reset back to Android

The cookie-cutter sequence on a fresh phone is:  boot-uefi  ->  boot-loader  ->  ramdisk  ->  run.
Nothing is written to the phone's flash at any point.

Hosts: works on Windows (scoop/adb platform-tools in PATH) and inside the WSL build tree;
paths are taken relative to this file, so run it from anywhere.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
OUT = os.path.join(WS, 'out')
FASTBOOT = os.environ.get('FASTBOOT', 'fastboot')
MKPAYLOAD = os.environ.get('MKPAYLOAD', os.path.join(
    WS, 'repos', 'hackios-xnu-kernel', 'xnuloader', 'mkpayload.py'))
KERNEL = os.environ.get('KERNEL', os.path.join(OUT, 'mach.development.bcm2837'))
LOADER = os.environ.get('LOADER', os.path.join(OUT, 'loader-aston.efi'))
PAYLOAD = os.path.join(OUT, 'run-payload.bin')
DEFAULT_SECS = 30
SYSIMAGE = os.path.join(OUT, 'system.apfs')
SOC_ARGS = os.path.join(WS, 'port', 'devices', 'oneplus-aston', 'soc.args')
# The kernel command line the port needs on top of whatever the caller passes: the loader
# reports where it put the payload on stdout, `rd=md0` is the resident system image, and
# `hv_wdt_pet=1` lets the loader keep the phone's virtual watchdog fed while XNU runs.
BASE_CMDLINE = 'debug=0x8 cpus=8 rd=md0 hv_wdt_pet=1 aston_touch=1 aston_touch_ldo=1 battery=1'


def fb(*args, timeout=30, capture=True):
    cmd = [FASTBOOT, *args]
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
    except FileNotFoundError:
        sys.exit(f'{FASTBOOT} not found in PATH: install Android platform-tools '
                 '(scoop install adb, or put platform-tools on PATH)')
    except subprocess.TimeoutExpired:
        return 1, ''
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def devices():
    _, out = fb('devices')
    return [line.split()[0] for line in out.splitlines() if line.strip() and 'fastboot' in line]


def state():
    if not devices():
        return 'absent'
    _, out = fb('getvar', 'product')
    return 'loader' if 'xnuloader' in out else 'fastboot'


def report():
    print(f'fastboot : {shutil.which(FASTBOOT) or FASTBOOT}')
    print(f'state    : {state()}')
    if os.path.isdir(OUT):
        for name in sorted(os.listdir(OUT)):
            p = os.path.join(OUT, name)
            if os.path.isfile(p):
                print(f'  {os.path.getsize(p):>10}  {name}')


def require_loader():
    st = state()
    if st == 'loader':
        return
    if st == 'absent':
        sys.exit('no phone in fastboot: plug it in, hold Power+VolumeDown until fastboot shows')
    if st == 'fastboot':
        sys.exit('the phone is in stock fastboot, not in the XNU loader: '
                 'run "boot-loader" first (or "boot-uefi" for the UEFI-only test)')


def wait_loader(seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        if state() == 'loader':
            return True
        time.sleep(2)
    return False


def boot_image(path):
    if not os.path.isfile(path):
        sys.exit(f'missing {path}')
    print(f'fastboot boot {path}')
    rc, out = fb('boot', path, timeout=120)
    print(out.strip())
    if rc != 0 or 'OKAY' not in out.upper():
        sys.exit(f'fastboot boot was refused (rc={rc})')


def soc_args():
    """devices/oneplus-aston/soc.args as one string, the way tools/modem-cycle.sh feeds it.

    Comments and blank lines are dropped: the kernel command line is a single string and a
    '#' in it would just become part of the next argument.
    """
    if not os.path.isfile(SOC_ARGS):
        return ''
    tokens = []
    with open(SOC_ARGS, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if line:
                tokens.extend(line.split())
    return ' '.join(tokens)


def build_payload(secs, root, cmdline):
    if not os.path.isfile(MKPAYLOAD):
        sys.exit(f'missing {MKPAYLOAD}')
    if not os.path.isfile(KERNEL):
        sys.exit(f'missing kernel {KERNEL} (build it with scripts/build_kernel_aston.sh in WSL)')
    if not os.path.isfile(LOADER):
        sys.exit(f'missing loader {LOADER} (build it with scripts/build_loader_aston.sh in WSL)')
    # No implicit "-v": the kernel's verbose console paints scrolling text over the framebuffer,
    # which looks alarming on the phone. Ask for it explicitly with --cmdline "... -v" when needed.
    line = ' '.join(x for x in (f'loader_return_after={secs}', BASE_CMDLINE, soc_args(),
                                cmdline or '') if x.strip())
    args = ['--cmdline', line]
    # Like `xl run`: the loader is already resident, so the payload carries only what it runs
    # (kernel, optional root ramdisk) and the command line -- not loader.efi itself.
    entries = [f'kernel={KERNEL}']
    if root:
        if not os.path.isfile(root):
            sys.exit(f'missing root ramdisk {root} (make images)')
        entries.append(f'ramdisk={root}')
    subprocess.check_call([sys.executable, MKPAYLOAD, '-o', PAYLOAD, *entries, *args])
    print(f'payload cmdline: {line}')
    return PAYLOAD


def upload_ramdisk(path):
    """`fastboot oem ramdisk` opens the window, `stage` fills it: the image stays resident in RAM."""
    require_loader()
    if path in ('none', '-'):
        rc, out = fb('oem', 'ramdisk', 'none', timeout=30)
        print(out.strip())
        return
    if not os.path.isfile(path):
        sys.exit(f'missing resident image {path} (build it with make images in WSL)')
    rc, out = fb('oem', 'ramdisk', timeout=30)
    print(out.strip())
    if rc != 0 or 'OKAY' not in out.upper():
        sys.exit('the loader refused to open a ramdisk window (no free memory?)')
    size = os.path.getsize(path)
    print(f'uploading {size / 1048576:.0f} MB to the resident window, this takes a while')
    t0 = time.time()
    rc, out = fb('stage', path, timeout=1800)
    print(out.strip())
    if rc != 0 or 'OKAY' not in out.upper():
        sys.exit('stage failed')
    dt = max(1.0, time.time() - t0)
    print(f'resident image uploaded: {size / 1048576:.0f} MB in {dt:.0f} s '
          f'({size / 1048576 / dt:.1f} MB/s)')


def get_log(path=os.path.join(OUT, 'loader.log')):
    fb('oem', 'log', timeout=30)
    rc, _ = fb('get_staged', path, timeout=60)
    if rc != 0 or not os.path.isfile(path) or os.path.getsize(path) == 0:
        print('log: nothing staged by the loader')
        return None
    # The loader pads the transfer; keep the text up to the last newline.
    raw = open(path, 'rb').read().replace(b'\0', b'')
    open(path, 'wb').write(raw)
    print(raw.decode(errors='replace'))
    print(f'log saved to {path}')
    return path


def get_readlog(path=os.path.join(OUT, 'logdump.log')):
    """The log a previous run left in the log partition: the kernel's own USB is gone by the
    time it writes it, so this is read back by a freshly booted loader ("oem readlog")."""
    require_loader()
    rc, out = fb('oem', 'readlog', timeout=60)
    print(out.strip())
    if rc != 0 or 'OKAY' not in out.upper():
        sys.exit('the loader could not read the log partition')
    rc, _ = fb('get_staged', path, timeout=120)
    if rc != 0 or not os.path.isfile(path) or os.path.getsize(path) == 0:
        sys.exit('nothing came back from get_staged')
    raw = open(path, 'rb').read()
    # Keep the text part: the log partition copy is padded to whole blocks.
    cut = raw.rfind(b'\n')
    raw = raw[:cut + 1] if cut > 0 else raw.rstrip(b'\0')
    open(path, 'wb').write(raw)
    print(raw.decode(errors='replace'))
    print(f'log saved to {path}')
    return path


def main():
    ap = argparse.ArgumentParser(description='HakiOS on OnePlus Ace 3 (aston) over fastboot')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status')
    sub.add_parser('boot-uefi')
    sub.add_parser('boot-loader')
    sub.add_parser('boot-auto')
    r = sub.add_parser('ramdisk')
    r.add_argument('file', nargs='?', default=SYSIMAGE,
                   help='system image to keep resident in RAM (default out/system.apfs; "none" drops it)')
    sub.add_parser('payload')
    sub.add_parser('run')
    for q in (sub.choices['payload'], sub.choices['run']):
        q.add_argument('--secs', type=int, default=DEFAULT_SECS)
        q.add_argument('--root', default='',
                       help='root.apfs for /dev/md1 (default out/root.apfs when it exists)')
        q.add_argument('--cmdline', default='')
        q.add_argument('--follow', type=int, default=0,
                       help='fetch the log every N seconds while the run is going on')
    sub.add_parser('log')
    sub.add_parser('readlog')
    sub.add_parser('reboot')
    a = ap.parse_args()

    if a.cmd == 'status':
        report()
    elif a.cmd == 'boot-uefi':
        boot_image(os.path.join(OUT, 'boot-aston-uefi.img'))
    elif a.cmd == 'boot-auto':
        boot_image(os.path.join(OUT, 'boot-aston-auto.img'))
        print('one shot: the loader starts the kernel by itself (no USB commands needed); '
              'with no logs to fetch, watch the phone screen')
    elif a.cmd == 'boot-loader':
        boot_image(os.path.join(OUT, 'boot-aston-xnu.img'))
        if wait_loader():
            print('loader is up (product: xnuloader)')
        else:
            print('loader did not answer on USB; the UEFI stage may have failed - '
                  'boot "boot-uefi" and look at the screen')
    elif a.cmd == 'ramdisk':
        upload_ramdisk(a.file)
    elif a.cmd in ('payload', 'run'):
        root = a.root or (os.path.join(OUT, 'root.apfs')
                          if os.path.isfile(os.path.join(OUT, 'root.apfs')) else '')
        if a.cmd == 'payload':
            build_payload(a.secs, root, a.cmdline)
        else:
            require_loader()
            path = build_payload(a.secs, root, a.cmdline)
            print(f'fastboot stage {path}')
            rc, out = fb('stage', path, timeout=300)
            print(out.strip())
            if rc != 0 or 'OKAY' not in out.upper():
                sys.exit('stage failed')
            rc, out = fb('oem', 'run', timeout=30)
            print(out.strip())
            end = time.time() + a.secs + 120
            result = ''
            last_follow = time.time()
            while time.time() < end:
                _, got = fb('getvar', 'result', timeout=20)
                line = next((l for l in got.splitlines() if l.startswith('result:')), '')
                if line and 'running' not in line:
                    result = line
                    break
                if a.follow and time.time() - last_follow >= a.follow:
                    last_follow = time.time()
                    fb('oem', 'log', timeout=30)
                    fb('get_staged', os.path.join(OUT, 'loader.log.live'), timeout=60)
                    print(f'[{time.strftime("%H:%M:%S")}] log snapshot -> out/loader.log.live')
                time.sleep(2)
            print(result or 'result: no answer (kernel hung or watchdog reset) - check the phone')
            get_log()
    elif a.cmd == 'log':
        require_loader()
        get_log()
    elif a.cmd == 'readlog':
        get_readlog()
    elif a.cmd == 'reboot':
        fb('reboot')


if __name__ == '__main__':
    main()
