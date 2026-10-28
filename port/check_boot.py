#!/usr/bin/env python3
"""Sanity-parse an Android boot image header (what ABL will see)."""
import struct
import sys

path = sys.argv[1]
data = open(path, 'rb').read()
magic = data[:8]
if magic != b'ANDROID!':
    sys.exit(f'{path}: bad magic {magic!r}')

kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from('<IIII', data, 8)
header_version = struct.unpack_from('<I', data, 40)[0]
page_size = struct.unpack_from('<I', data, 36)[0] if header_version < 3 else 4096
cmdline = data[44:44 + 1536].split(b'\0', 1)[0].decode(errors='replace')
print(f'file           : {path} ({len(data)} bytes)')
print(f'magic          : {magic!r}')
print(f'header_version : {header_version}')
print(f'header_size    : {header_size}')
print(f'kernel_size    : {kernel_size}')
print(f'ramdisk_size   : {ramdisk_size}')
print(f'os_version      : {os_version:#010x} -> {os_version >> 25}.{os_version >> 18 & 0x7f}.{os_version >> 11 & 0x7f}')
print(f'cmdline        : {cmdline!r}')
if header_version >= 3:
    off = 4096
    print(f'kernel offset  : {off}, dtb/compat area follows kernel+ramdisk')
    print(f'kernel head    : {data[off:off+4]!r}')
    if kernel_size + off + ramdisk_size < len(data):
        dtb_off = off + kernel_size + ramdisk_size
        dtb_off += (-dtb_off) % 4096
        tail = data[dtb_off:]
        print(f'dtb offset     : {dtb_off}, tail {len(tail)} bytes, head {tail[:8]!r}')
