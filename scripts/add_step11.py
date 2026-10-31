"""Step 11: watch the link for seconds and show the pins and the reference clock.

DETECT_ACT means the host is training and the far end is silent, so this step prints what is
readable about the three candidates: no power, no reference clock, or a module still held in
reset. It samples LTSSM over three seconds and then dumps the four pin levels, the TCSR clkref
bit, and the controller's own debug words.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

# a way to read a pin back
anchor = 'gpio_out(uint32_t *tlmm, unsigned pin, unsigned value)'
i = s.index(anchor)
after = s.index('\n}\n', i) + 3
helper = '''
static unsigned
gpio_in(uint32_t *tlmm, unsigned pin)
{
	uint32_t in = *(volatile uint32_t *)((uintptr_t)tlmm + 0x0b000u + 4u * (pin / 32));

	return (in >> (pin % 32)) & 1u;
}
'''
s = s[:after] + helper + s[after:]

# step 11
old = '''	case 10: {'''
new = '''	case 11: {
		bool up;
		uint32_t *parf, *tlmm, *tcsr, *dbi, i;
		static const uint32_t when[] = { 0, 100, 300, 600, 1000, 2000, 3000 };

		(void)step_power_on();
		(void)step_pcie_rails();
		(void)step_clkref();
		(void)step_wcn_power();
		up = step_link();
		parf = map("the PCIe controller", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
		tlmm = map("the pin controller", ASTON_TLMM, ASTON_TLMM_SIZE);
		tcsr = map("the TCSR clock controller", ASTON_TCSR, ASTON_TCSR_SIZE);
		dbi = map("the PCIe core", 0x60000000ul, 0x00010000ul);
		if (parf != NULL && tlmm != NULL && dbi != NULL) {
			for (i = 0; i < sizeof(when) / sizeof(when[0]); i++) {
				uint32_t ltssm = *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);

				printf("wifi: 11: %u ms ltssm %08x state %u dbg0 %08x\\n", when[i],
				    ltssm, ltssm & 0x3f,
				    *(volatile uint32_t *)((uintptr_t)dbi + 0x728));
				delay(2000);
			}
			printf("wifi: 11 SAYS: up=%d pins perst %u clkreq %u wlan_en %u sw %u\\n", up,
			    gpio_in(tlmm, TLMM_GPIO_PERST), gpio_in(tlmm, TLMM_GPIO_CLKREQ),
			    gpio_in(tlmm, TLMM_GPIO_WLAN_EN),
			    gpio_in(tlmm, TLMM_GPIO_WLAN_SW_CTRL));
			if (tcsr != NULL) {
				printf("wifi: 11 SAYS: clkref %08x pcie gdscr %08x status %08x\\n",
				    *(volatile uint32_t *)((uintptr_t)tcsr + TCSR_PCIE0_CLKREF_EN),
				    *(volatile uint32_t *)((uintptr_t)map("the clock controller",
				    ASTON_GCC, ASTON_GCC_SIZE) + GCC_PCIE0_GDSCR),
				    *(volatile uint32_t *)((uintptr_t)parf + PARF_STATUS));
			}
		}
		break;
	}
	case 10: {'''
assert old in s
s = s.replace(old, new, 1)
open(p, 'w', encoding='utf-8', newline='').write(s)
print('step 11 in place')
