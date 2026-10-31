#!/usr/bin/env python3
"""Search a binary for ASCII and UTF-16LE occurrences of the given text markers."""
import sys

path = sys.argv[1]
patterns = [p.encode() for p in sys.argv[2:]]
data = open(path, 'rb').read()
print(f'{path}: {len(data)} bytes')
for pat in patterns:
    ascii_hits = data.count(pat)
    utf16 = b''.join(bytes([b, 0]) for b in pat)
    utf16_hits = data.count(utf16)
    print(f'  {pat.decode():<28} ascii={ascii_hits:<3} utf16le={utf16_hits}')
