#!/usr/bin/env bash
cd /home/chenyu/hackios/hackios-os/xnu-src/xnu-8796.121.2 || exit 1
echo "--- files with kprintf ring:"
grep -rln "KPRINTF_BUFFER_SIZE\|kprintf_buffer" osfmk/kern/ libkern/ 2>/dev/null | head
echo "--- buffer size:"
grep -rn "KPRINTF_BUFFER_SIZE\|BUFFER_SIZE" osfmk/kern/printf.c 2>/dev/null | head
echo "--- how the loader reads the kernel's ring (boot arg logbuf):"
cd /home/chenyu/hackios/hackios-os
grep -n "22308\|klog\|kernel_log\|return slot\|log_buf" xnuloader/loader.c | head -20
echo "--- is our driver symbol in the kernel?"
grep -c "hakios_aston_touch" xnu-src/xnu-8796.121.2/bsd/conf/files
grep -n "aston_touch" xnu-src/xnu-8796.121.2/bsd/dev/hakios.input.c
echo "--- driver kernel flag parse:"
sed -n '196,240p' xnu-src/xnu-8796.121.2/bsd/dev/hakios.aston_touch.c
