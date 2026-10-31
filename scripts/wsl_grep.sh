#!/usr/bin/env bash
cd /home/chenyu/hackios/hackios-os || exit 1
echo "--- oem log anchors:"; grep -c 'starts_with(cmd, "oem log")' xnuloader/loader.c
echo "--- helpers:"; grep -n 'find_log_partition(void)' xnuloader/loader.c
grep -n 'flush_dcache' xnuloader/loader.c | head -3
grep -n 'media->last_block' xnuloader/loader.c | head -3
grep -n 'typedef.*efi_block_io\|struct.*efi_block_io' xnuloader/efi.h | head -5
