"""Step 14: the order lemonade uses, which is the one that actually brings a QCA6490 up.

Differences from what this file used to do, all of them things pci-msm and the board driver do:

  * PERST is held low from the power step until the moment the state machine is started.
  * The PIPE clock branch is voted *after* the PHY sequence, and the PHY status bit 6 is polled
    until it clears; the old code voted PIPE before the PHY was programmed and never waited.
  * PARF routing (device type, DBI base, SLV address space) happens before the first DBI access.
  * The link is trained at Gen1 with ASPM off, and success is read from DBI 0xf28 bit 10 and
    DBI 0x80 bit 29 instead of guessing from LTSSM numbers.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

old = '	case 12: {'
new = '''	case 14: {
		uint32_t *gcc, *parf, *phy, *tlmm, *dbi, i, v;
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
		if (gcc == NULL || parf == NULL || phy == NULL || tlmm == NULL ||
		    dbi == NULL) {
			break;
		}
		printf("wifi: 14: retaining the domain's flip-flops and holding PERST low\\n");
		*(volatile uint32_t *)((uintptr_t)gcc + 0x06b004) |= (1u << 11);
		*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) =
		    (*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) & ~0xffu) | 0x2fu;
		gpio_out(tlmm, TLMM_GPIO_PERST, 0);

		printf("wifi: 14: PARF routing before any DBI access\\n");
		*(volatile uint32_t *)((uintptr_t)parf + PARF_DEVICE_TYPE) = PARF_DEVICE_TYPE_RC;
		*(volatile uint32_t *)((uintptr_t)parf + PARF_PHY_CTRL) &= ~1u;
		*(volatile uint32_t *)((uintptr_t)parf + 0x350) = 0;
		*(volatile uint32_t *)((uintptr_t)parf + PARF_SYS_CTRL) = 0x365e;
		*(volatile uint32_t *)((uintptr_t)parf + PARF_MHI_CLOCK_RESET_CTRL) |= (1u << 4);
		*(volatile uint32_t *)((uintptr_t)parf + 0x358) = 0x4000000;
		*(volatile uint32_t *)((uintptr_t)parf + PARF_AXI_MSTR_WR_ADDR_HALT_V2) |=
		    (1u << 31);
		printf("wifi: 14: parf sys %08x halt %08x rsvd %08x\\n",
		    *(volatile uint32_t *)((uintptr_t)parf + PARF_SYS_CTRL),
		    *(volatile uint32_t *)((uintptr_t)parf + PARF_AXI_MSTR_WR_ADDR_HALT_V2),
		    *(volatile uint32_t *)((uintptr_t)parf + 0x358));

		printf("wifi: 14: replaying %u PHY writes\\n", ASTON_PHY_SEQ_LEN);
		for (i = 0; i < ASTON_PHY_SEQ_LEN; i++) {
			*(volatile uint32_t *)((uintptr_t)phy + aston_phy_seq[i].off) =
			    aston_phy_seq[i].value;
			if (aston_phy_seq[i].delay_us) {
				delay(aston_phy_seq[i].delay_us);
			}
		}
		delay(1000);

		printf("wifi: 14: voting the PIPE clock and waiting for the PHY to lock\\n");
		*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) |= (1u << 4);
		for (i = 0; i < 200; i++) {
			v = *(volatile uint32_t *)((uintptr_t)phy + 0x214);
			if ((v & (1u << 6)) == 0) {
				break;
			}
			delay(1000);
		}
		printf("wifi: 14: phy status %08x after %u ms, pipe %08x votes %08x/%08x\\n",
		    *(volatile uint32_t *)((uintptr_t)phy + 0x214), i,
		    *(volatile uint32_t *)((uintptr_t)gcc + 0x06b030),
		    *(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE),
		    *(volatile uint32_t *)((uintptr_t)gcc + 0x052000));

		printf("wifi: 14: gen1, aspm off, link control2 was %08x\\n",
		    *(volatile uint32_t *)((uintptr_t)dbi + 0xa0));
		*(volatile uint32_t *)((uintptr_t)dbi + 0xa0) =
		    (*(volatile uint32_t *)((uintptr_t)dbi + 0xa0) & ~0xfu) | 1u;
		*(volatile uint32_t *)((uintptr_t)dbi + 0x80) =
		    *(volatile uint32_t *)((uintptr_t)dbi + 0x80) & ~3u;

		printf("wifi: 14: releasing PERST and starting the state machine\\n");
		gpio_out(tlmm, TLMM_GPIO_PERST, 1);
		delay(1000);
		{
			uint32_t l = *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);

			*(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM) = l | PARF_LTSSM_EN;
		}
		for (i = 0; i < 200; i++) {
			if ((*(volatile uint32_t *)((uintptr_t)dbi + 0xf28) & (1u << 10)) &&
			    (*(volatile uint32_t *)((uintptr_t)dbi + 0x80) & (1u << 29))) {
				up = true;
				break;
			}
			delay(5000);
		}
		printf("wifi: 14 SAYS: up=%d after %u ms ltssm %08x dbi80 %08x f28 %08x\\n",
		    up, i * 5, *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
		    *(volatile uint32_t *)((uintptr_t)dbi + 0x80),
		    *(volatile uint32_t *)((uintptr_t)dbi + 0xf28));
		break;
	}
	case 12: {'''
assert old in s
s = s.replace(old, new, 1)
open(p, 'w', encoding='utf-8', newline='').write(s)
print('step 14 in place')
