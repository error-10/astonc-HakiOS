"""Make step 9 short and loud.

The kernel log that comes back is only the last ten kilobytes of a boot's worth of output, so a
step that prints forty lines hides its own ending. Step 9 now does the whole bring-up once and
finishes with one line that carries the numbers worth having: both LTSSM candidates, the PARF
status, and whether the link came up.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

old_case = '''	case 9:
		(void)step_power_on();
		(void)step_pcie_rails();
		(void)step_link();
		(void)step_wcn_power();
		(void)step_link();
		break;'''
new_case = '''	case 9: {
		bool up;
		uint32_t *parf;

		(void)step_power_on();
		(void)step_pcie_rails();
		(void)step_wcn_power();
		up = step_link();
		parf = map("the PCIe controller", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
		if (parf != NULL) {
			printf("wifi: 9 SAYS: up=%d ltssm %08x/%08x status %08x\\n", up,
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
			    *(volatile uint32_t *)((uintptr_t)parf + 0x01c0),
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_STATUS));
		}
		break;
	}'''
assert old_case in s
s = s.replace(old_case, new_case, 1)

old_tl = '''		if (i == 0 || i == 5 || i == 20 || i == 100 || i == 300) {'''
new_tl = '''		if (i == 0 || i == 100) {'''
assert old_tl in s
s = s.replace(old_tl, new_tl, 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('step 9 tightened')
