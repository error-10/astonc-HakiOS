#!/usr/bin/env bash
cd /home/chenyu/hackios/hackios-os
for f in qemu-hybrid qemu-pristine2 qemu-f0; do
  echo "--- $f"
  grep -n 'md0\|md1\|rootdev\|resident\|BSD root' logs/$f.log | head -10
done
