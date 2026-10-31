"""Step 12: does the far end answer at all?

DETECT_ACT means the controller is probing and never sees a receiver, which is what an unpowered
or held-in-reset module looks like. The four pins involved are driven here directly, with the
function selector tried both ways (0 and 1 -- on some Qualcomm SoCs GPIO is not function 0), and
each combination gets a second of sampling.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

old = '	case 11: {'
new = '''	case 12: {
		uint32_t *parf, *tlmm;
		unsigned f, i;
		static const unsigned quad[] = { 94, 95, 96, 83 };
		static const uint32_t sample[] = { 0, 100, 200, 400, 700, 1000 };

		(void)step_power_on();
		(void)step_pcie_rails();
		(void)step_clkref();
		(void)step_wcn_power();
		parf = map("the PCIe controller", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
		tlmm = map("the pin controller", ASTON_TLMM, ASTON_TLMM_SIZE);
		if (parf == NULL || tlmm == NULL) {
			break;
		}
		for (f = 0; f < 2; f++) {
			for (i = 0; i < 4; i++) {
				uint32_t *pin = (uint32_t *)((uintptr_t)tlmm + quad[i] * 0x1000);

				*(volatile uint32_t *)(pin + 0) = f | TLMM_GPIO_CFG_DRIVE_8MA |
				    TLMM_GPIO_CFG_OUTPUT_EN;
				*(volatile uint32_t *)(pin + 1) = TLMM_GPIO_IO_OUT;
				printf("wifi: 12: func %u pin %u cfg %08x io %08x\\n", f, quad[i],
				    *(volatile uint32_t *)(pin + 0),
				    *(volatile uint32_t *)(pin + 1));
			}
			delay(50000);
			*(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM) |=
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM) | PARF_LTSSM_EN;
			printf("wifi: 12: func %u ltssm en -> %08x\\n", f,
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM));
			for (i = 0; i < sizeof(sample) / sizeof(sample[0]); i++) {
				uint32_t ltssm =
				    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);

				printf("wifi: 12: func %u t+%u ms ltssm %08x state %u\\n", f,
				    sample[i], ltssm, ltssm & 0x3f);
				delay(100000);
			}
		}
		printf("wifi: 12 SAYS: done\\n");
		break;
	}
	case 11: {'''
assert old in s
s = s.replace(old, new, 1)
open(p, 'w', encoding='utf-8', newline='').write(s)
print('step 12 in place')
