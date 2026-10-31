"""Add step 10: enable the PCIe reference clock buffer, then bring the link up.

The device tree hangs `pcie_clkref_en` off the TCSR clock controller (clock-controller@1fc0000),
and the mainline tcsrcc-sm8550 driver implements it as a branch at 0x15100 bit 0. Nothing has
touched that bit, so the module at the other end of the link has no reference clock at all --
which is reason enough for the host to sit in detect-quiet.

Step 10 sets it, then runs the full bring-up and prints one summary line.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

# constants
anchor = '#define ASTON_TLMM            0x0f100000ul      /* dt: pinctrl@f100000 */'
const = '''#define ASTON_TCSR            0x01fc0000ul      /* dt: clock-controller@1fc0000 */
#define ASTON_TCSR_SIZE       0x00030000ul
#define TCSR_PCIE0_CLKREF_EN  0x00015100ul      /* tcsrcc-sm8550: branch, bit 0 */

#define ASTON_TLMM            0x0f100000ul      /* dt: pinctrl@f100000 */'''
assert anchor in s
s = s.replace(anchor, const, 1)

# function, placed next to step_pcie_rails
anchor2 = 'static bool\nstep_wcn_power(void)\n{'
func = '''/* Step 10, part one: flip on the reference clock buffer that feeds the module. */
static bool
step_clkref(void)
{
	uint32_t *tcsr, before;

	tcsr = map("the TCSR clock controller", ASTON_TCSR, ASTON_TCSR_SIZE);
	if (tcsr == NULL) {
		return false;
	}
	before = *(volatile uint32_t *)((uintptr_t)tcsr + TCSR_PCIE0_CLKREF_EN);
	*(volatile uint32_t *)((uintptr_t)tcsr + TCSR_PCIE0_CLKREF_EN) = before | 1u;
	printf("wifi: 10: pcie0 clkref was %08x, now %08x\\n", before,
	    *(volatile uint32_t *)((uintptr_t)tcsr + TCSR_PCIE0_CLKREF_EN));
	delay(2000);
	return true;
}

static bool
step_wcn_power(void)
{'''
assert anchor2 in s
s = s.replace(anchor2, func, 1)
s = s.replace('static bool step_pcie_rails(void);',
              'static bool step_pcie_rails(void);\nstatic bool step_clkref(void);', 1)

# dispatch: step 10 = rails, clkref, link, summary with DBI debug words
old_case = '''	case 9: {'''
new_case = '''	case 10: {
		bool up;
		uint32_t *parf, *dbi;

		(void)step_power_on();
		(void)step_pcie_rails();
		(void)step_clkref();
		(void)step_wcn_power();
		up = step_link();
		parf = map("the PCIe controller", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
		dbi = map("the PCIe core", 0x60000000ul, 0x00010000ul);
		if (parf != NULL && dbi != NULL) {
			printf("wifi: 10 SAYS: up=%d ltssm %08x/%08x status %08x\\n", up,
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
			    *(volatile uint32_t *)((uintptr_t)parf + 0x01c0),
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_STATUS));
			printf("wifi: 10 SAYS: dbi id %08x link ctrl %08x debug0 %08x debug1 %08x\\n",
			    *(volatile uint32_t *)((uintptr_t)dbi + 0x000),
			    *(volatile uint32_t *)((uintptr_t)dbi + 0x710),
			    *(volatile uint32_t *)((uintptr_t)dbi + 0x728),
			    *(volatile uint32_t *)((uintptr_t)dbi + 0x72c));
		}
		break;
	}
	case 9: {'''
assert old_case in s
s = s.replace(old_case, new_case, 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('step 10 added')
