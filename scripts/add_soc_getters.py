#!/usr/bin/env python3
"""Give the drivers a way to ask where the SoC's blocks are.

hakios.aston_wifi.c calls hakios_soc_rsc() / hakios_soc_cmd_db(), the getters that let a driver use
the addresses the loader passes (soc_rsc=, soc_cmd_db=) instead of another phone's hard-coded ones.
They were referenced but never written, so the kernel stopped compiling.  This adds both, plus the
prototypes.

Idempotent.
"""
import io
import os

HS = os.environ.get('HS', '/home/chenyu/hackios/hackios-os')
H = os.path.join(HS, 'xnu/files/bsd/sys/hakios.input.h')
C = os.path.join(HS, 'xnu/files/bsd/dev/hakios.input.c')

DECLS = '''/*
 * Where the SoC's blocks are, from the loader's boot arguments (soc_rsc=, soc_cmd_db=).  A driver
 * that cannot hard-code one phone's addresses asks here: 0 means "I was not told, use your own".
 */
uint32_t hakios_soc_rsc(void);
uint32_t hakios_soc_cmd_db(void);
'''

IMPL = '''
/*
 * The always-on resource controller and the command DB, as the loader told us.  Asked once and
 * remembered: these never move during a run.
 */
static uint32_t
boot_arg_address(const char *name)
{
	uint64_t value = 0;

	if (!PE_parse_boot_argn(name, &value, sizeof(value))) {
		return 0;
	}
	return (uint32_t)value;
}

uint32_t
hakios_soc_rsc(void)
{
	static uint32_t value = 0xffffffffu;

	if (value == 0xffffffffu) {
		value = boot_arg_address("soc_rsc");
	}
	return value;
}

uint32_t
hakios_soc_cmd_db(void)
{
	static uint32_t value = 0xffffffffu;

	if (value == 0xffffffffu) {
		value = boot_arg_address("soc_cmd_db");
	}
	return value;
}
'''


def add(path, anchor, text, after=True):
    s = io.open(path, encoding='utf-8').read()
    if text.strip().split('\n')[0] in s and ('hakios_soc_rsc(void)' in s) and path.endswith('.h') and s.count('hakios_soc_rsc') >= 2:
        print('  already: %s' % os.path.basename(path))
        return
    if 'hakios_soc_rsc' in s and path.endswith('.c'):
        print('  already: %s' % os.path.basename(path))
        return
    if anchor not in s:
        print('  MISS   : %s anchor' % os.path.basename(path))
        return
    s = s.replace(anchor, anchor + text, 1) if after else s.replace(anchor, text + anchor, 1)
    io.open(path, 'w', encoding='utf-8', newline='').write(s)
    print('  patched: %s' % os.path.basename(path))


# the header: after the touch-posting call the drivers already use
add(H, 'void hakios_touch_post(int type, int finger, int x, int y);\n', '\n' + DECLS, after=True)
# the .c: before hakios_input_init(), which is where every driver starts
add(C, 'void\nhakios_input_init(void)\n', IMPL + '\n', after=False)
print('done')
