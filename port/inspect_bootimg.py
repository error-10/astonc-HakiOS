#!/usr/bin/env python3
"""Decompress the kernel blob of a boot image and look for the XNUP payload."""
import struct
import sys
import zlib

PAGE = 4096


def main(path):
    d = open(path, 'rb').read()
    print(f'{path}: {len(d)} bytes, magic={d[:8]}')
    ksize = struct.unpack_from('<I', d, 8)[0]
    off = PAGE
    print(f' kernel_size={ksize} at {off}; first bytes {d[off:off + 4].hex()}')
    blob = d[off:off + ksize]
    out = zlib.decompressobj(16 + zlib.MAX_WBITS)
    raw = out.decompress(blob) + out.flush()
    print(f' decompressed {len(raw)} bytes ({len(raw) / 1048576:.2f} MB)')
    print(f' head {raw[:16].hex()}')
    i = raw.find(b'XNUP')
    print(f' XNUP at {i}')
    if i < 0:
        return
    magic, size = struct.unpack_from('<II', raw, i)
    print(f' payload magic={magic:#010x} size={size}')
    body = raw[i + 8:i + 8 + size]          # offsets relative to the body, not to raw
    p = 0
    while p + 24 <= len(body):
        name, esize, res = struct.unpack_from('<16sII', body, p)
        name = name.split(b'\0')[0].decode('ascii', 'replace')
        if not name:
            break
        print(f'   entry {name!r} size={esize} resv={res}')
        if name in ('cmdline', 'physbase', 'rdres', 'checkpoint', 'usb'):
            print(f'     {body[p + 24:p + 24 + esize].rstrip(bytes(1)).decode("ascii", "replace")}')
        p += 24 + ((esize + 15) & ~15)     # mkpayload pads the data, not the whole record


if __name__ == '__main__':
    for f in sys.argv[1:]:
        main(f)
