"""Add step 9: vote the PCIe controller's own rails, then watch LTSSM over time.

The four rails voted so far belong to the radio. The controller and its PHY have their own supplies
in the device tree -- vreg-1p2 is regulator-pm-v6e-l3 (1200 mV), vreg-0p9 is regulator-pm-v6e-l1
(880 mV) -- and nothing has ever voted them on. That alone is enough for the PHY to stay in reset
and for LTSSM to read zero forever.

Step 9 runs the whole bring-up in driver order: power domains, the controller's rails, the link,
the radio's rails, and after each PERST release it samples LTSSM several times instead of once.
Two candidate LTSSM offsets are printed side by side so the wrong one cannot hide the right one.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

# 1. controller rails table
anchor = '''static uint16_t
le16(const uint8_t *p)'''
rails = '''/* The controller's own supplies, from the device tree's vreg-* properties. */
static const struct {
	const char *name;
	uint32_t    mv;
} pcie_rails[] = {
	{ "ldoe3", 1200 },      /* vreg-1p2, pm_v6e_l3 */
	{ "ldoe1",  880 },      /* vreg-0p9, pm_v6e_l1 */
};

static uint16_t
le16(const uint8_t *p)'''
assert anchor in s
s = s.replace(anchor, rails, 1)

# 2. the rail-voting step, using the same tcs_vote shape the radio step uses
anchor2 = '''/* Step 6: turn the PCIe0 power domain and its clocks on, then look at the link again.'''
early = '''/* Step 9, part one: vote the controller's two supplies on through the same TCS path. */
static bool
step_pcie_rails(void)
{
	uint32_t *rsc, *db, i, addr, rsc_base, db_base;

	printf("wifi: 9: voting the controller's own supplies\\n");
	rsc_base = hakios_soc_rsc() ? hakios_soc_rsc() : ASTON_RSC_DEFAULT;
	db_base = hakios_soc_cmd_db() ? hakios_soc_cmd_db() : ASTON_DB_DEFAULT;

	rsc = map("the always-on resource controller", rsc_base, 0x00010000ul);
	if (rsc == NULL) {
		return false;
	}
	db = map("the command DB", db_base, ASTON_DB_SIZE);
	if (db == NULL) {
		return false;
	}

	for (i = 0; i < sizeof(pcie_rails) / sizeof(pcie_rails[0]); i++) {
		uint32_t addrs[3], values[3];

		addr = db_find(db, pcie_rails[i].name);
		if (addr == 0) {
			printf("wifi: 9: %s is not in the command DB\\n", pcie_rails[i].name);
			continue;
		}
		addrs[0] = addr;
		addrs[1] = addr + 4;
		addrs[2] = addr + 8;
		values[0] = pcie_rails[i].mv;
		values[1] = 1;
		values[2] = 4;
		printf("wifi: 9: %s at %08x, %u mV, vote rc=%d\\n", pcie_rails[i].name, addr,
		    pcie_rails[i].mv, tcs_vote(rsc, addrs, values));
	}
	delay(20000);
	return true;
}

/* Step 6: turn the PCIe0 power domain and its clocks on, then look at the link again.'''
assert anchor2 in s
s = s.replace(anchor2, early, 1)

# 3. sample LTSSM over time, at both candidate offsets
old_loop = '''	for (i = 0; i < 500; i++) {
		ltssm = *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);
		if ((ltssm & 0x3f) != 0) {
			break;
		}
		delay(1000);
	}'''
new_loop = '''	for (i = 0; i < 500; i++) {
		ltssm = *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);
		if (i == 0 || i == 5 || i == 20 || i == 100 || i == 300) {
			printf("wifi: 7: ltssm %u ms: 1b0 %08x / 1c0 %08x\\n", i, ltssm,
			    *(volatile uint32_t *)((uintptr_t)parf + 0x01c0));
		}
		if ((ltssm & 0x3f) != 0) {
			break;
		}
		delay(1000);
	}'''
assert old_loop in s
s = s.replace(old_loop, new_loop, 1)

# 4. dispatch
old_case = '''	case 8:
		(void)step_power_on();
		(void)step_link();
		(void)step_wcn_power();
		(void)step_link();
		break;'''
new_case = '''	case 8:
		(void)step_power_on();
		(void)step_link();
		(void)step_wcn_power();
		(void)step_link();
		break;
	case 9:
		(void)step_power_on();
		(void)step_pcie_rails();
		(void)step_link();
		(void)step_wcn_power();
		(void)step_link();
		break;'''
assert old_case in s
s = s.replace(old_case, new_case, 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('step 9 in place')
