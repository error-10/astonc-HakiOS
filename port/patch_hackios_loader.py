#!/usr/bin/env python3
"""Add the OnePlus Ace 3 (aston, SM8550) platform to hackios-os xnuloader/loader.c.

Ported from the oneplus-dodge port (devices/oneplus-dodge/patches/hakios-os.patch), trimmed:
no mpidr_map (kalama numbers its cores uniformly as core << 8), aston addresses instead of
dodge, fb_base 0xB8000000 for the platform pick.

usage: patch_hackios_loader.py PATH/TO/hackios-os/xnuloader/loader.c
"""
import sys

path = sys.argv[1]
src = open(path, encoding='utf-8').read()

# The payload lives at XNU_PAYLOAD_BASE (0xE2000000 on aston): 0xF0000000 is inside the
# Trusted VM's carve-out on this SoC, so the dodge/redwood address would be unreadable.
PAYLOAD_OLD = '#define PAYLOAD_BASE        0xF0000000ULL'
PAYLOAD_NEW = '#define PAYLOAD_BASE        0xE2000000ULL'

if PAYLOAD_OLD in src:
    src = src.replace(PAYLOAD_OLD, PAYLOAD_NEW, 1)
    print('patch: PAYLOAD_BASE 0xF0000000 -> 0xE2000000')

# A previous run leaves the loader + kernel log in the log partition and then resets; the
# kernel's own USB is gone by then, so the only way back at that log is to read the partition
# from a fresh loader. "oem readlog" stages it for `fastboot get_staged`.
READLOG_HANDLER = (
    '\t\t} else if (starts_with(cmd, "oem readlog")) {\n'
    '\t\t\t/* stage the log partition: a previous run left its loader + kernel log there */\n'
    '\t\t\tefi_block_io *bio = find_log_partition();\n'
    '\t\t\tif (bio == NULL) {\n'
    '\t\t\t\tfb_reply("FAIL", "no log partition");\n'
    '\t\t\t\treturn;\n'
    '\t\t\t}\n'
    '\t\t\tuint64_t bs = bio->media->block_size;\n'
    '\t\t\tuint64_t total = (uint64_t)(bio->media->last_block + 1) * bs;\n'
    '\t\t\tuint64_t len = total < sizeof(out_buf) ? total : sizeof(out_buf);\n'
    '\t\t\tlen = (len / bs) * bs;\n'
    '\t\t\tif (len == 0) {\n'
    '\t\t\t\tfb_reply("FAIL", "bad size");\n'
    '\t\t\t\treturn;\n'
    '\t\t\t}\n'
    '\t\t\tefi_status rs = bio->read_blocks(bio, bio->media->media_id, 0, len, out_buf);\n'
    '\t\t\tif (!EFI_ERROR(rs)) {\n'
    '\t\t\t\tflush_dcache((uint64_t)(uintptr_t)out_buf, (uint64_t)(uintptr_t)out_buf + len);\n'
    '\t\t\t\tstaged_data = out_buf;\n'
    '\t\t\t\tstaged_len = len;\n'
    '\t\t\t}\n'
    '\t\t\tfb_reply(EFI_ERROR(rs) ? "FAIL" : "OKAY", EFI_ERROR(rs) ? "read failed" : "");\n'
    '\t\t} else if (starts_with(cmd, "oem log")) {\n'
)


def add_readlog(text):
    anchor = '\t\t} else if (starts_with(cmd, "oem log")) {\n'
    if 'oem readlog' in text:
        return text, False
    if text.count(anchor) != 1:
        sys.exit(f'patch: readlog anchor found {text.count(anchor)} times, expected once')
    return text.replace(anchor, READLOG_HANDLER, 1), True


if 'platform_aston' in src:
    # Second-pass hunk: the virtual-watchdog arming was gated on redwood alone, which would
    # leave the phone's Gunyah watchdog unarmed on aston (and it bites in ~30 s). Arm it on
    # every real phone; only QEMU virt has no useful SMC target.
    wdt_old = '\tif (PLAT != &platform_redwood) {\n\t\treturn; /* SMC is not routed anywhere useful on QEMU virt */\n\t}\n'
    wdt_new = ('\tif (PLAT == &platform_qemu_virt) {\n'
               '\t\treturn; /* SMC is not routed anywhere useful on QEMU virt */\n'
               '\t}\n')
    if wdt_old in src:
        src = src.replace(wdt_old, wdt_new, 1)
        print('patch: watchdog armed on every phone (was redwood-only)')
    # Second-pass hunk: the display may sit at an offset inside Display_Reserved rather than
    # exactly at its base; pick aston for anything inside the window.
    fb_old = '\t\t} else if (SCREEN.base == 0xB8000000ULL) {\n'
    fb_new = ('\t\t} else if (SCREEN.base >= 0xB8000000ULL && SCREEN.base < 0xBAB00000ULL) {\n'
              '\t\t\t/* anywhere inside Display_Reserved: the panel may be offset from its base */\n')
    if fb_old in src:
        src = src.replace(fb_old, fb_new, 1)
        print('patch: platform_aston picked for the whole Display_Reserved window')
    # Second-pass: rewrite whatever "oem readlog" handler is present so it stages the *tail*
    # of the log partition (its head is early userland noise; the kernel prints we need are at
    # the end).  Slicing keeps this idempotent regardless of which version is already in.
    if 'oem readlog' in src:
        start = src.index('\t\t} else if (starts_with(cmd, "oem readlog")) {')
        end = src.index('\t\t} else if (starts_with(cmd, "oem log")) {', start)
        anchor = '\t\t} else if (starts_with(cmd, "oem log")) {\n'
        src = src[:start] + READLOG_HANDLER[:-len(anchor)] + src[end:]
        print('patch: oem readlog rewritten to stage the tail of the log partition')
    # Battery: the charger stack is in aston's UEFI too (ChargerExDxe, QcomChargerDxeLA), so let
    # the loader reach it on this phone and publish the cache the kernel reads.
    batt_old = '\tif (charger_enabled || PLAT != &platform_redwood) {\n'
    batt_new = '\tif (charger_enabled || (PLAT != &platform_redwood && PLAT != &platform_aston)) {\n'
    if batt_old in src:
        src = src.replace(batt_old, batt_new, 1)
        print('patch: charger polled on aston too')
    src, added = add_readlog(src)
    if added:
        print('patch: oem readlog command added')
    open(path, 'w', encoding='utf-8').write(src)
    print('patch: platform already present, payload base and watchdog touched up')
    sys.exit(0)

EDITS = []


def sub(old, new, note):
    EDITS.append((old, new, note))


# 1. struct platform: mpidr map + GIC redistributor window, and the two helpers.
sub(
    '\tuint32_t small_cores;            /* a bit for each of the slower cores, by number: "small-core" in the device tree */\n};\n',
    '\tuint32_t small_cores;            /* a bit for each of the slower cores, by number: "small-core" in the device tree */\n'
    '\tconst uint64_t *mpidr_map;       /* cores numbered by MPIDRs with no uniform shift (SM8750), NULL: core_shift */\n'
    '\tuint64_t gic_redist_size;        /* the redistributor window: cores * stride (0: the kernel\'s 0x20000) */\n'
    '};\n'
    '\n'
    '/* MPIDR of core n / the core an MPIDR belongs to, by the map when there is one. */\n'
    'static uint64_t\n'
    'core_mpidr(const struct platform *p, int n)\n'
    '{\n'
    '\treturn p->mpidr_map != NULL ? p->mpidr_map[n] : (uint64_t)n << p->core_shift;\n'
    '}\n'
    '\n'
    'static int\n'
    'mpidr_core(const struct platform *p, uint64_t mpidr)\n'
    '{\n'
    '\tif (p->mpidr_map == NULL) return (int)(mpidr >> p->core_shift);\n'
    '\tfor (int i = 0; i < p->cores; i++) if (p->mpidr_map[i] == mpidr) return i;\n'
    '\treturn -1;\n'
    '}\n',
    'struct platform fields + core_mpidr/mpidr_core helpers',
)

# 2. platform_aston right after platform_redwood.
sub(
    '\t.small_cores = 0x0f,\n};\n',
    '\t.small_cores = 0x0f,\n};\n'
    '\n'
    'static const struct platform platform_aston = {\n'
    '\t/* OnePlus Ace 3 / 12R (SM8550 "kalama"): 1x Cortex-X3, 4x Cortex-A715, 3x Cortex-A510.\n'
    '\t * MPIDRs are uniform (core << 8). The GIC redistributor stride is 0x40000, twice what\n'
    '\t * the kernel hardcodes, so the GIC walk is patched in the image below. */\n'
    '\t.name = "aston", .io_base = 0x00400000, .io_size = 0x3FC00000,\n'
    '\t.gic_dist = 0x17100000, .gic_redist = 0x17180000, .gic_redist_size = 0x200000,\n'
    '\t.uart = 0, .log_other_cpu = 1,\n'
    '\t.cores = 8, .core_shift = 8,\n'
    '\t/* cores 0-2 are the Cortex-A510s */\n'
    '\t.small_cores = 0x07,\n'
    '};\n',
    'platform_aston',
)

# 3. bootcpu= through the map helper.
sub(
    "\t\t\tkernel_mpidr = (uint64_t)(c[8] - '0') << PLAT->core_shift;",
    "\t\t\tkernel_mpidr = core_mpidr(PLAT, c[8] - '0');",
    'bootcpu= via core_mpidr',
)

# 4. GIC redistributor stride patch, in run_kernel just before the boot_args section.
sub(
    '\t/* --- boot_args ------------------------------------------------------ */\n',
    '\t/* The kernel walks the GIC redistributors in steps it hardcodes as 0x20000; on SoCs whose\n'
    '\t * stride is 0x40000 (SM8550 among them) that bus-errors before the first interrupt. Patch\n'
    '\t * the step in the image when the platform says it differs: an "add xN, xN, #stride"\n'
    '\t * (encoding the stride) feeding the next instruction\'s compare loop register. */\n'
    '\tif (PLAT->gic_redist_size != 0 && PLAT->gic_redist_size / PLAT->cores != 0x20000) {\n'
    '\t\tuint32_t stride = (uint32_t)(PLAT->gic_redist_size / PLAT->cores);\n'
    '\t\tfor (uint32_t *q = (uint32_t *)kern_lo; (uint8_t *)q + 8 <= (uint8_t *)kern_hi; q++) {\n'
    '\t\t\tuint32_t add = q[0], cmp = q[1];\n'
    '\t\t\tint add_ok = (add & 0xff000000u) == 0x91000000u && ((add >> 22) & 3) == 1 && ((add >> 10) & 0xfff) == 0x020;\n'
    '\t\t\tint cmp_ok = (cmp & 0xfffffc1fu) == 0xeb0a001fu && ((cmp >> 5) & 0x1f) == (add & 0x1f);\n'
    '\t\t\tif (add_ok && cmp_ok) {\n'
    '\t\t\t\tq[0] = (add & 0xffc003ffu) | ((uint32_t)stride >> 12) << 10;\n'
    '\t\t\t\tprint("gic walk stride patched to %x at %x\\n", (uint64_t)stride, (uint64_t)(uintptr_t)q);\n'
    '\t\t\t\tbreak;\n'
    '\t\t\t}\n'
    '\t\t}\n'
    '\t}\n'
    '\n'
    '\t/* --- boot_args ------------------------------------------------------ */\n',
    'GIC redistributor stride patch',
)

# 5. core numbering by MPIDR map in the CPU list.
sub(
    '\tint cpu_count = 1, boot_core = (int)(kernel_mpidr >> plat->core_shift);',
    '\tint cpu_count = 1, boot_core = mpidr_core(plat, kernel_mpidr);',
    'boot_core via mpidr_core',
)
sub(
    '\t\t\t\tuint64_t mpidr = (uint64_t)core << plat->core_shift;',
    '\t\t\t\tuint64_t mpidr = core_mpidr(plat, core);',
    'cpu list mpidr via core_mpidr',
)

# 6. GIC device tree node: real redistributor window size.
sub(
    '\tuint64_t gic_reg[4] = { plat->gic_dist - plat->io_base, 0x10000, plat->gic_redist - plat->io_base, 0x100000 };',
    '\tuint64_t gic_reg[4] = { plat->gic_dist - plat->io_base, 0x10000,\n'
    '\t    plat->gic_redist - plat->io_base, plat->gic_redist_size != 0 ? plat->gic_redist_size : 0x100000 };',
    'gic redist window size',
)

# 7. Platform pick: the aston display is inside Display_Reserved (0xB8000000, 0x02B00000).
sub(
    '\t\tif (SCREEN.base == 0xE1000000ULL) {\n'
    '\t\t\tPLAT = &platform_redwood;\n'
    '\t\t} else {\n'
    '\t\t\tramfb_phone_screen();\n'
    '\t\t}\n',
    '\t\tif (SCREEN.base == 0xE1000000ULL) {\n'
    '\t\t\tPLAT = &platform_redwood;\n'
    '\t\t} else if (SCREEN.base >= 0xB8000000ULL && SCREEN.base < 0xBAB00000ULL) {\n'
    '\t\t\t/* anywhere inside Display_Reserved: the panel may be offset from its base */\n'
    '\t\t\tPLAT = &platform_aston;\n'
    '\t\t} else {\n'
    '\t\t\tramfb_phone_screen();\n'
    '\t\t}\n',
    'platform_aston by fb_base',
)

# 8. Virtual watchdog: arm it on every phone, not just redwood.
sub(
    '\tif (PLAT != &platform_redwood) {\n'
    '\t\treturn; /* SMC is not routed anywhere useful on QEMU virt */\n'
    '\t}\n',
    '\tif (PLAT == &platform_qemu_virt) {\n'
    '\t\treturn; /* SMC is not routed anywhere useful on QEMU virt */\n'
    '\t}\n',
    'virtual watchdog on every phone',
)

# 9. Battery: aston's UEFI carries the Qualcomm charger drivers, so poll them here as well.
sub(
    '\tif (charger_enabled || PLAT != &platform_redwood) {\n',
    '\tif (charger_enabled || (PLAT != &platform_redwood && PLAT != &platform_aston)) {\n',
    'charger polled on aston too',
)

for old, new, note in EDITS:
    if src.count(old) != 1:
        sys.exit(f'patch: anchor for "{note}" found {src.count(old)} times, expected once')
    src = src.replace(old, new, 1)

src, added = add_readlog(src)
if added:
    print('patch: oem readlog command added')

open(path, 'w', encoding='utf-8').write(src)
print(f'patch: {len(EDITS)} hunks applied to {path}')
