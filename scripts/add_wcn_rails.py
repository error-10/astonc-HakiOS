"""Repair clk_root_on's opening and put the WCN power-on code in front of it.

The text editor and I got our wires crossed on the previous edit, so the brace and the local
declaration are restored here and the new code is inserted in the same pass.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

broken = ('static bool\nclk_root_on(uint32_t *gcc, const char *what, uint32_t base, uint32_t cfg)\n'
          '\n\t*(volatile uint32_t *)')
fixed = ('static bool\nclk_root_on(uint32_t *gcc, const char *what, uint32_t base, uint32_t cfg)\n'
         '{\n\tuint32_t cmd = 0, i;\n\n\t*(volatile uint32_t *)')
assert broken in s, 'the broken clk_root_on header is not there'
s = s.replace(broken, fixed, 1)

new_code = r'''
/* The radio's own supplies. They are PMIC rails voted through the apps RSC, with the same
 * three-command AMC vote the touch driver uses; the command DB keys come from the names of the
 * device tree's regulator nodes (rpmh-regulator-ldob15 -> ldo.b15, rpmh-regulator-smpe4 ->
 * smps.e4), and the voltages are the ones that tree asks for. */
#define ASTON_RSC_TCS     0x0d00u
#define ASTON_RSC_STRIDE  0x02a0u
#define ASTON_DB_SIZE     0x00100000ul

static const struct {
	const char *name;
	uint32_t    mv;
} wcn_rails[] = {
	{ "ldo.b15", 1800 },    /* vdd-wlan-io, pm_humu_l15 */
	{ "smps.e4",  966 },    /* vdd-wlan-dig, pm_v6e_s4 */
	{ "smps.g4", 1350 },    /* vdd-wlan-rfa2, pm_v6g_s4 */
	{ "smps.g6", 1900 },    /* vdd-wlan-rfa1, pm_v6g_s6 */
};

static uint16_t
le16(const uint8_t *p)
{
	return (uint16_t)(p[0] | (uint16_t)p[1] << 8);
}

static uint32_t
le32(const uint8_t *p)
{
	return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

/* Look a cmd-db key up and return the address its three commands live at, or 0. */
static uint32_t
db_find(uint32_t *db, const char *name)
{
	const uint8_t *base = (const uint8_t *)db;
	unsigned s, i, k;

	if (le32(base + 4) != 0x0c0330db) {
		return 0;
	}
	for (s = 0; s < 8; s++) {
		const uint8_t *d = base + 8 + s * 16;
		unsigned off = le16(d + 2), n = le16(d + 6);

		if (!le16(d) || !n || n > 512) {
			continue;
		}
		if (off + n * 24 + 32 > ASTON_DB_SIZE - 144) {
			continue;
		}
		for (i = 0; i < n; i++) {
			const uint8_t *e = base + 144 + off + 24 * i;
			bool same = true;

			for (k = 0; k < 8; k++) {
				if (e[k] != (uint8_t)(name[k] ? name[k] : 0)) {
					same = false;
					break;
				}
			}
			if (same) {
				return le32(e + 16);
			}
		}
	}
	return 0;
}

/* One three-command vote through an idle ACTIVE TCS slot, the format the touch driver proved. */
static int
tcs_vote(uint32_t *rsc, const uint32_t addrs[3], const uint32_t values[3])
{
	uintptr_t base = (uintptr_t)rsc + ASTON_RSC_TCS, t = 0;
	uint32_t saved[9], control, wait, mask, irq, i;
	unsigned slot, a, j;

	for (slot = 0; slot < 3; slot++) {
		uintptr_t candidate = base + slot * ASTON_RSC_STRIDE;

		if (*(volatile uint32_t *)(candidate + 0x28) &&
		    !(*(volatile uint32_t *)(candidate + 0x24) & 0x1000000) &&
		    !*(volatile uint32_t *)(candidate + 0x2c)) {
			t = candidate;
			break;
		}
	}
	if (!t) {
		return -12;
	}

	mask = 1u << slot;
	irq = *(volatile uint32_t *)base;
	control = *(volatile uint32_t *)(t + 0x24);
	wait = *(volatile uint32_t *)(t + 0x20);
	*(volatile uint32_t *)(t + 0x24) = control & ~0x10000u;
	for (a = 0; a < 3; a++) {
		for (j = 0; j < 3; j++) {
			saved[a * 3 + j] = *(volatile uint32_t *)(t + 0x34 + a * 24 + j * 4);
		}
	}
	*(volatile uint32_t *)(base + 8) = mask;
	for (a = 0; a < 3; a++) {
		*(volatile uint32_t *)(t + 0x34 + a * 24) = 0x10108;
		*(volatile uint32_t *)(t + 0x38 + a * 24) = addrs[a];
		*(volatile uint32_t *)(t + 0x3c + a * 24) = values[a];
	}
	*(volatile uint32_t *)(t + 0x20) = 7;
	*(volatile uint32_t *)(t + 0x2c) = 7;
	*(volatile uint32_t *)base = irq | mask;
	*(volatile uint32_t *)(t + 0x24) = 0x10000;
	*(volatile uint32_t *)(t + 0x24) = 0x1010000;
	for (i = 0; i < 2000 && !(*(volatile uint32_t *)(base + 4) & mask); i++) {
		delay(100);
	}
	if (i == 2000) {
		return -13;
	}
	*(volatile uint32_t *)(t + 0x24) = 0x10000;
	*(volatile uint32_t *)(t + 0x24) = 0;
	*(volatile uint32_t *)(t + 0x2c) = 0;
	*(volatile uint32_t *)(t + 0x20) = wait;
	*(volatile uint32_t *)(base + 8) = mask;
	*(volatile uint32_t *)base = irq;
	for (a = 0; a < 3; a++) {
		for (j = 0; j < 3; j++) {
			*(volatile uint32_t *)(t + 0x34 + a * 24 + j * 4) = saved[a * 3 + j];
		}
	}
	*(volatile uint32_t *)(t + 0x24) = control;
	return 0;
}

'''

anchor = 'static bool\nclk_root_on(uint32_t *gcc'
assert anchor in s
s = s.replace(anchor, new_code.lstrip('\n') + anchor, 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('restored clk_root_on and inserted rail code')
