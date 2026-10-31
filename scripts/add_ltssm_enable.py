"""Set PARF_LTSSM bit 8 -- the training state machine's enable -- right after PERST# is released.

Mainline pcie-qcom.c defines LTSSM_EN as bit 8 of PARF_LTSSM and calls ltssm_enable() from
qcom_pcie_start_link() once PERST# is deasserted. We have never written that bit, which is exactly
why the register has read zero since the first probe.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

if 'PARF_LTSSM_EN' not in s:
    anchor = '#define PARF_LTSSM                      0x01b0'
    assert anchor in s, 'LTSSM define not found'
    s = s.replace(anchor, anchor + '\n#define PARF_LTSSM_EN                    (1u << 8)', 1)

old = '\tprintf("wifi: 7: phy done, releasing PERST\\n");\n\tgpio_out(tlmm, TLMM_GPIO_PERST, 1);\n'
assert old in s, 'PERST release block not found'

new = ('\tprintf("wifi: 7: phy done, releasing PERST\\n");\n'
       '\tgpio_out(tlmm, TLMM_GPIO_PERST, 1);\n'
       '\tdelay(2000);\n'
       '\n'
       '\t/* Bit 8 of PARF_LTSSM enables the training state machine. Until it is set the machine\n'
       '\t * stays in detect-quiet, which is the zero this register has read all along. */\n'
       '\t*(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM) |= PARF_LTSSM_EN;\n'
       '\tprintf("wifi: 7: ltssm enable written, register now %08x\\n",\n'
       '\t    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM));\n')
s = s.replace(old, new, 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('ltssm enable written:', s.count('ltssm enable written'), 'defs:', s.count('PARF_LTSSM_EN'))
