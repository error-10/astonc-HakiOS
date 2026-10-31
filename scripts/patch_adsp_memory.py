#!/usr/bin/env python3
"""Point the audio DSP loader at the memory the phone actually gives it.

Measured, not guessed:

  * The firmware on this phone (`fw/ace3/files/adsp/adsp.mdt`) declares 59 segments; the loader's
    MAX_SEGMENTS was 48, so the header was rejected before anything else happened.
  * Its segment addresses run 0x9ea00000..0xa3280000.  The kernel had ADSP_MEMORY = 0x86700000,
    which the comment itself attributed to another SoC ("memory-region of qcom,lpass@3700000").
  * The real reservation, from the phone's own device tree
    (`refs/phone-fdt.dts:184`), is `adspslpi_region@9ea00000`, 0x4880000 bytes (72.5 MB).

Idempotent.
"""
import io
import os

C = os.path.join(os.environ.get('HS', '/home/chenyu/hackios/hackios-os'),
                 'xnu/files/bsd/dev/hakios.adsp.c')


def sub(s, old, new):
    if new in s:
        print('  already: %s' % old.split('\n')[0][:66])
        return s
    if old not in s:
        print('  MISS   : %s' % old.split('\n')[0][:66])
        return s
    print('  patched: %s' % old.split('\n')[0][:66])
    return s.replace(old, new, 1)


s = io.open(C, encoding='utf-8').read()

s = sub(s, '#define ADSP_MEMORY             0x86700000u     /* dt: reserved-memory adsp@86700000, memory-region of qcom,lpass@3700000 */',
        '#define ADSP_MEMORY             0x9ea00000u     /* dt: reserved-memory adspslpi_region@9ea00000, memory-region of remoteproc-adsp */')

s = sub(s, '#define ADSP_MEMORY_SIZE        0x04000000u',
        '#define ADSP_MEMORY_SIZE        0x04880000u     /* dt: adspslpi_region is 0x4880000 long */')

s = sub(s, '#define MAX_SEGMENTS            48',
        '#define MAX_SEGMENTS            64              /* the firmware here declares 59 */')

io.open(C, 'w', encoding='utf-8', newline='').write(s)
print('done')
