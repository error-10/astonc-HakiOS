#!/usr/bin/env bash
cd /home/chenyu/hackios/hackios-os || exit 1
echo "--- readlog in loader.c:"; grep -n 'oem readlog' xnuloader/loader.c
echo "--- loader.efi:"; ls -l xnuloader/loader.efi
echo "--- usb-payload.bin:"; ls -l xnuloader/usb-payload.bin
