/*
 * The GPU of the OnePlus Ace 3, an Adreno 740, looked at -- read only.
 *
 * The driver in hakios.adreno.c is for the POCO X5 Pro's Adreno 642L: every address in it
 * belongs to that phone. This file is the same idea, started again for this one, and it stops
 * before it writes anything. The question it answers first is not "how fast is the GPU" but
 * "may a kernel under Qualcomm's hypervisor even read the GPU's registers", and that answer
 * decides whether the rest is work or a dead end.
 *
 * Boot-arg a740=N performs steps 1 to N and stops:
 *
 *   1  reads  the GPU's clock controller at 0x3d90000 -- where the boot loader left it
 *   2  reads  the GPU's own registers at 0x3d00000: the revision, the status word that says
 *             whether the core is idle or hung, and the interrupt status
 *   3  reads  the SMMU in front of the GPU at 0x3da0000: its ID registers, which say which
 *             implementation of the SMMU it is and what it can do
 *   4  reads  the boot loader's list of RPMh resources (cmd-db) for the names of the rails the
 *             GPU's power is voted on: gfx, cx, mx
 *
 * An access the hypervisor does not like does not answer: it ends the run at once, or a quarter
 * of a minute later. So a step says what it is about to touch before it touches it, and a step
 * that reads nothing sensible stops the sequence instead of going on.
 */

#include <kern/clock.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <mach/vm_param.h>
#include <pexpert/pexpert.h>
#include <sys/hakios.input.h>
#include <sys/systm.h>
#include <vm/vm_kern.h>

extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);
extern vm_offset_t ml_io_map_wcomb(vm_offset_t phys_addr, vm_size_t size);

/* Where this phone's peripherals begin, as the loader's "arm-io" node says. */
#define ASTON_SOC_BASE       0x00400000ul

#define ASTON_GPU_REGS       0x03d00000ul      /* "kgsl_3d0_reg_memory" in the phone's device tree */
#define ASTON_GPU_REGS_SIZE  0x00040000ul
#define ASTON_GPU_RSCC       0x03d50000ul      /* "rscc" */
#define ASTON_GPU_RSCC_SIZE  0x00010000ul
#define ASTON_GPU_CC         0x03d90000ul      /* the GPU's own clock controller, "gpucc" */
#define ASTON_GPU_CC_SIZE    0x00009000ul
#define ASTON_GPU_SMMU       0x03da0000ul      /* "kgsl-smmu" */
#define ASTON_GPU_SMMU_SIZE  0x00040000ul

#define ASTON_CMD_DB         0x081c60000ul     /* the boot loader's list of RPMh resources */
#define ASTON_CMD_DB_SIZE    0x00020000ul
#define ASTON_RSC            0x17a20000ul      /* apps rsc drv@2: where the TCS slots live */

/*
 * Where the GPU's clock controller keeps the registers that matter, from the upstream driver
 * for this very SoC (drivers/clk/qcom/gpucc-sm8550.c). The block's own base is 0x3d90000 and
 * these are byte offsets into it -- the 0x9xxx range, not the 0x0000 the PLLs sit at.
 */
#define GPUCC_PLL0            0x0000
#define GPUCC_PLL1            0x1000
#define GPUCC_CX_GDSCR        0x9108          /* gpu_cc_cx_gdsc */
#define GPUCC_CX_GDS_HW_CTRL  0x953c
#define GPUCC_GX_GDSCR        0x905c          /* gpu_cc_gx_gdsc */
#define GPUCC_GX_CLAMP_IO     0x9504
#define GPUCC_CX_BCR          0x9104          /* gpu_cc_cx_bcr */
#define GPUCC_AHB_CBCR        0x911c          /* gpu_cc_ahb_clk */
#define GPUCC_CRC_AHB_CBCR    0x9120          /* gpu_cc_crc_ahb_clk */
#define GPUCC_CX_GMU_CBCR     0x913c          /* gpu_cc_cx_gmu_clk */
#define GPUCC_CXO_CBCR        0x9144          /* gpu_cc_cxo_clk */
#define GPUCC_HUB_CX_INT_CBCR 0x9148
#define GPUCC_MEMNOC_GFX_CBCR 0x9150
#define GPUCC_MND1X_0_CBCR    0x9288
#define GPUCC_MND1X_1_CBCR    0x928c
#define GPUCC_GMU_BCR         0x9314

/* The bits of a power domain control register and of the status register beside it. */
#define GDSC_SW_COLLAPSE      (1u << 0)
#define GDSC_HW_CONTROL       (1u << 1)
#define GDSC_SW_OVERRIDE      (1u << 2)
#define GDSC_PWR_ON           (1u << 31)      /* the control register's own "I am on" bit */
#define GDSC_STATUS_UP        (1u << 16)      /* the status register's "power up complete" */

#define RSC_TCS_OFFSET        0x0d00
#define RSC_TCS_STRIDE        0x2a0

/* Dword offsets in the GPU's register block (mesa's a6xx.xml, A7XX variants). */
#define A740_RBBM_HW_VERSION       0x00000
#define A740_RBBM_INT_0_MASK       0x00038
#define A740_RBBM_INT_0_STATUS     0x00201
#define A740_RBBM_STATUS           0x00210
#define A740_RBBM_STATUS3          0x00213
#define A740_RBBM_SECVID_TRUST_CNTL 0x0f400

#define R(name, off) { name, off }

struct reg_name {
	const char *name;
	uint32_t    off;
};

static uint32_t *g_cc;          /* the clock controller, mapped once, in bytes */
static uint32_t *g_rsc;
static bool g_power;            /* a740_power=1: step 5 may write to the hardware */

static struct reg_name gpu_regs[] = {
	R("RBBM_HW_VERSION", A740_RBBM_HW_VERSION),
	R("RBBM_INT_0_STATUS", A740_RBBM_INT_0_STATUS),
	R("RBBM_STATUS", A740_RBBM_STATUS),
	R("RBBM_STATUS3", A740_RBBM_STATUS3),
	R("RBBM_SECVID_TRUST_CNTL", A740_RBBM_SECVID_TRUST_CNTL),
};

static struct reg_name cc_regs[] = {
	R("cc+0x0000", 0x0000), R("cc+0x0004", 0x0001), R("cc+0x0008", 0x0002), R("cc+0x000c", 0x0003),
	R("cc+0x1000", 0x0400), R("cc+0x1004", 0x0401), R("cc+0x1008", 0x0402), R("cc+0x100c", 0x0403),
};

static struct reg_name smmu_regs[] = {
	R("SMMU_IDR0", 0x0000), R("SMMU_IDR1", 0x0001), R("SMMU_IDR2", 0x0002), R("SMMU_IDR3", 0x0003),
	R("SMMU_IDR5", 0x0005), R("SMMU_IDR7", 0x0007),
	R("SMMU_SID0", 0x0800), R("SMMU_SID1", 0x0801),
};

static bool
is_the_phone(void)
{
	extern vm_offset_t pe_arm_get_soc_base_phys(void);

	if (pe_arm_get_soc_base_phys() != ASTON_SOC_BASE) {
		printf("a740: not this phone (the loader did not say aston): nothing is read\n");
		return false;
	}
	return true;
}

static uint32_t *
map(const char *what, uint64_t phys, uint64_t size)
{
	uint32_t *base = (uint32_t *)(uintptr_t)ml_io_map(phys, size);

	if (base == NULL) {
		printf("a740: cannot map %s at 0x%llx\n", what, phys);
	}
	return base;
}

static void
dump(const char *what, uint32_t *base, struct reg_name *regs, unsigned count)
{
	if (regs == NULL || count == 0) {
		return;
	}
	printf("a740: %s:\n", what);
	for (unsigned i = 0; i < count; i++) {
		/*
		 * The name goes out before the read, not with the value. An access the hypervisor
		 * does not allow never comes back, so the last line on the screen names the register
		 * that ended the run -- which is the whole point of reading these blocks one at a
		 * time.
		 */
		printf("a740:   %-22s ", regs[i].name);
		printf("%08x\n", base[regs[i].off]);
	}
}

/* Step 1: the GPU's clock controller, as the boot loader left it. */
static bool
step_clocks(void)
{
	uint32_t *cc;
	unsigned live = 0;

	printf("a740: 1: reading the GPU's clock controller at 0x%x\n", ASTON_GPU_CC);
	cc = map("the GPU's clock controller", ASTON_GPU_CC, ASTON_GPU_CC_SIZE);
	if (cc == NULL) {
		return false;
	}
	g_cc = cc;
	dump("clock controller", cc, cc_regs, sizeof(cc_regs) / sizeof(cc_regs[0]));
	/*
	 * Then one word every 0x100 bytes, up to 0x3fff. Not the whole block: the last run walked
	 * it word by word and died at 0x4000 with an external abort (esr 0x96000010, the fault
	 * address exactly one 16K page past the start of the mapping), so the first 16K answers and
	 * the page after it does not. Staying below 0x4000 keeps this step safe and still shows
	 * which parts of the block carry values.
	 */
	printf("a740: 1: a word every 0x100 bytes, as far as this block answers:\n");
	for (unsigned off = 0; off < 0x4000; off += 0x100) {
		uint32_t value;

		printf("a740:   cc+0x%04x              ", off);
		value = *(volatile uint32_t *)((uintptr_t)cc + off);
		printf("%08x\n", value);
		if (value != 0 && value != 0xffffffff) {
			live++;
		}
	}
	printf("a740: 1: %u of those 64 words read back as something (a dead block reads all 0 or all f)\n", live);
	if (live == 0) {
		printf("a740: 1: the clock controller reads nothing at all: stopping here\n");
		return false;
	}
	return true;
}

/* Step 2: the GPU's own registers. */
static bool
step_core(void)
{
	uint32_t *gpu;
	uint32_t version;

	printf("a740: 2: reading the GPU's registers at 0x%x\n", ASTON_GPU_REGS);
	gpu = map("the GPU's registers", ASTON_GPU_REGS, ASTON_GPU_REGS_SIZE);
	if (gpu == NULL) {
		return false;
	}
	dump("3D core", gpu, gpu_regs, sizeof(gpu_regs) / sizeof(gpu_regs[0]));

	version = gpu[A740_RBBM_HW_VERSION];
	printf("a740: 2: RBBM_HW_VERSION %08x -- the device tree says this is an Adreno 740 (0x43050a01)\n", version);
	if (version == 0xffffffff) {
		printf("a740: 2: the GPU does not answer: stopping here\n");
		return false;
	}
	return true;
}

/* Step 3: the SMMU in front of the GPU. */
static bool
step_smmu(void)
{
	uint32_t *smmu;

	printf("a740: 3: reading the GPU's SMMU at 0x%x\n", ASTON_GPU_SMMU);
	smmu = map("the GPU's SMMU", ASTON_GPU_SMMU, ASTON_GPU_SMMU_SIZE);
	if (smmu == NULL) {
		return false;
	}
	dump("SMMU", smmu, smmu_regs, sizeof(smmu_regs) / sizeof(smmu_regs[0]));
	if (smmu[0] == 0xffffffff || smmu[0] == 0) {
		printf("a740: 3: the SMMU reads nothing sensible: stopping here\n");
		return false;
	}
	return true;
}

/*
 * Step 4: the names the GPU's rails are voted on. The boot loader keeps them in a table in
 * memory (cmd-db): a header, then entries of a name and two addresses. Printing the names that
 * mention the GPU is enough to know whether this phone calls them gfx, cx and mx.
 */
static bool
step_rails(void)
{
	uint8_t *db;
	unsigned found = 0;

	printf("a740: 4: looking for the GPU's rails in the boot loader's resource list at 0x%x\n", ASTON_CMD_DB);
	db = (uint8_t *)(uintptr_t)ml_io_map_wcomb(ASTON_CMD_DB, ASTON_CMD_DB_SIZE);
	if (db == NULL) {
		printf("a740: 4: cannot map the resource list\n");
		return false;
	}
	/* The entries are ASCII names ending in ".lvl"; the GPU's are "gfx", "cx" and "mx". */
	for (unsigned i = 0; i + 3 < ASTON_CMD_DB_SIZE; i++) {
		if (db[i] >= 'a' && db[i] <= 'z' && db[i + 1] == '.' && db[i + 2] == 'l' && db[i + 3] == 'v') {
			char name[16];
			unsigned n = 0;

			while (i >= n && n < sizeof(name) - 1 && db[i - n] >= 'a' && db[i - n] <= 'z') {
				n++;
			}
			if (n == 0 || n >= sizeof(name)) {
				continue;
			}
			for (unsigned k = 0; k < n; k++) {
				name[k] = (char)db[i - n + 1 + k];
			}
			name[n] = 0;
			if (strncmp(name, "gfx", 3) == 0 || strncmp(name, "cx", 2) == 0 || strncmp(name, "mx", 2) == 0) {
				printf("a740: 4:   %s.lvl at 0x%x\n", name, i - n + 1);
				found++;
			}
		}
	}
	printf("a740: 4: %u of the GPU's rails named\n", found);
	return true;
}

/*
 * Step 5: the same registers, but this time asking the hardware to bring the GPU's power
 * domains up instead of only reading them. Nothing here is needed to read the two blocks the
 * earlier steps read; it is needed for the GPU's own registers, which answer all zeros while
 * the graphics core has no power.
 *
 * The order is the one the vendor driver uses: rail votes first, then the buses into the block,
 * then the CX domain (the GPU's "outside": buses, GMU, SMMU), then the GX domain (the core).
 * A domain is on when its control register reports the hardware has finished, and each write is
 * read back so a domain that refuses to come up says so instead of being walked over.
 */
static uint16_t
le16(const uint8_t *p)
{
	return (uint16_t)(p[0] | (uint16_t)p[1] << 8);
}

static uint32_t
le32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t
cc_rd(unsigned off)
{
	return *(volatile uint32_t *)((uintptr_t)g_cc + off);
}

static void
cc_wr(unsigned off, uint32_t value)
{
	*(volatile uint32_t *)((uintptr_t)g_cc + off) = value;
	__asm__ volatile("dsb sy" ::: "memory");
}

static uint32_t
rsc_rd(uintptr_t a)
{
	return *(volatile uint32_t *)a;
}

static void
rsc_wr(uintptr_t a, uint32_t v)
{
	*(volatile uint32_t *)a = v;
	__asm__ volatile("dsb sy" ::: "memory");
}

/* One 3-command vote through an idle ACTIVE TCS slot, the same format the touch driver uses. */
static int
rsc_vote(const uint32_t addrs[3], const uint32_t values[3])
{
	uintptr_t base = (uintptr_t)g_rsc + RSC_TCS_OFFSET, t = 0, saved[9], control, wait;
	uint32_t mask, irq;
	unsigned i, j;

	for (unsigned slot = 0; slot < 3; slot++) {
		uintptr_t candidate = base + slot * RSC_TCS_STRIDE;

		if (rsc_rd(candidate + 0x28) && !(rsc_rd(candidate + 0x24) & 0x1000000) &&
		    !rsc_rd(candidate + 0x2c)) {
			t = candidate;
			mask = 1u << slot;
			break;
		}
	}
	if (!t) {
		return -12;
	}
	irq = rsc_rd(base);
	control = rsc_rd(t + 0x24);
	wait = rsc_rd(t + 0x20);
	rsc_wr(t + 0x24, control & ~0x10000u);
	for (i = 0; i < 3; i++) {
		for (j = 0; j < 3; j++) {
			saved[i * 3 + j] = rsc_rd(t + 0x34 + i * 24 + j * 4);
		}
	}
	rsc_wr(base + 8, mask);
	for (i = 0; i < 3; i++) {
		rsc_wr(t + 0x34 + i * 24, 0x10108);
		rsc_wr(t + 0x38 + i * 24, addrs[i]);
		rsc_wr(t + 0x3c + i * 24, values[i]);
	}
	rsc_wr(t + 0x20, 7);
	rsc_wr(t + 0x2c, 7);
	rsc_wr(base, irq | mask);
	rsc_wr(t + 0x24, 0x10000);
	rsc_wr(t + 0x24, 0x1010000);
	for (i = 0; i < 2000 && !(rsc_rd(base + 4) & mask); i++) {
		delay_for_interval(100, NSEC_PER_USEC);
	}
	rsc_wr(t + 0x24, 0x10000);
	rsc_wr(t + 0x24, 0);
	rsc_wr(t + 0x2c, 0);
	rsc_wr(t + 0x20, wait);
	rsc_wr(base + 8, mask);
	rsc_wr(base, irq);
	for (i = 0; i < 3; i++) {
		for (j = 0; j < 3; j++) {
			rsc_wr(t + 0x34 + i * 24 + j * 4, (uint32_t)saved[i * 3 + j]);
		}
	}
	rsc_wr(t + 0x24, control);
	return i == 2000 ? -13 : 0;
}

/* The address the resource list gives a rail's name, or 0. */
static uint32_t
rail_address(const char *want)
{
	uint8_t *db = (uint8_t *)(uintptr_t)ml_io_map_wcomb(ASTON_CMD_DB, ASTON_CMD_DB_SIZE);
	unsigned want_len = 0;

	if (db == NULL) {
		return 0;
	}
	if (le32(db + 4) != 0x0c0330db) {
		printf("a740: 5: the resource list has no header (%08x)\n", le32(db + 4));
		return 0;
	}
	while (want[want_len]) {
		want_len++;
	}
	/*
	 * The list is a small header and eight sections; a section says where its entries start
	 * and how many there are, and each entry is 24 bytes with a 16 byte name and the address
	 * at +16. This is the layout the touch driver's regulator lookup uses, which works.
	 */
	for (unsigned s = 0; s < 8; s++) {
		uint8_t *section = db + 8 + s * 16;
		unsigned off = le16(section + 2), n = le16(section + 6);

		if (!le16(section) || !n || n > 512) {
			continue;
		}
		if (off + n * 24 + 32 > ASTON_CMD_DB_SIZE - 144) {
			continue;
		}
		for (unsigned i = 0; i < n; i++) {
			uint8_t *e = db + 144 + off + 24 * i;
			unsigned k;

			for (k = 0; k < want_len; k++) {
				if (e[k] != (uint8_t)want[k] || !e[k]) {
					break;
				}
			}
			if (k == want_len && (want_len == 16 || e[k] == 0)) {
				return le32(e + 16);
			}
		}
	}
	return 0;
}

/*
 * Turn one power domain on and report what the hardware says about it.
 *
 * The status of a domain is not in the control register. On these SoCs each domain reports
 * through a separate status register -- the little hardware sequencer at gds_hw_ctrl, or the
 * configuration copy at gdscr + 4 -- and it says "up" by setting bit 16 there. The control
 * register keeps bit 0 (collapse) and bit 2 (software override) as its inputs, so reading bit
 * 16 of it tells you nothing; the last run read that bit, saw it clear, and called a domain
 * that had come up "off".
 *
 * Returns whether the status register agreed, but the caller carries on either way: the GPU's
 * own registers are the real answer and they are one line further down.
 */
static bool
gdsc_on(const char *what, unsigned gdscr, unsigned status_reg, unsigned clamp_reg)
{
	uint32_t value, status = 0;

	value = cc_rd(gdscr);
	printf("a740: 5: %s: control %08x  status %08x\n", what, value, cc_rd(status_reg));
	if (clamp_reg != 0) {
		uint32_t clamp = cc_rd(clamp_reg);

		cc_wr(clamp_reg, clamp & ~1u);
		printf("a740: 5: %s: clamp %08x -> %08x\n", what, clamp, cc_rd(clamp_reg));
	}
	/* Clear "collapse" and take the domain into software control (Linux's gdsc_enable). */
	cc_wr(gdscr, (value & ~GDSC_SW_COLLAPSE) | GDSC_SW_OVERRIDE);
	printf("a740: 5: %s: control now %08x\n", what, cc_rd(gdscr));
	/*
	 * "Is it up?" is bit 31 of the control register, or bit 31 of the register the hardware
	 * sequencer reports through -- exactly what the vendor's gdsc-regulator and this project's
	 * own working Adreno driver test. Bit 16 belongs to the wait-count fields; polling it says
	 * "off" about a domain that came up, which is what the last two runs did.
	 */
	for (unsigned i = 0; i < 400; i++) {
		status = cc_rd(status_reg);
		if ((cc_rd(gdscr) | status) & GDSC_PWR_ON) {
			printf("a740: 5: %s is up (control %08x, status %08x)\n", what,
			    cc_rd(gdscr), status);
			return true;
		}
		delay_for_interval(100, NSEC_PER_USEC);
	}
	printf("a740: 5: %s never reported up (status %08x, control %08x)\n", what, status,
	    cc_rd(gdscr));
	return false;
}

static void
clock_on(const char *what, unsigned cbcr)
{
	uint32_t value = cc_rd(cbcr);

	cc_wr(cbcr, value | 1u);
	printf("a740: 5: %s %08x -> %08x\n", what, value, cc_rd(cbcr));
}

static bool
step_power(void)
{
	uint32_t rails[3] = { 0, 0, 0 }, levels[3] = { 4, 0, 0 };   /* level 4 = NOMINAL */
	uint32_t cx_lvl, mx_lvl, cx_before, gx_before, gx_clamp_before;
	int rc;

	printf("a740: 5: trying to power the GPU up -- writes start here\n");
	g_cc = map("the GPU's clock controller", ASTON_GPU_CC, ASTON_GPU_CC_SIZE);
	if (g_cc == NULL) {
		return false;
	}
	cx_before = cc_rd(GPUCC_CX_GDSCR);
	gx_before = cc_rd(GPUCC_GX_GDSCR);
	printf("a740: 5: gpucc at 0x%x: cx domain %08x  gx domain %08x\n", ASTON_GPU_CC,
	    cx_before, gx_before);

	/* The rail the graphics core hangs off, as the resource list spells its name. */
	g_rsc = (uint32_t *)(uintptr_t)ml_io_map(ASTON_RSC, 0x10000);
	rails[0] = rail_address("gfx.lvl");
	cx_lvl = rail_address("cx.lvl");
	mx_lvl = rail_address("mx.lvl");
	printf("a740: 5: gfx.lvl %08x  cx.lvl %08x  mx.lvl %08x\n", rails[0], cx_lvl, mx_lvl);
	if (g_rsc != NULL && rails[0] != 0) {
		rc = rsc_vote(rails, levels);
		printf("a740: 5: gfx.lvl vote rc=%d\n", rc);
	}

	/*
	 * The order is the one the clock driver implies: the domain the buses live in comes up
	 * first, then the branches inside it, then the core's own domain. Enabling a branch before
	 * its domain answers nothing, which is what the last run showed -- 0x911c read 0 before the
	 * write and 0 after it.
	 */
	gdsc_on("cx domain", GPUCC_CX_GDSCR, GPUCC_CX_GDS_HW_CTRL, 0);
	clock_on("ahb", GPUCC_AHB_CBCR);
	clock_on("crc_ahb", GPUCC_CRC_AHB_CBCR);
	clock_on("cxo", GPUCC_CXO_CBCR);
	clock_on("cx_gmu", GPUCC_CX_GMU_CBCR);
	clock_on("hub_cx_int", GPUCC_HUB_CX_INT_CBCR);

	gx_clamp_before = cc_rd(GPUCC_GX_CLAMP_IO);
	gdsc_on("gx domain", GPUCC_GX_GDSCR, GPUCC_GX_GDSCR, GPUCC_GX_CLAMP_IO);
	clock_on("memnoc_gfx", GPUCC_MEMNOC_GFX_CBCR);
	clock_on("mnd1x_0", GPUCC_MND1X_0_CBCR);
	clock_on("mnd1x_1", GPUCC_MND1X_1_CBCR);

	printf("a740: 5: after the writes: cx %08x gx %08x\n",
	    cc_rd(GPUCC_CX_GDSCR), cc_rd(GPUCC_GX_GDSCR));

	{
		uint32_t *gpu = map("the GPU's registers", ASTON_GPU_REGS, ASTON_GPU_REGS_SIZE);

		if (gpu != NULL) {
			printf("a740: 5: RBBM_HW_VERSION %08x  RBBM_STATUS %08x\n",
			    gpu[A740_RBBM_HW_VERSION], gpu[A740_RBBM_STATUS]);
			printf("a740: 5: (0x0a0f.... would be an Adreno 740 answering)\n");
		}
	}
	/*
	 * Put the two power domains back the way they were found. A domain left half way between
	 * on and off keeps the GPU's clock controller in a state no other software expects, and
	 * whatever runs after this kernel deserves to find the phone as the boot loader left it.
	 */
	cc_wr(GPUCC_GX_GDSCR, gx_before);
	cc_wr(GPUCC_CX_GDSCR, cx_before);
	cc_wr(GPUCC_GX_CLAMP_IO, gx_clamp_before);
	printf("a740: 5: domains put back: cx %08x (status %08x)  gx %08x\n",
	    cc_rd(GPUCC_CX_GDSCR), cc_rd(GPUCC_CX_GDS_HW_CTRL), cc_rd(GPUCC_GX_GDSCR));
	return true;
}

static void
a740_probe(uint32_t steps)
{
	uint32_t done = 0;

	printf("a740: reading up to step %u of what this phone's GPU is\n", steps);
	if (!is_the_phone()) {
		return;
	}
	if (steps >= 1) {
		if (!step_clocks()) {
			printf("a740: stopped at step 1\n");
			return;
		}
		done = 1;
	}
	if (steps >= 2) {
		if (!step_core()) {
			printf("a740: stopped at step 2\n");
			return;
		}
		done = 2;
	}
	if (steps >= 3) {
		if (!step_smmu()) {
			printf("a740: stopped at step 3\n");
			return;
		}
		done = 3;
	}
	if (steps >= 4) {
		if (!step_rails()) {
			printf("a740: stopped at step 4\n");
			return;
		}
		done = 4;
	}
	if (steps >= 5) {
		if (!g_power) {
			printf("a740: 5: skipped -- step 5 writes to the hardware, so it needs a740_power=1\n");
		} else if (!step_power()) {
			printf("a740: stopped at step 5\n");
			return;
		} else {
			done = 5;
		}
	}
	printf("a740: %u steps read, and every one of them answered\n", done);
}

/*
 * Called once while the system starts, from hakios_input_init(), which is where this port's
 * devices are brought up. Nothing happens unless the boot-arg asks for it.
 *
 * "a740_pause=<seconds>" holds the boot here after the steps have printed, so that the screen
 * keeps what they said long enough to be photographed. The loader's own log cannot be asked
 * for this: once the kernel runs, the loader stops answering, so the screen is the only place
 * these numbers can be read.
 */
extern void delay(int usec);

void
hakios_a740_init(void)
{
	uint32_t steps = 0, pause = 0, power = 0;

	if (!PE_parse_boot_argn("a740", &steps, sizeof(steps)) || steps == 0) {
		return;
	}
	if (PE_parse_boot_argn("a740_power", &power, sizeof(power)) && power != 0) {
		g_power = true;
	}
	a740_probe(steps);
	if (PE_parse_boot_argn("a740_pause", &pause, sizeof(pause)) && pause > 0 && pause <= 300) {
		printf("a740: holding the screen for %u seconds\n", pause);
		for (uint32_t i = 0; i < pause * 10; i++) {
			delay(100000);          /* a tenth of a second at a time */
		}
		printf("a740: the hold is over, the system carries on\n");
	}
}
