#!/usr/bin/env python3
"""Create a QEMU run script for the 'our loader + prebuilt kernel + forced physbase' test."""
import sys

base = "/home/chenyu/hackios/hackios-os/"
src = base + "qemu/run-ios-aston.sh"
dst = base + "qemu/run-ios-hybrid2.sh"

s = open(src).read()
k_old = "K=xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837"
k_new = "K=prebuilt/mach.development.bcm2837"
assert k_old in s, "kernel line not found"
s = s.replace(k_old, k_new, 1)

rd_old = '--rdres "$(printf \'%x\' "$(stat -c %s "$IMG")")"'
rd_new = '--physbase 0xf4000000 --rdres "$(printf \'%x\' "$(stat -c %s "$IMG")")"'
assert rd_old in s, "rdres line not found"
s = s.replace(rd_old, rd_new, 1)

open(dst, "w").write(s)
print("wrote", dst)
