#!/usr/bin/env bash
cd /home/chenyu/hackios/hackios-os
for f in qemu-hybrid3 qemu-own3; do
  echo "--- $f  (lines: $(wc -l < logs/$f.log))"
  head -5 logs/$f.log
  grep -n 'largest free block\|resident image at pa\|Darwin Kernel Version\|launchd.ios\|SpringBoard\|panic(' logs/$f.log | head -12
done
