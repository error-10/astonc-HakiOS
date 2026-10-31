#!/usr/bin/env python3
import io

p = '/home/chenyu/hackios/hackios-os/xnu/files/bsd/sys/hakios.input.h'
s = io.open(p, encoding='utf-8').read()

if 'hakios_soc_rsc' in s:
    print('already')
else:
    anchor = 'void hakios_input_init(void);\n'
    add = (
        '\n'
        "/* Where the SoC's blocks are, from the loader's boot arguments (soc_rsc=, soc_cmd_db=).\n"
        " * A driver that cannot hard-code one phone's addresses asks here: 0 means \"not told\". */\n"
        'uint32_t hakios_soc_rsc(void);\n'
        'uint32_t hakios_soc_cmd_db(void);\n'
    )
    assert anchor in s, 'anchor missing'
    s = s.replace(anchor, anchor + add, 1)
    io.open(p, 'w', encoding='utf-8', newline='').write(s)
    print('patched header')
