"""One unattended cycle: wait for the phone, boot the loader, upload the image, run a probe.

Written because the manual sequence kept losing the phone between steps: after
`fastboot boot` the loader re-enumerates on USB, and a command sent two seconds later
finds nothing. Every step here waits for the phone to come back before it starts.

    python port/cycle.py "aston_wifi_only=5 -v" [--secs 40] [--no-image] [--wait 240]
"""
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'aston', os.path.join(HERE, 'hackios-aston.py'))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def wait_for_phone(seconds):
    """fastboot devices until something shows up, or until the time is up."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if h.devices():
            return True
        time.sleep(3)
    return False


def product():
    """`kalama` from stock fastboot, `xnuloader` once our loader is running, '' if nothing."""
    return h.state()


def main():
    args = sys.argv[1:]
    cmdline = args[0] if args and not args[0].startswith('--') else '-v'
    secs = 40
    image = True
    wait = 240
    if '--secs' in args:
        secs = int(args[args.index('--secs') + 1])
    if '--wait' in args:
        wait = int(args[args.index('--wait') + 1])
    if '--no-image' in args:
        image = False

    print(f'cycle: waiting up to {wait} s for the phone in fastboot')
    if not wait_for_phone(wait):
        print('cycle: no phone; nothing done')
        return 2

    print(f'cycle: phone present, state={h.state()}')

    for attempt in (1, 2, 3):
        try:
            if h.state() != 'loader':
                print(f'cycle: attempt {attempt}: booting the loader')
                h.boot_image(os.path.join(h.OUT, 'boot-aston-xnu.img'))
                if not h.wait_loader(60):
                    print('cycle: the loader did not answer')
                    continue
                if not wait_for_phone(60):
                    print('cycle: the loader went away again')
                    time.sleep(20)
                    continue
            print(f'cycle: attempt {attempt}: the loader is up')

            if image:
                print('cycle: uploading the resident image')
                h.upload_ramdisk(os.path.join(h.OUT, 'system.apfs'))
                if not wait_for_phone(60):
                    print('cycle: the phone vanished during the upload')
                    time.sleep(20)
                    continue

            print(f'cycle: running the probe, {secs} s, cmdline="{cmdline}"')
            rc = h.run_probe(secs, cmdline)
            print(f'cycle: probe returned {rc}')
            return rc
        except SystemExit as exc:
            # The launcher exits on anything that goes wrong; one retry is cheap next to
            # getting the phone back into fastboot by hand.
            print(f'cycle: attempt {attempt} failed: {exc}')
            time.sleep(20)

    print('cycle: gave up')
    return 5


if __name__ == '__main__':
    sys.exit(main())
