"""Move the step 9 additions to where the symbols they use already exist.

The first attempt inserted the new code ahead of the ASTON_* constants and of db_find, so the
compiler saw four undeclared identifiers and an implicit declaration. Put the rail table next to
wcn_rails and the function next to step_wcn_power, and declare it with the other forward
declarations.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

# 1. drop the misplaced rail table
start = s.index("/* The controller's own supplies, from the device tree's vreg-* properties. */")
end = s.index('static uint16_t\nle16(const uint8_t *p)', start)
s = s[:start] + s[end:]

# 2. drop the misplaced function
start = s.index('/* Step 9, part one: vote the controller')
end = s.index('/* Step 6: turn the PCIe0 power domain', start)
s = s[:start] + s[end:]

# 3. rail table, right after wcn_rails
anchor = '''};
'''
i = s.index('} wcn_rails[] = {')
j = s.index(anchor, i) + len(anchor)
table = '''
/* The controller's own supplies, from the device tree's vreg-* properties. */
static const struct {
	const char *name;
	uint32_t    mv;
} pcie_rails[] = {
	{ "ldoe3", 1200 },      /* vreg-1p2, pm_v6e_l3 */
	{ "ldoe1",  880 },      /* vreg-0p9, pm_v6e_l1 */
};
'''
s = s[:j] + table + s[j:]

# 4. forward declaration alongside the others
fwd_anchor = 'static bool step_wcn_power(void);'
assert fwd_anchor in s
s = s.replace(fwd_anchor, 'static bool step_pcie_rails(void);\nstatic bool step_wcn_power(void);', 1)

# 5. the function itself, just before step_wcn_power's definition
func = '''/* Step 9, part one: vote the controller's two supplies on through the same TCS path the radio
 * rails use. Nothing has ever voted these, so the PHY cannot leave reset.
 */
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

'''
anchor2 = 'static bool\nstep_wcn_power(void)\n{'
k = s.index(anchor2)
s = s[:k] + func + s[k:]

open(p, 'w', encoding='utf-8', newline='').write(s)
print('step 9 moved into place')
