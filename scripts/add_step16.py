"""Step 16: the pins the device tree actually names.

The converged node in aston.dts says:

    wlan-en-gpio  = <&tlmm 80 0>     <- this is the module's enable, and it was never driven
    bt-en-gpio    = <&tlmm 81 0>
    sw-ctrl-gpio  = <&tlmm 82 0>     (the bt-qca-converged node adds gpio 83 as wlan-sw-ctrl)

What the probe used to call WLAN_EN was gpio 96, which is the pcie node's wake-gpio -- an input.
So the radio has been sitting unpowered the whole time. This step drives 80/81/82/83 the way the
board driver does, then repeats step 14's link sequence.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

if 'step_link_pins' in s:
    print('already there')
else:
    consts = '''#define TLMM_GPIO_WLAN_EN_REAL   80            /* dn: wlan-en-gpio */
#define TLMM_GPIO_BT_EN          81            /* dn: bt-en-gpio */
#define TLMM_GPIO_SW_CTRL        82            /* dn: sw-ctrl-gpio */
'''
    anchor = '#define TLMM_GPIO_WLAN_SW_CTRL 83'
    i = s.index(anchor)
    end = s.index('\n', i) + 1
    s = s[:end] + consts + s[end:]

    fn = '''
/* Step 16: the radio's real enable pins, then step 14's sequence. */
static void
step_link_pins(void)
{
	uint32_t *gcc, *parf, *phy, *tlmm, *dbi, i, v, cfg;
	bool up = false;

	(void)step_power_on();
	(void)step_pcie_rails();
	(void)step_clkref();
	(void)step_wcn_power();
	gcc = map("the clock controller", ASTON_GCC, ASTON_GCC_SIZE);
	parf = map("the PCIe controller", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
	phy = map("the PCIe PHY", ASTON_PCIE_PHY, ASTON_PCIE_PHY_SIZE);
	tlmm = map("the pin controller", ASTON_TLMM, ASTON_TLMM_SIZE);
	dbi = map("the PCIe core", 0x60000000ul, 0x00010000ul);
	if (gcc == NULL || parf == NULL || phy == NULL || tlmm == NULL || dbi == NULL) {
		return;
	}

	printf("wifi: 16: driving the pins the device tree names (80/81/82/83)\\n");
	gpio_out(tlmm, TLMM_GPIO_WLAN_EN_REAL, 0);
	gpio_out(tlmm, TLMM_GPIO_BT_EN, 0);
	gpio_out(tlmm, TLMM_GPIO_SW_CTRL, 1);
	gpio_out(tlmm, TLMM_GPIO_WLAN_SW_CTRL, 1);
	delay(10000);
	gpio_out(tlmm, TLMM_GPIO_WLAN_EN_REAL, 1);
	delay(100000);
	printf("wifi: 16: wlan-en 80 io %08x, bt-en 81 io %08x, sw 82 io %08x, sw 83 io %08x\\n",
	    *(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_WLAN_EN_REAL * 0x1000 + 4),
	    *(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_BT_EN * 0x1000 + 4),
	    *(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_SW_CTRL * 0x1000 + 4),
	    *(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_WLAN_SW_CTRL * 0x1000 + 4));

	cfg = *(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_CLKREQ * 0x1000);
	*(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_CLKREQ * 0x1000) =
	    (cfg & ~0x3ffu) | 7u;

	*(volatile uint32_t *)((uintptr_t)gcc + 0x06b004) |= (1u << 11);
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) =
	    (*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) & ~0xffu) | 0x2fu;
	gpio_out(tlmm, TLMM_GPIO_PERST, 0);

	*(volatile uint32_t *)((uintptr_t)parf + PARF_DEVICE_TYPE) = PARF_DEVICE_TYPE_RC;
	*(volatile uint32_t *)((uintptr_t)parf + PARF_PHY_CTRL) &= ~1u;
	*(volatile uint32_t *)((uintptr_t)parf + 0x350) = 0;
	*(volatile uint32_t *)((uintptr_t)parf + PARF_SYS_CTRL) = 0x365e;
	*(volatile uint32_t *)((uintptr_t)parf + PARF_MHI_CLOCK_RESET_CTRL) |= (1u << 4);
	*(volatile uint32_t *)((uintptr_t)parf + 0x358) = 0x4000000;
	*(volatile uint32_t *)((uintptr_t)parf + PARF_AXI_MSTR_WR_ADDR_HALT_V2) |= (1u << 31);

	for (i = 0; i < ASTON_PHY_SEQ_LEN; i++) {
		*(volatile uint32_t *)((uintptr_t)phy + aston_phy_seq[i].off) =
		    aston_phy_seq[i].value;
		if (aston_phy_seq[i].delay_us) {
			delay(aston_phy_seq[i].delay_us);
		}
	}
	delay(1000);
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) |= (1u << 4);
	for (i = 0; i < 200; i++) {
		v = *(volatile uint32_t *)((uintptr_t)phy + 0x214);
		if ((v & (1u << 6)) == 0) {
			break;
		}
		delay(1000);
	}
	*(volatile uint32_t *)((uintptr_t)dbi + 0xa0) =
	    (*(volatile uint32_t *)((uintptr_t)dbi + 0xa0) & ~0xfu) | 1u;
	*(volatile uint32_t *)((uintptr_t)dbi + 0x80) =
	    *(volatile uint32_t *)((uintptr_t)dbi + 0x80) & ~3u;

	gpio_out(tlmm, TLMM_GPIO_PERST, 1);
	delay(1000);
	v = *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);
	*(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM) = v | PARF_LTSSM_EN;
	for (i = 0; i < 600; i++) {
		if ((*(volatile uint32_t *)((uintptr_t)dbi + 0xf28) & (1u << 10)) &&
		    (*(volatile uint32_t *)((uintptr_t)dbi + 0x80) & (1u << 29))) {
			up = true;
			break;
		}
		delay(5000);
	}
	printf("wifi: 16 SAYS: up=%d after %u ms ltssm %08x dbi80 %08x f28 %08x\\n",
	    up, i * 5, *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
	    *(volatile uint32_t *)((uintptr_t)dbi + 0x80),
	    *(volatile uint32_t *)((uintptr_t)dbi + 0xf28));
}

'''
    anchor2 = 'static void\nwifi_probe_only(uint32_t which)'
    j = s.index(anchor2)
    s = s[:j] + fn + s[j:]

    old = '\tcase 15:'
    new = '''\tcase 16:
\t\tstep_link_pins();
\t\tbreak;
\tcase 15:'''
    s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8', newline='').write(s)
    print('step 16 added')
