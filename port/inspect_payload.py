#!/usr/bin/env python3
"""Inspect an XNUP payload container: header and each entry (name/size)."""
import struct
import sys


def main(path):
    data = open(path, 'rb').read()
    print(f'{path}: {len(data)} bytes ({len(data) / 1048576:.2f} MB)')
    magic, size = struct.unpack_from('<II', data, 0)
    print(f'  header magic={magic:#010x} expected=0x50554e58 size={size} ({size / 1048576:.2f} MB)')
    off = 8
    n = 0
    while off + 24 <= len(data):
        name, esize, res = struct.unpack_from('<16sII', data, off)
        name = name.split(b'\0')[0].decode('ascii', 'replace')
        if not name:
            break
        n += 1
        print(f'  [{n}] name={name!r} size={esize} ({esize / 1048576:.2f} MB) resv={res} data_at={off + 24}')
        off += 24 + esize
        off = (off + 15) & ~15
    print(f'  entries={n}, consumed={off} of {len(data)}')


if __name__ == '__main__':
    for p in sys.argv[1:]:
        main(p)
