"""Step 15: the same bring-up as 14, with the two pin details lemonade gets right.

  * CLKREQ is an input to the controller, not a GPIO we drive: it is left in its alternate
    function (1) with a pull-up, so the controller actually sees a clock request. Driving it
    as a plain GPIO high tells the PHY nobody wants a clock.
  * WLAN_EN is cycled low then high with the pause the board driver asks for, instead of being
    raised once during the power step.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

if 'step_link_alt' in s:
    print('already there')
else:
    fn = '''
/* Step 15's body: step 14's order with CLKREQ left as an input and WLAN_EN cycled. */
static void
step_link_alt(void)
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

	/* WLAN_EN: low, pause, high, pause -- what the board driver does after the rails are up. */
	gpio_out(tlmm, TLMM_GPIO_WLAN_EN, 0);
	delay(10000);
	gpio_out(tlmm, TLMM_GPIO_WLAN_EN, 1);
	delay(50000);
	/* CLKREQ: alternate function 1, pull-up, 2 mA input. */
	cfg = *(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_CLKREQ * 0x1000);
	*(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_CLKREQ * 0x1000) =
	    (cfg & ~0x3ffu) | 7u;
	printf("wifi: 15: clkreq cfg was %08x now %08x, wlan-en io %08x\\n", cfg,
	    *(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_CLKREQ * 0x1000),
	    *(volatile uint32_t *)((uintptr_t)tlmm + TLMM_GPIO_WLAN_EN * 0x1000 + 4));

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
	for (i = 0; i < 400; i++) {
		if ((*(volatile uint32_t *)((uintptr_t)dbi + 0xf28) & (1u << 10)) &&
		    (*(volatile uint32_t *)((uintptr_t)dbi + 0x80) & (1u << 29))) {
			up = true;
			break;
		}
		delay(5000);
	}
	printf("wifi: 15 SAYS: up=%d after %u ms ltssm %08x dbi80 %08x f28 %08x phy %08x\\n",
	    up, i * 5, *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
	    *(volatile uint32_t *)((uintptr_t)dbi + 0x80),
	    *(volatile uint32_t *)((uintptr_t)dbi + 0xf28),
	    *(volatile uint32_t *)((uintptr_t)phy + 0x214));
}

'''
    anchor = 'static void\nwifi_probe_only(uint32_t which)'
    i = s.index(anchor)
    s = s[:i] + fn + s[i:]

    old = '\tcase 14: {'
    new = '''\tcase 15:
\t\tstep_link_alt();
\t\tbreak;
\tcase 14: {'''
    s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8', newline='').write(s)
    print('step 15 added')
