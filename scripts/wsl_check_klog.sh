#!/usr/bin/env bash
cd /home/chenyu/hackios/hackios-os/xnu-src/xnu-8796.121.2 || exit 1
echo "--- kprintf buffer defines:"
grep -rn "KPRINTF\|msgbuf" osfmk/kern/kprintf.c libkern/*.c 2>/dev/null | head -20
echo "--- boot-arg for buffer size:"
grep -rn "buf_size\|BUFSIZE\|kprintf_buf" osfmk/kern/kprintf.c | head -20
echo "--- our driver print calls:"
grep -n "printf\|kprintf" bsd/dev/hakios.aston_touch.c | head -20
echo "--- driver init entry:"
grep -n "aston_touch_init\|PE_parse_boot_argn" bsd/dev/hakios.aston_touch.c | head -20
