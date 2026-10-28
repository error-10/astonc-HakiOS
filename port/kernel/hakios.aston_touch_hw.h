/*
 * OnePlus Ace 3 / aston Synaptics S3910 transport.
 *
 * Ported from the proven OnePlus 13 (dodge) and Ace 5 (giulia) implementations.
 * Wiring comes from the live aston device tree
 * (kernel_platform/qcom/proprietary/devicetree/oplus/tp/aston-oplus_tp-23801.dtsi):
 *
 *   QUPV3_SE4 SPI, pins: MISO gpio44 (qup1_se4_l0), MOSI gpio45 (l1),
 *                        CLK  gpio46 (l2), CS gpio47 (l3), 6 mA, no pull
 *   irq-gpio   = <&tlmm 25 0x2008>   (active low)
 *   reset-gpio = <&tlmm 24 0x1>      (active high)
 *   avdd       = <&tlmm 10 0x1>      (enable2v8_gpio / synaptics,avdd-gpio)
 *   vdd (1.8V) = <&L4B>              (PMIC LDO, voted through the apps RSC TCS)
 *
 * The transport is a conservative bit-bang SPI (mode 0, MSB first) so that no
 * GENI firmware/clock assumptions are needed, exactly as on dodge and giulia.
 *
 * The includer provides s39_rd, s39_wr and s39_delay (microseconds).
 */
#ifndef HAKIOS_ASTON_TOUCH_HW_H
#define HAKIOS_ASTON_TOUCH_HW_H

#define S39_TLMM_PA     0x0f100000ULL   /* TLMM per-pin register bank */
/* kalama.dtsi apps_rsc@17a00000: drv-0/1/2 at 0x17a00000, 0x17a10000, 0x17a20000;
 * the RSC that carries the TCS slots we vote through is drv-2, and only that
 * 64 KB window is accessible (reads into drv-0 abort at the bus level). */
#define S39_RSC_PA      0x17a20000ULL   /* SM8550 apps rsc drv@2 */
#define S39_DB_PA       0x81c60000ULL   /* aop cmd-db */
#define S39_DB_SIZE     0x20000ULL      /* mapping size for the cmd-db */
#define S39_RSC_TCS     0x0d00ULL       /* TCS offset inside rsc */
#define S39_RSC_STRIDE  0x2a0ULL        /* TCS slot stride (672) */

#define S39_SPI_MISO    44
#define S39_SPI_MOSI    45
#define S39_SPI_CLK     46
#define S39_SPI_CS      47
#define S39_INT_PIN     25
#define S39_RST_PIN     24
#define S39_AVDD_PIN    10

#define S39_MAX 2048

struct s39_hw {
	uintptr_t gpio, rsc, db;
	uint32_t regulator, rsc_id, last_status, slot;
	unsigned mux;
	uint8_t header[4], data[S39_MAX + 3];
	unsigned length, max_x, max_y, setup_step;
};

static uintptr_t
s39_cfg(struct s39_hw *h, unsigned pin)
{
	return h->gpio + 0x1000 * pin;
}

static void
s39_set(struct s39_hw *h, unsigned pin, unsigned high)
{
	s39_wr(s39_cfg(h, pin) + 4, high ? 2 : 0);
}

static unsigned
s39_get(struct s39_hw *h, unsigned pin)
{
	return s39_rd(s39_cfg(h, pin) + 4) & 1;
}

/*
 * cfg bits: [1:0] pull, [4:2] drive strength, [8:6] mux, [9] output enable.
 * The mux value of the "gpio" function is SoC specific; the proven dodge/giulia
 * value is 2, and the caller can try 0 as a fallback (see aston_touch_init).
 */
static void
s39_pin(struct s39_hw *h, unsigned pin, unsigned output, unsigned high)
{
	if (output) s39_set(h, pin, high);
	uint32_t v = s39_rd(s39_cfg(h, pin));
	s39_wr(s39_cfg(h, pin), (v & ~0x3ffu) | (h->mux << 6) | (output << 9));
}

static uint16_t
s39_le16(const uint8_t *p)
{
	return p[0] | (uint16_t)p[1] << 8;
}

static uint32_t
s39_le32(const uint8_t *p)
{
	return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

/* cmd-db: find the LDO 1.8V regulator the device tree calls L4B. */
static uint32_t
s39_find_ldob4(struct s39_hw *h)
{
	const uint8_t *db = (const uint8_t *)h->db;
	if (s39_le32(db + 4) != 0x0c0330db) return 0;
	for (unsigned s = 0; s < 8; s++) {
		const uint8_t *d = db + 8 + s * 16;
		unsigned off = s39_le16(d + 2), n = s39_le16(d + 6);
		if (!s39_le16(d) || !n || n > 512) continue;
		if (off + n * 24 + 32 > S39_DB_SIZE - 144) continue;
		for (unsigned i = 0; i < n; i++) {
			const uint8_t *e = db + 144 + off + 24 * i;
			if (e[0] == 'l' && e[1] == 'd' && e[2] == 'o' && e[3] == 'b' &&
			    e[4] == '4' && !e[5] && !e[6] && !e[7])
				return s39_le32(e + 16);
		}
	}
	return 0;
}

/* One 3-command AMC vote through an idle ACTIVE TCS slot (proven format). */
static int
s39_tcs_vote(struct s39_hw *h, const uint32_t addrs[3], const uint32_t values[3])
{
	uintptr_t base = h->rsc + S39_RSC_TCS, t = 0;

	for (unsigned slot = 0; slot < 3; slot++) {
		uintptr_t candidate = base + slot * S39_RSC_STRIDE;
		if (s39_rd(candidate + 0x28) && !(s39_rd(candidate + 0x24) & 0x1000000) &&
		    !s39_rd(candidate + 0x2c)) {
			t = candidate;
			h->slot = slot;
			break;
		}
	}
	if (!t) return -12;

	uint32_t mask = 1u << h->slot, irq = s39_rd(base);
	uint32_t control = s39_rd(t + 0x24), wait = s39_rd(t + 0x20);
	s39_wr(t + 0x24, control & ~0x10000u);
	uint32_t saved[9];
	for (unsigned i = 0; i < 3; i++)
		for (unsigned j = 0; j < 3; j++)
			saved[i * 3 + j] = s39_rd(t + 0x34 + i * 24 + j * 4);
	s39_wr(base + 8, mask);
	for (unsigned i = 0; i < 3; i++) {
		s39_wr(t + 0x34 + i * 24, 0x10108);
		s39_wr(t + 0x38 + i * 24, addrs[i]);
		s39_wr(t + 0x3c + i * 24, values[i]);
	}
	s39_wr(t + 0x20, 7);
	s39_wr(t + 0x2c, 7);
	s39_wr(base, irq | mask);
	s39_wr(t + 0x24, 0x10000);
	s39_wr(t + 0x24, 0x1010000);
	unsigned i;
	for (i = 0; i < 2000 && !(s39_rd(base + 4) & mask); i++) s39_delay(100);
	h->last_status = s39_rd(base + 4);
	if (i == 2000) return -13;
	s39_wr(t + 0x24, 0x10000);
	s39_wr(t + 0x24, 0);
	s39_wr(t + 0x2c, 0);
	s39_wr(t + 0x20, wait);
	s39_wr(base + 8, mask);
	s39_wr(base, irq);
	for (unsigned a = 0; a < 3; a++)
		for (unsigned j = 0; j < 3; j++)
			s39_wr(t + 0x34 + a * 24 + j * 4, saved[a * 3 + j]);
	s39_wr(t + 0x24, control);
	return 0;
}

/* Vote VDD_IO (L4B, 1.8 V) on through the apps RSC. Best effort. */
static int
s39_vdd_io(struct s39_hw *h)
{
	h->regulator = s39_find_ldob4(h);
	if (!h->regulator) return -10;
	uint32_t la[3] = { h->regulator + 0, h->regulator + 4, h->regulator + 8 };
	uint32_t lv[3] = { 1800, 1, 4 };
	return s39_tcs_vote(h, la, lv);
}

/* Print the cmd-db entries whose names mention a regulator (diagnostics). */
static void
s39_cmddb_dump(struct s39_hw *h)
{
	const uint8_t *db = (const uint8_t *)h->db;
	unsigned shown = 0;

	if (s39_le32(db + 4) != 0x0c0330db) {
		printf("s3910: no cmd-db at %#lx (%#x)\n", (unsigned long)h->db, s39_le32(db + 4));
		return;
	}
	for (unsigned s = 0; s < 8 && shown < 40; s++) {
		const uint8_t *d = db + 8 + s * 16;
		unsigned off = s39_le16(d + 2), n = s39_le16(d + 6);
		if (!s39_le16(d) || !n || n > 512) continue;
		if (off + n * 24 + 32 > S39_DB_SIZE - 144) continue;
		for (unsigned i = 0; i < n && shown < 40; i++) {
			const uint8_t *e = db + 144 + off + 24 * i;
			if (e[0] < 'a' || e[0] > 'z') continue;
			char name[9];
			for (unsigned k = 0; k < 8; k++) name[k] = e[k] ? e[k] : ' ';
			name[8] = 0;
			printf("s3910: cmddb %s %08x\n", name, s39_le32(e + 16));
			shown++;
		}
	}
}

static void
s39_bus_init(struct s39_hw *h)
{
	s39_pin(h, S39_SPI_CS, 1, 1);     /* CS inactive first */
	s39_pin(h, S39_SPI_CLK, 1, 0);
	s39_pin(h, S39_SPI_MOSI, 1, 1);
	s39_pin(h, S39_SPI_MISO, 0, 0);
	s39_pin(h, S39_INT_PIN, 0, 0);
}

static void
s39_reset(struct s39_hw *h)
{
	s39_pin(h, S39_RST_PIN, 1, 0);
	s39_delay(10000);
	s39_set(h, S39_RST_PIN, 1);
	s39_delay(80000);
}

/* Mode 0, MSB first; reading clocks out 0xff, as the Linux transport does. */
static void
s39_spi(struct s39_hw *h, const uint8_t *tx, uint8_t *rx, unsigned n)
{
	s39_set(h, S39_SPI_CS, 0);
	s39_delay(2);
	for (unsigned i = 0; i < n; i++) {
		uint8_t v = tx ? tx[i] : 0xff, r = 0;
		for (unsigned b = 0; b < 8; b++) {
			s39_set(h, S39_SPI_MOSI, (v >> (7 - b)) & 1);
			s39_set(h, S39_SPI_CLK, 1);
			r = (r << 1) | s39_get(h, S39_SPI_MISO);
			s39_set(h, S39_SPI_CLK, 0);
		}
		if (rx) rx[i] = r;
	}
	s39_delay(2);
	s39_set(h, S39_SPI_CS, 1);
	s39_delay(10);
}

/* Return the report/status code, or a negative transport error. */
static int
s39_read(struct s39_hw *h)
{
	h->length = 0;
	s39_spi(h, 0, h->header, 4);
	if (h->header[0] != 0xa5) return -20;
	unsigned n = s39_le16(h->header + 2);
	if (h->header[1] == 0 || h->header[1] == 0xff) return 0;
	if (n > S39_MAX) return -21;
	if (n) {
		s39_spi(h, 0, h->data, n + 3);
		if (h->data[0] != 0xa5 || h->data[1] != 3 || h->data[n + 2] != 0x5a) return -22;
		for (unsigned i = 0; i < n; i++) h->data[i] = h->data[i + 2];
	}
	h->length = n;
	return h->header[1];
}

static int
s39_command(struct s39_hw *h, uint8_t cmd, const uint8_t *p, unsigned n)
{
	uint8_t out[259];

	if (n > 256) return -23;
	out[0] = cmd;
	out[1] = n;
	out[2] = n >> 8;
	for (unsigned i = 0; i < n; i++) out[i + 3] = p[i];
	s39_spi(h, out, 0, n + 3);
	for (unsigned i = 0; i < 100; i++) {
		s39_delay(2000);
		if (s39_get(h, S39_INT_PIN)) continue;
		int r = s39_read(h);
		if (r < 0 || (r > 0 && r < 0x10)) return r;
	}
	return -24;
}

/* Configure a compact volatile report: count, then {index:4,class:4,x:16,y:16}. */
static const uint8_t s39_report_config[] = { 0x18, 8, 1, 6, 4, 7, 4, 8, 16, 9, 16, 3, 0 };

static int
s39_start_reports(struct s39_hw *h)
{
	uint8_t p[256] = { 0 };
	int r;

	h->setup_step = 1;
	if ((r = s39_command(h, 0x20, 0, 0)) != 1) return r;
	if (h->length < 40 || s39_le16(h->data + 2)) return -30;
	h->max_x = s39_le16(h->data + 32);
	h->max_y = s39_le16(h->data + 34);
	unsigned size = s39_le16(h->data + 12);
	if (!h->max_x || !h->max_y || size < sizeof(s39_report_config) || size > sizeof(p)) return -31;

	h->setup_step = 2;
	p[0] = 0x23;
	if ((r = s39_command(h, 6, p, 1)) != 1) return r;      /* stop HBP frames */
	h->setup_step = 3;
	p[0] = 0x11; p[1] = 2; p[2] = 0;
	if ((r = s39_command(h, 0x24, p, 3)) != 1) return r;   /* LBP */
	h->setup_step = 4;
	p[0] = 9; p[1] = 0;
	if ((r = s39_command(h, 0x24, p, 3)) != 1) return r;   /* normal sensing */
	h->setup_step = 5;
	for (unsigned i = 0; i < size; i++)
		p[i] = i < sizeof(s39_report_config) ? s39_report_config[i] : 0;
	if ((r = s39_command(h, 0x26, p, size)) != 1) return r;
	h->setup_step = 6;
	if ((r = s39_command(h, 0x25, 0, 0)) != 1) return r;
	if (h->length < sizeof(s39_report_config)) return -32;
	for (unsigned i = 0; i < sizeof(s39_report_config); i++)
		if (h->data[i] != s39_report_config[i]) return -32;
	h->setup_step = 7;
	p[0] = 0x11;
	if ((r = s39_command(h, 5, p, 1)) != 1) return r;      /* enable reports */
	h->setup_step = 8;
	return 0;
}

#endif /* HAKIOS_ASTON_TOUCH_HW_H */
