"""Add step 8 (power the radio itself) to the Wi-Fi probe.

The controller side came up in step 7 and then sat in DETECT_QUIET: it was training, but there
was nothing on the other end to train with, because the module had no power. Step 8 votes the
four PMIC rails the device tree names for it and drives wlan-en and the software control line,
then repeats the controller bring-up so the link gets a second chance at a powered endpoint.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

# 1. forward declaration
s = s.replace('static bool step_power_on(void);\nstatic bool step_link(void);',
              'static bool step_power_on(void);\nstatic bool step_link(void);\n'
              'static bool step_wcn_power(void);', 1)

# 2. the function itself, right before wifi_probe()
new_fn = r'''/* Step 8: give the radio its power. The four rails in wcn_rails are the ones the device tree
 * hangs off the cnss node, and without them the endpoint is dark no matter what the host does.
 */
static bool
step_wcn_power(void)
{
	uint32_t *rsc, *db, *tlmm, i, addr, rsc_base, db_base;
	bool voted = true;

	printf("wifi: 8: powering the radio itself\n");
	rsc_base = hakios_soc_rsc() ? hakios_soc_rsc() : ASTON_RSC_DEFAULT;
	db_base = hakios_soc_cmd_db() ? hakios_soc_cmd_db() : ASTON_DB_DEFAULT;
	printf("wifi: 8: rsc %08x, command DB %08x\n", rsc_base, db_base);

	rsc = map("the always-on resource controller", rsc_base, 0x00010000ul);
	if (rsc == NULL) {
		return false;
	}
	db = map("the command DB", db_base, ASTON_DB_SIZE);
	if (db == NULL) {
		return false;
	}
	tlmm = map("the pin controller", ASTON_TLMM, ASTON_TLMM_SIZE);
	if (tlmm == NULL) {
		return false;
	}

	for (i = 0; i < sizeof(wcn_rails) / sizeof(wcn_rails[0]); i++) {
		uint32_t addrs[3], values[3];
		int rc;

		addr = db_find(db, wcn_rails[i].name);
		if (addr == 0) {
			printf("wifi: 8: %s is not in the command DB\n", wcn_rails[i].name);
			voted = false;
			continue;
		}
		addrs[0] = addr;
		addrs[1] = addr + 4;
		addrs[2] = addr + 8;
		values[0] = wcn_rails[i].mv;
		values[1] = 1;          /* on */
		values[2] = 4;          /* mode, as the touch driver votes it */
		rc = tcs_vote(rsc, addrs, values);
		printf("wifi: 8: %s at %08x, %u mV, vote rc=%d\n", wcn_rails[i].name, addr,
		    wcn_rails[i].mv, rc);
		if (rc != 0) {
			voted = false;
		}
	}

	gpio_out(tlmm, TLMM_GPIO_WLAN_SW_CTRL, 1);
	gpio_out(tlmm, TLMM_GPIO_WLAN_EN, 1);
	printf("wifi: 8: wlan-en (gpio%u) and sw-ctrl (gpio%u) driven high\n",
	    TLMM_GPIO_WLAN_EN, TLMM_GPIO_WLAN_SW_CTRL);
	delay(50000);

	printf("wifi: 8: rails %s\n", voted ? "all voted" : "incomplete");
	return voted;
}

static void
wifi_probe(uint32_t steps)'''
anchor = 'static void\nwifi_probe(uint32_t steps)'
assert anchor in s
s = s.replace(anchor, new_fn, 1)

# 3. dispatch
old_case = '''	case 7:
		(void)step_power_on();
		(void)step_link();
		break;'''
new_case = '''	case 7:
		(void)step_power_on();
		(void)step_link();
		break;
	case 8:
		(void)step_power_on();
		(void)step_link();
		(void)step_wcn_power();
		(void)step_link();
		break;'''
assert old_case in s
s = s.replace(old_case, new_case, 1)

# 4. the pins the step needs
s = s.replace('#define TLMM_GPIO_WLAN_EN     96                /* dn: wlan-en-gpios */',
              '#define TLMM_GPIO_WLAN_EN     96                /* dn: wlan-en-gpios */\n'
              '#define TLMM_GPIO_WLAN_SW_CTRL 83               /* dn: qcom,wlan-sw-ctrl-gpio */', 1)

# 5. the doc comment at the top of the file
s = s.replace(''' *   5  reads  the clock controller's PCIe0 power domains, gate and reset lines at 0x100000
 *             and the perst / clkreq / wlan-en pins at 0xf100000: whether the controller is
 *             powered at all, which decides whether steps 1-4 could ever have said anything''',
              ''' *   5  reads  the clock controller's PCIe0 power domains, gate and reset lines at 0x100000
 *             and the perst / clkreq / wlan-en pins at 0xf100000: whether the controller is
 *             powered at all, which decides whether steps 1-4 could ever have said anything
 *   6  votes  the PCIe0 power domains on and then off the AXI halts, and sees the PARF block
 *             come alive
 *   7  writes the controller and PHY bring-up: root generators, resets, RC mode, the device
 *             tree's PHY sequence, PERST
 *   8  votes  the four PMIC rails the radio needs and drives wlan-en, then repeats step 7''', 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('step 8 added')
