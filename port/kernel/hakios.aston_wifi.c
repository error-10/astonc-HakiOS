/*
 * The Wi-Fi of the OnePlus Ace 3, a QCA6490 behind PCIe0, looked at -- read only.
 *
 * The driver in hakios.wifi.c is for the POCO X5 Pro's WCN6750: that radio hangs off the WPSS
 * DSP and is reached through ath11k's AHB path. This phone's radio is a PCIe endpoint, so
 * nothing of that transport applies; what happens here first is the question that decides
 * whether the rest is work or a dead end -- may a kernel under Qualcomm's hypervisor even read
 * the PCIe controller's registers?
 *
 * Boot-arg aston_wifi=N performs steps 1 to N and stops:
 *
 *   1  reads  the PCIe0 host controller's PARF block at 0x1c00000: where the link training
 *             state machine stands, and which of the block's pages answer at all
 *   2  reads  the controller's own config space (DBI) at 0x60000000: the vendor and device
 *             ids it presents, which say whether the root complex is alive
 *   3  reads  the ELBI window at 0x60000f20: the door the MHI/BHI handshake with the radio
 *             goes through
 *   4  reads  the endpoint's config space through ECAM at 0x60100000: bus 0, device 0,
 *             function 0 -- the radio itself, if the link came up
 *   5  reads  the clock controller's PCIe0 power domains, gate and reset lines at 0x100000
 *             and the perst / clkreq / wlan-en pins at 0xf000000: whether the controller is
 *             powered at all, which decides whether steps 1-4 could ever have said anything
 *   6  votes  the PCIe0 power domains on and then off the AXI halts, and sees the PARF block
 *             come alive
 *   7  writes the controller and PHY bring-up: root generators, resets, RC mode, the device
 *             tree's PHY sequence, PERST
 *   8  votes  the four PMIC rails the radio needs and drives wlan-en, then repeats step 7
 *
 * Every address here is from this phone's device tree (qcom,pcie@1c00000: reg-names
 * parf/dm_core/elbi/conf), not from another port.
 *
 * An access the hypervisor does not like does not answer: it ends the run at once, or a quarter
 * of a minute later. So a step says what it is about to touch before it touches it, and a step
 * that reads nothing sensible stops the sequence instead of going on. Steps 1-5 only read;
 * step 6 writes, to turn the PCIe0 power domain and its clocks on so the link can train.
 */

#include <kern/clock.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <mach/vm_param.h>
#include <pexpert/pexpert.h>
#include <sys/hakios.input.h>
#include <sys/systm.h>
#include <vm/vm_kern.h>

#include "hakios.aston_pcie_phy_seq.h"

extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);

#define ASTON_SOC_BASE        0x00400000ul

#define ASTON_PCIE_PARF       0x01c00000ul      /* dt: qcom,pcie@1c00000 / reg-names "parf" */
#define ASTON_PCIE_PARF_SIZE  0x00003000ul
#define ASTON_PCIE_DBI        0x60000000ul      /* "dm_core": the controller's config space */
#define ASTON_PCIE_DBI_SIZE   0x00001000ul
#define ASTON_PCIE_ELBI       (0x60000000ul + 0x00000f20ul)   /* "elbi": MHI's door */
#define ASTON_PCIE_ELBI_SIZE  0x00001000ul
#define ASTON_PCIE_ECAM       0x60100000ul      /* "conf": the endpoint's config space */
#define ASTON_PCIE_ECAM_SIZE  0x00001000ul

/*
 * PARF, from the mainline pcie-qcom driver's view of this controller family. Only the first
 * one is certain enough to name; the rest is read as a sweep, because which pages answer is
 * itself the answer we are after.
 */
#define PARF_LTSSM            0x01c0            /* link training state machine, state in [5:0] */
#define PARF_LTSSM_LINK_UP    (1u << 6)

#define DBI_DEVICE_VENDOR     0x0000            /* 0x1103/0x1107 << 16 | 0x17cb */
#define DBI_CLASS_REVISION    0x0008
#define DBI_HEADER_TYPE       0x000c

/*
 * Step 5's registers, from the mainline kalama clock driver (drivers/clk/qcom/gcc-sm8550.c):
 * every offset below is the one that driver gives the PCIe0 gate, reset line or power domain,
 * so a value that does not match its documented reset state is an answer about the hypervisor,
 * not a guess about the register.
 */
#define ASTON_GCC             0x00100000ul      /* dt: clock-controller@100000 */
#define ASTON_GCC_SIZE        0x00100000ul
#define ASTON_TCSR            0x01fc0000ul      /* dt: clock-controller@1fc0000 */
#define ASTON_TCSR_SIZE       0x00030000ul

#define ASTON_SPMI_CORE       0x0c400000ul      /* dt: spmi@c42d000 reg-names "core" */
#define ASTON_SPMI_CORE_SIZE  0x00003000ul
#define ASTON_SPMI_OBS        0x0c440000ul      /* "obsrvr": one channel per APID */
#define ASTON_SPMI_OBS_SIZE   0x00080000ul
#define TCSR_PCIE0_CLKREF_EN  0x00015100ul      /* tcsrcc-sm8550: branch, bit 0 */

#define ASTON_TLMM            0x0f000000ul      /* dt: pinctrl@f000000.
                                                    * Was 0xf100000: every pin write landed one
                                                    * megabyte too high, so PERST was never released. */
#define ASTON_TLMM_SIZE       0x00100000ul

#define GCC_PCIE0_GDSCR       0x06b004          /* pcie_0_gdsc: bit 31 = powered, bit 0 = collapse */
#define GCC_PCIE0_PHY_GDSCR   0x06c000          /* pcie_0_phy_gdsc */
#define GCC_GDSC_COLLAPSE     0x052020          /* the vote register both domains answer to */
#define GCC_VOTE_A            0x052000          /* phy_rchng lives here */
#define GCC_VOTE_B            0x052008          /* slv/mstr/cfg/aux/pipe/q2a live here */
#define GCC_PCIE0_SLV_Q2A     0x06b01c
#define GCC_PCIE0_SLV_AXI     0x06b020
#define GCC_PCIE0_MSTR_AXI    0x06b02c
#define GCC_PCIE0_CFG_AHB     0x06b038
#define GCC_PCIE0_AUX         0x06b03c
#define GCC_PCIE0_PIPE        0x06b048
#define GCC_PCIE0_RCHNG       0x06b054
#define GCC_PCIE0_RCHNG_RCG   0x06b058
#define GCC_PCIE0_AUX_RCG     0x06b074
#define GCC_PCIE0_CLKREF      0x08c004          /* the reference clock switch */

/* The controller-side registers, same names and offsets as drivers/pci/controller/dwc/
 * pcie-qcom.c, which is where the sequence in step 7 comes from. */
#define PARF_SYS_CTRL                   0x0000
#define PARF_PM_CTRL                    0x0020
#define PARF_PHY_CTRL                   0x0040
#define PARF_MHI_CLOCK_RESET_CTRL       0x0174
#define PARF_AXI_MSTR_WR_ADDR_HALT_V2   0x01a8
#define PARF_LTSSM                      0x01b0
#define PARF_LTSSM_EN                    (1u << 8)
#define PARF_INT_ALL_STATUS             0x0224
#define PARF_INT_ALL_CLEAR              0x0228
#define PARF_STATUS                     0x0230
#define PARF_DEVICE_TYPE                0x1000
#define PARF_DEVICE_TYPE_RC             0x4
#define PARF_PHY_TEST_PWR_DOWN          (1u << 0)
#define PARF_MAC_PHY_POWERDOWN_IN_P2_D_MUX_EN (1u << 29)
#define PARF_MHI_BYPASS                 (1u << 4)
#define PARF_REQ_NOT_ENTR_L1            (1u << 5)
#define PARF_AXI_MSTR_WR_HALT_EN        (1u << 31)

/* The PHY's own register window ("phy" in the device tree) and its own reset line. */
#define ASTON_PCIE_PHY         0x01c06000ul
#define ASTON_PCIE_PHY_SIZE    0x00002000ul
#define GCC_PCIE0_PHY_BCR      0x06c01c          /* reset: pcie_0_phy_reset */
#define GCC_PCIE0_BCR          0x06b000          /* reset: pcie_0_core_reset */

/* One TLMM GPIO: cfg at 0x1000*n, in/out at +4, interrupt config at +8. */
#define TLMM_GPIO_CFG_FUNC_GPIO   0x0u
#define TLMM_GPIO_CFG_DRIVE_8MA   (3u << 6)
#define TLMM_GPIO_CFG_OUTPUT_EN   (1u << 9)
#define TLMM_GPIO_IO_OUT          (1u << 1)

/* The two vote registers the GDSCs and the branch clocks answer to. */
#define GCC_GDSC_VOTE         0x052020          /* per-domain collapse vote */
#define GCC_GDSC_VOTE_PCIE0   (1u << 0)         /* pcie_0_gdsc: collapse_mask = BIT(0) */
#define GCC_GDSC_VOTE_PHY     (1u << 3)         /* pcie_0_phy_gdsc: collapse_mask = BIT(3) */
#define GCC_GATE_VOTE         0x052008          /* branch enables: bits 0..5 are PCIe0's */
#define GCC_GATE_VOTE_PCIE0   0x0000003fu       /* slv_axi, mstr_axi, cfg_ahb, aux, pipe, q2a */

#define TLMM_GPIO_PERST       94                /* dn: perst-gpios */
#define TLMM_GPIO_CLKREQ      95                /* dn: clkreq-gpios */
#define TLMM_GPIO_WLAN_EN     96                /* dn: wlan-en-gpios */
#define TLMM_GPIO_WLAN_SW_CTRL 83               /* dn: qcom,wlan-sw-ctrl-gpio */
#define TLMM_GPIO_WLAN_EN_REAL   80            /* dn: wlan-en-gpio */
#define TLMM_GPIO_BT_EN          81            /* dn: bt-en-gpio */
#define TLMM_GPIO_SW_CTRL        82            /* dn: sw-ctrl-gpio */

/* The two root generators behind the PCIe0 branches, from gcc-sm8550.c: the aux clock runs
 * at 19.2 MHz straight off CXO, the rate-change clock at 100 MHz off GPLL0's even output.
 * At boot both read 0x80000000 -- "root off" -- so the branches are voted but nothing is
 * actually clocking the controller, which is why the link state stays at zero. */
#define GCC_PCIE0_AUX_CMD_RCGR     0x06b074
#define GCC_PCIE0_RCHNG_CMD_RCGR   0x06b058
#define RCG_CMD                    0x0
#define RCG_CFG_RCGR               0x4
#define RCG_CMD_UPDATE             (1u << 0)
#define RCG_CMD_ROOT_EN            (1u << 1)
#define RCG_CMD_ROOT_OFF           (1u << 31)
#define RCG_CFG(sel, div)          ((((sel) & 0x7) << 8) | (((div) - 1) & 0xff))

/* The branch halt bits, useful to see whether a vote actually took effect. */
#define GCC_PCIE0_AUX_HALT         0x06b03c
#define GCC_PCIE0_RCHNG_HALT       0x06b054
#define GCC_PCIE0_CFG_AHB_HALT     0x06b038

#define ECAM_DEVICE_VENDOR    0x0000
#define ECAM_COMMAND_STATUS   0x0004
#define ECAM_CLASS_REVISION   0x0008
#define ECAM_BIST_HEADER      0x000c

static bool
is_the_phone(void)
{
	extern vm_offset_t pe_arm_get_soc_base_phys(void);

	if (pe_arm_get_soc_base_phys() != ASTON_SOC_BASE) {
		printf("wifi: not this phone (the loader did not say aston): nothing is read\n");
		return false;
	}
	return true;
}

static uint32_t *
map(const char *what, uint64_t phys, uint64_t size)
{
	uint32_t *base = (uint32_t *)(uintptr_t)ml_io_map(phys, size);

	if (base == NULL) {
		printf("wifi: cannot map %s at 0x%llx\n", what, phys);
	}
	return base;
}

static bool
read_word(const char *what, uint32_t *base, unsigned off, uint32_t *out)
{
	/*
	 * The name goes out before the read, not with the value: an access that does not come
	 * back leaves the last line on the screen naming the register that ended the run.
	 */
	printf("wifi:   %-24s ", what);
	*out = *(volatile uint32_t *)((uintptr_t)base + off);
	printf("%08x\n", *out);
	return true;
}

/* Step 1: where the link stands, and which pages of PARF answer. */
static bool
step_parf(bool stop_if_dead)
{
	uint32_t *parf, ltssm = 0;
	unsigned live = 0;

	printf("wifi: 1: reading PCIe0's PARF block at 0x%x\n", ASTON_PCIE_PARF);
	parf = map("the PCIe0 PARF block", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
	if (parf == NULL) {
		return false;
	}
	read_word("PARF_LTSSM", parf, PARF_LTSSM, &ltssm);
	printf("wifi: 1: link state %u, link up %s\n", ltssm & 0x3f,
	    (ltssm & PARF_LTSSM_LINK_UP) ? "yes" : "no");

	printf("wifi: 1: a word every 0x100 bytes across the block:\n");
	for (unsigned off = 0; off < ASTON_PCIE_PARF_SIZE; off += 0x100) {
		uint32_t value;

		printf("wifi:   parf+0x%04x             ", off);
		value = *(volatile uint32_t *)((uintptr_t)parf + off);
		printf("%08x\n", value);
		if (value != 0 && value != 0xffffffff) {
			live++;
		}
	}
	printf("wifi: 1: %u of those 48 words read back as something (a dead block reads all 0 or all f)\n",
	    live);
	if (live == 0 && stop_if_dead) {
		printf("wifi: 1: the controller reads nothing at all: stopping here\n");
		return false;
	}
	if (live == 0) {
		printf("wifi: 1: the controller reads nothing at all, carrying on anyway (step 5 asks why)\n");
	}
	return true;
}

/* Step 2: the controller's own config space. */
static bool
step_dbi(void)
{
	uint32_t *dbi;
	uint32_t id = 0;

	printf("wifi: 2: reading the controller's config space at 0x%x\n", ASTON_PCIE_DBI);
	dbi = map("the controller's config space", ASTON_PCIE_DBI, ASTON_PCIE_DBI_SIZE);
	if (dbi == NULL) {
		return false;
	}
	read_word("DBI_DEVICE_VENDOR", dbi, DBI_DEVICE_VENDOR, &id);
	read_word("DBI_CLASS_REVISION", dbi, DBI_CLASS_REVISION, &id);
	read_word("DBI_HEADER_TYPE", dbi, DBI_HEADER_TYPE, &id);
	if (id == 0xffffffff) {
		printf("wifi: 2: the controller does not answer, carrying on anyway\n");
	}
	return true;
}

/* Step 3: the ELBI window the MHI handshake goes through. */
static bool
step_elbi(void)
{
	uint32_t *elbi;
	unsigned live = 0;

	printf("wifi: 3: reading the ELBI window at 0x%x\n", (unsigned)(ASTON_PCIE_ELBI));
	elbi = map("the ELBI window", ASTON_PCIE_ELBI, ASTON_PCIE_ELBI_SIZE);
	if (elbi == NULL) {
		return false;
	}
	printf("wifi: 3: the window the BHI handshake would use, word by word:\n");
	for (unsigned off = 0; off < 0x00a8; off += 4) {
		uint32_t value;

		printf("wifi:   elbi+0x%04x             ", off);
		value = *(volatile uint32_t *)((uintptr_t)elbi + off);
		printf("%08x\n", value);
		if (value != 0 && value != 0xffffffff) {
			live++;
		}
	}
	printf("wifi: 3: %u of those 42 words read back as something\n", live);
	return true;
}

/* Step 4: the radio itself, through ECAM. */
static bool
step_endpoint(void)
{
	uint32_t *ecam;
	uint32_t id = 0;

	printf("wifi: 4: reading bus 0, device 0, function 0 through ECAM at 0x%x\n", ASTON_PCIE_ECAM);
	ecam = map("the endpoint's config space", ASTON_PCIE_ECAM, ASTON_PCIE_ECAM_SIZE);
	if (ecam == NULL) {
		return false;
	}
	read_word("ECAM_DEVICE_VENDOR", ecam, ECAM_DEVICE_VENDOR, &id);
	printf("wifi: 4: vendor 0x%04x device 0x%04x -- the device tree expects 0x17cb and 0x1103 or 0x1107\n",
	    id & 0xffff, id >> 16);
	if (id == 0xffffffff || id == 0) {
		printf("wifi: 4: no endpoint answers: either the link is down or nothing is powered\n");
	}
	read_word("ECAM_COMMAND_STATUS", ecam, ECAM_COMMAND_STATUS, &id);
	read_word("ECAM_CLASS_REVISION", ecam, ECAM_CLASS_REVISION, &id);
	read_word("ECAM_BIST_HEADER", ecam, ECAM_BIST_HEADER, &id);
	return true;
}

/* Step 5: whether the PCIe power domains and gates are even on, and what the pins say. */
static bool
step_power(void)
{
	static const struct { const char *name; unsigned off; } clocks[] = {
	    { "pcie0_gdscr",       GCC_PCIE0_GDSCR },
	    { "pcie0_phy_gdscr",   GCC_PCIE0_PHY_GDSCR },
	    { "gdsc_collapse_vote", GCC_GDSC_COLLAPSE },
	    { "vote_0x52000",      GCC_VOTE_A },
	    { "vote_0x52008",      GCC_VOTE_B },
	    { "slv_q2a_axi_halt",  GCC_PCIE0_SLV_Q2A },
	    { "slv_axi_halt",      GCC_PCIE0_SLV_AXI },
	    { "mstr_axi_halt",     GCC_PCIE0_MSTR_AXI },
	    { "cfg_ahb_halt",      GCC_PCIE0_CFG_AHB },
	    { "aux_halt",          GCC_PCIE0_AUX },
	    { "pipe_halt",         GCC_PCIE0_PIPE },
	    { "rchng_halt",        GCC_PCIE0_RCHNG },
	    { "rchng_rcg",         GCC_PCIE0_RCHNG_RCG },
	    { "aux_rcg",           GCC_PCIE0_AUX_RCG },
	    { "clkref",            GCC_PCIE0_CLKREF },
	};
	static const unsigned pins[] = { TLMM_GPIO_PERST, TLMM_GPIO_CLKREQ, TLMM_GPIO_WLAN_EN };
	uint32_t *gcc, *tlmm, gdscr = 0;

	printf("wifi: 5: reading the PCIe0 power domains and gates in the clock controller at 0x%x\n",
	    ASTON_GCC);
	gcc = map("the clock controller", ASTON_GCC, ASTON_GCC_SIZE);
	if (gcc == NULL) {
		return false;
	}
	for (unsigned i = 0; i < sizeof(clocks) / sizeof(clocks[0]); i++) {
		read_word(clocks[i].name, gcc, clocks[i].off, &gdscr);
		if (clocks[i].off == GCC_PCIE0_GDSCR) {
			printf("wifi: 5: pcie0 domain %s, collapse %s\n",
			    (gdscr & (1u << 31)) ? "powered" : "off",
			    (gdscr & 1u) ? "requested" : "not requested");
		}
	}

	printf("wifi: 5: perst / clkreq / wlan-en pins, cfg io irq:\n");
	tlmm = map("the pin controller", ASTON_TLMM, ASTON_TLMM_SIZE);
	if (tlmm == NULL) {
		return false;
	}
	for (unsigned i = 0; i < sizeof(pins) / sizeof(pins[0]); i++) {
		uint32_t cfg, io, irq;

		printf("wifi:   gpio%-3u                  ", pins[i]);
		cfg = *(volatile uint32_t *)((uintptr_t)tlmm + pins[i] * 0x1000);
		io  = *(volatile uint32_t *)((uintptr_t)tlmm + pins[i] * 0x1000 + 4);
		irq = *(volatile uint32_t *)((uintptr_t)tlmm + pins[i] * 0x1000 + 8);
		printf("%08x %08x %08x\n", cfg, io, irq);
	}
	return true;
}

/* One step on its own: "aston_wifi_only=5" reads step 5 and nothing else, which is how a
 * step that hangs the bus gets separated from the ones that answer. */
static bool step_power_on(void);
static bool step_link(void);
static void gpio_out(uint32_t *tlmm, unsigned pin, unsigned value);
static unsigned gpio_in(uint32_t *tlmm, unsigned pin);
static bool step_pcie_rails(void);
static bool step_clkref(void);
static bool step_wcn_power(void);
static bool step_pmic_read(void);


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
	printf("wifi: 15: clkreq cfg was %08x now %08x, wlan-en io %08x\n", cfg,
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
	printf("wifi: 15 SAYS: up=%d after %u ms ltssm %08x dbi80 %08x f28 %08x phy %08x\n",
	    up, i * 5, *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
	    *(volatile uint32_t *)((uintptr_t)dbi + 0x80),
	    *(volatile uint32_t *)((uintptr_t)dbi + 0xf28),
	    *(volatile uint32_t *)((uintptr_t)phy + 0x214));
}


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

	printf("wifi: 16: driving the pins the device tree names (80/81/82/83)\n");
	gpio_out(tlmm, TLMM_GPIO_WLAN_EN_REAL, 0);
	gpio_out(tlmm, TLMM_GPIO_BT_EN, 0);
	gpio_out(tlmm, TLMM_GPIO_SW_CTRL, 1);
	gpio_out(tlmm, TLMM_GPIO_WLAN_SW_CTRL, 1);
	delay(10000);
	gpio_out(tlmm, TLMM_GPIO_WLAN_EN_REAL, 1);
	delay(100000);
	printf("wifi: 16: wlan-en 80 io %08x, bt-en 81 io %08x, sw 82 io %08x, sw 83 io %08x\n",
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
	printf("wifi: 16 SAYS: up=%d after %u ms ltssm %08x dbi80 %08x f28 %08x\n",
	    up, i * 5, *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
	    *(volatile uint32_t *)((uintptr_t)dbi + 0x80),
	    *(volatile uint32_t *)((uintptr_t)dbi + 0xf28));
}


/* ---------------------------------------------------------------------------
 * SPMI: read one PMIC register through the arbiter's observer channel.
 *
 * The windows come from aston.dts (qcom,spmi@c42d000): core 0xc400000,
 * observer 0xc440000.  The core block holds the APID table: count at +4, then
 * one entry per APID at +0x2000 + 4*i, whose bits 8..19 are the PPID.  A read
 * is opcode 13 written to observer + 0x20*apid; +0x08 bit0 goes DONE, bits
 * 1..3 are FAILURE/DENIED/DROPPED, and the byte shows up at +0x18.
 *
 * Returns 0 on success, -2 when the PPID is not in the table, -3 when the
 * arbiter reported an error and -4 when it never finished.
 * ------------------------------------------------------------------------- */
static int
spmi_rd(uint32_t *core, uint32_t *obs, uint16_t ppid, uint8_t reg, uint32_t *out)
{
	uintptr_t o;
	uint32_t n, i, v, st = 0;

	n = *(volatile uint32_t *)((uintptr_t)core + 4) & 0x7ff;
	if (n == 0 || n > 1024) {
		return -1;
	}
	for (i = 0; i < n; i++) {
		v = *(volatile uint32_t *)((uintptr_t)core + 0x2000 + 4 * i);
		if (((v >> 8) & 0xfff) == (uint32_t)ppid) {
			break;
		}
	}
	if (i == n) {
		return -2;
	}

	o = (uintptr_t)obs + 0x20 * (uintptr_t)i;
	*(volatile uint32_t *)(o + 0x00) =
	    (13u << 27) | ((uint32_t)(reg & 0xff) << 4);
	for (i = 0; i < 2000; i++) {
		st = *(volatile uint32_t *)(o + 0x08);
		if (st & 1u) {
			break;
		}
		delay(1);
	}
	if (!(st & 1u)) {
		return -4;
	}
	if (st & 0xe) {
		return -3;
	}
	*out = *(volatile uint32_t *)(o + 0x18) & 0xff;
	return 0;
}

/* Read a byte and keep the error code so the log can say *why* it failed. */
static int
pmic_byte(uint32_t *core, uint32_t *obs, uint16_t ppid, uint8_t reg, uint32_t *out)
{
	*out = 0xdeadbeef;
	return spmi_rd(core, obs, ppid, reg, out);
}

/*
 * step 20: ask the PMIC itself whether the rails we voted for are on.
 *
 * Why it matters: tcs_vote() only reports that the RPMh/RSC command was
 * accepted.  If a rail shows en=0 here, the module never had power and the
 * PCIe link could not have trained, no matter how right the controller side is.
 *
 * PM8550 components (from aston.dts): pm8550 = SID 1, pm8550ve_f = SID 3,
 * pm8550vs = SIDs 2/3/4/6.  The rails we care about live on vs:2 (SMPG2/4/6,
 * 0x615/0x617/0x619) and vs:4 (SMPE4, 0x417).
 *
 * Register offsets inside a PMIC5 buck peripheral:
 *   0x04 type (0x03 = buck), 0x46 bit7 enable, 0x40/0x41 voltage set,
 *   0x42/0x43 voltage measured, 0x45 mode.
 */
static bool
step_pmic_read(void)
{
	static const struct {
		const char *name;
		uint16_t    ppid;
	} rails[] = {
		{ "smpe4", 0x417 },   /* vdd-wlan-dig 966 mV, PM8550vs:4 */
		{ "smpg2", 0x615 },   /* vdd-wlan-aon 980 mV, PM8550vs:6 */
		{ "smpg4", 0x617 },   /* vdd-wlan-rfa2 1350 mV */
		{ "smpg6", 0x619 },   /* vdd-wlan-rfa1 1900 mV */
		{ "smpg5", 0x618 },   /* vdd-wlan 1000 mV */
	};
	uint32_t *core, *obs;
	unsigned i;
	uint32_t n, ver, type, en, set_lo, set_hi, meas_lo, meas_hi, mode;
	int rc;

	core = map("the SPMI arbiter core", ASTON_SPMI_CORE, ASTON_SPMI_CORE_SIZE);
	obs = map("the SPMI arbiter observer", ASTON_SPMI_OBS, ASTON_SPMI_OBS_SIZE);
	if (core == NULL || obs == NULL) {
		return false;
	}

	ver = *(volatile uint32_t *)((uintptr_t)core);
	n = *(volatile uint32_t *)((uintptr_t)core + 4) & 0x7ff;
	printf("wifi: 20: arbiter version %08x, %u APIDs\n", ver, n);

	for (i = 0; i < sizeof(rails) / sizeof(rails[0]); i++) {
		rc = pmic_byte(core, obs, rails[i].ppid, 0x04, &type);
		if (rc != 0) {
			printf("wifi: 20: %s ppid %#x: no peripheral (rc %d)\n",
			    rails[i].name, rails[i].ppid, rc);
			continue;
		}
		(void)pmic_byte(core, obs, rails[i].ppid, 0x46, &en);
		(void)pmic_byte(core, obs, rails[i].ppid, 0x40, &set_lo);
		(void)pmic_byte(core, obs, rails[i].ppid, 0x41, &set_hi);
		(void)pmic_byte(core, obs, rails[i].ppid, 0x42, &meas_lo);
		(void)pmic_byte(core, obs, rails[i].ppid, 0x43, &meas_hi);
		(void)pmic_byte(core, obs, rails[i].ppid, 0x45, &mode);
		printf("wifi: 20: %s type %02x en %02x set %02x%02x meas %02x%02x mode %02x\n",
		    rails[i].name, type, en, set_hi, set_lo, meas_hi, meas_lo,
		    mode);
	}
	return true;
}

static void
wifi_probe_only(uint32_t which)
{
	if (!is_the_phone()) {
		return;
	}
	printf("wifi: only step %u was asked for\n", which);
	switch (which) {
	case 1:
		(void)step_parf(false);
		break;
	case 2:
		(void)step_dbi();
		break;
	case 3:
		(void)step_elbi();
		break;
	case 4:
		(void)step_endpoint();
		break;
	case 5:
		(void)step_power();
		break;
	case 6:
		(void)step_power_on();
		break;
	case 7:
		(void)step_power_on();
		(void)step_link();
		break;
	case 8:
		(void)step_power_on();
		(void)step_link();
		(void)step_wcn_power();
		(void)step_link();
		break;
	case 20:
		(void)step_pmic_read();
		break;
	case 16:
		step_link_pins();
		break;
	case 15:
		step_link_alt();
		break;
	case 14: {
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
		printf("wifi: 14: retaining the domain's flip-flops and holding PERST low\n");
		*(volatile uint32_t *)((uintptr_t)gcc + 0x06b004) |= (1u << 11);
		*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) =
		    (*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) & ~0xffu) | 0x2fu;
		gpio_out(tlmm, TLMM_GPIO_PERST, 0);

		printf("wifi: 14: PARF routing before any DBI access\n");
		*(volatile uint32_t *)((uintptr_t)parf + PARF_DEVICE_TYPE) = PARF_DEVICE_TYPE_RC;
		*(volatile uint32_t *)((uintptr_t)parf + PARF_PHY_CTRL) &= ~1u;
		*(volatile uint32_t *)((uintptr_t)parf + 0x350) = 0;
		*(volatile uint32_t *)((uintptr_t)parf + PARF_SYS_CTRL) = 0x365e;
		*(volatile uint32_t *)((uintptr_t)parf + PARF_MHI_CLOCK_RESET_CTRL) |= (1u << 4);
		*(volatile uint32_t *)((uintptr_t)parf + 0x358) = 0x4000000;
		*(volatile uint32_t *)((uintptr_t)parf + PARF_AXI_MSTR_WR_ADDR_HALT_V2) |=
		    (1u << 31);
		printf("wifi: 14: parf sys %08x halt %08x rsvd %08x\n",
		    *(volatile uint32_t *)((uintptr_t)parf + PARF_SYS_CTRL),
		    *(volatile uint32_t *)((uintptr_t)parf + PARF_AXI_MSTR_WR_ADDR_HALT_V2),
		    *(volatile uint32_t *)((uintptr_t)parf + 0x358));

		printf("wifi: 14: replaying %u PHY writes\n", ASTON_PHY_SEQ_LEN);
		for (i = 0; i < ASTON_PHY_SEQ_LEN; i++) {
			*(volatile uint32_t *)((uintptr_t)phy + aston_phy_seq[i].off) =
			    aston_phy_seq[i].value;
			if (aston_phy_seq[i].delay_us) {
				delay(aston_phy_seq[i].delay_us);
			}
		}
		delay(1000);

		printf("wifi: 14: voting the PIPE clock and waiting for the PHY to lock\n");
		*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) |= (1u << 4);
		for (i = 0; i < 200; i++) {
			v = *(volatile uint32_t *)((uintptr_t)phy + 0x214);
			if ((v & (1u << 6)) == 0) {
				break;
			}
			delay(1000);
		}
		printf("wifi: 14: phy status %08x after %u ms, pipe %08x votes %08x/%08x\n",
		    *(volatile uint32_t *)((uintptr_t)phy + 0x214), i,
		    *(volatile uint32_t *)((uintptr_t)gcc + 0x06b030),
		    *(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE),
		    *(volatile uint32_t *)((uintptr_t)gcc + 0x052000));

		printf("wifi: 14: gen1, aspm off, link control2 was %08x\n",
		    *(volatile uint32_t *)((uintptr_t)dbi + 0xa0));
		*(volatile uint32_t *)((uintptr_t)dbi + 0xa0) =
		    (*(volatile uint32_t *)((uintptr_t)dbi + 0xa0) & ~0xfu) | 1u;
		*(volatile uint32_t *)((uintptr_t)dbi + 0x80) =
		    *(volatile uint32_t *)((uintptr_t)dbi + 0x80) & ~3u;

		printf("wifi: 14: releasing PERST and starting the state machine\n");
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
		printf("wifi: 14 SAYS: up=%d after %u ms ltssm %08x dbi80 %08x f28 %08x\n",
		    up, i * 5, *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
		    *(volatile uint32_t *)((uintptr_t)dbi + 0x80),
		    *(volatile uint32_t *)((uintptr_t)dbi + 0xf28));
		break;
	}
	case 12: {
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
				printf("wifi: 12: func %u pin %u cfg %08x io %08x\n", f, quad[i],
				    *(volatile uint32_t *)(pin + 0),
				    *(volatile uint32_t *)(pin + 1));
			}
			delay(50000);
			{
				uint32_t v = *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);

				*(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM) =
				    v | PARF_LTSSM_EN;
			}
			printf("wifi: 12: func %u ltssm en -> %08x\n", f,
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM));
			for (i = 0; i < sizeof(sample) / sizeof(sample[0]); i++) {
				uint32_t ltssm =
				    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);

				printf("wifi: 12: func %u t+%u ms ltssm %08x state %u\n", f,
				    sample[i], ltssm, ltssm & 0x3f);
				delay(100000);
			}
		}
		printf("wifi: 12 SAYS: done\n");
		break;
	}
	case 11: {
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

				printf("wifi: 11: %u ms ltssm %08x state %u dbg0 %08x\n", when[i],
				    ltssm, ltssm & 0x3f,
				    *(volatile uint32_t *)((uintptr_t)dbi + 0x728));
				delay(2000);
			}
			printf("wifi: 11 SAYS: up=%d pins perst %u clkreq %u wlan_en %u sw %u\n", up,
			    gpio_in(tlmm, TLMM_GPIO_PERST), gpio_in(tlmm, TLMM_GPIO_CLKREQ),
			    gpio_in(tlmm, TLMM_GPIO_WLAN_EN),
			    gpio_in(tlmm, TLMM_GPIO_WLAN_SW_CTRL));
			if (tcsr != NULL) {
				printf("wifi: 11 SAYS: clkref %08x pcie gdscr %08x status %08x\n",
				    *(volatile uint32_t *)((uintptr_t)tcsr + TCSR_PCIE0_CLKREF_EN),
				    *(volatile uint32_t *)((uintptr_t)map("the clock controller",
				    ASTON_GCC, ASTON_GCC_SIZE) + GCC_PCIE0_GDSCR),
				    *(volatile uint32_t *)((uintptr_t)parf + PARF_STATUS));
			}
		}
		break;
	}
	case 10: {
		bool up;
		uint32_t *parf, *dbi;

		(void)step_power_on();
		(void)step_pcie_rails();
		(void)step_clkref();
		(void)step_wcn_power();
		up = step_link();
		parf = map("the PCIe controller", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
		dbi = map("the PCIe core", 0x60000000ul, 0x00010000ul);
		if (parf != NULL && dbi != NULL) {
			printf("wifi: 10 SAYS: up=%d ltssm %08x/%08x status %08x\n", up,
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
			    *(volatile uint32_t *)((uintptr_t)parf + 0x01c0),
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_STATUS));
			printf("wifi: 10 SAYS: dbi id %08x link ctrl %08x debug0 %08x debug1 %08x\n",
			    *(volatile uint32_t *)((uintptr_t)dbi + 0x000),
			    *(volatile uint32_t *)((uintptr_t)dbi + 0x710),
			    *(volatile uint32_t *)((uintptr_t)dbi + 0x728),
			    *(volatile uint32_t *)((uintptr_t)dbi + 0x72c));
		}
		break;
	}
	case 9: {
		bool up;
		uint32_t *parf;

		(void)step_power_on();
		(void)step_pcie_rails();
		(void)step_wcn_power();
		up = step_link();
		parf = map("the PCIe controller", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
		if (parf != NULL) {
			printf("wifi: 9 SAYS: up=%d ltssm %08x/%08x status %08x\n", up,
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM),
			    *(volatile uint32_t *)((uintptr_t)parf + 0x01c0),
			    *(volatile uint32_t *)((uintptr_t)parf + PARF_STATUS));
		}
		break;
	}
	default:
		printf("wifi: there is no step %u\n", which);
		break;
	}
}

/* Step 6: turn the PCIe0 power domain and its clocks on, then look at the link again.

 * Everything here is the mainline clock driver's own sequence, with the offsets taken from
 * drivers/clk/qcom/gcc-sm8550.c: a GDSC is uncollapsed by clearing its bit in the vote
 * register at 0x52020 and waiting for the power-on bit (bit 31) of its GDSCR; the branch
 * clocks are enabled by voting their bits in 0x52008 and then waiting for the halt bit to
 * drop. Nothing is restored afterwards: a reboot is the reset.
 */
static bool
step_power_on(void)
{
	uint32_t *gcc, collapse, vote;
	unsigned i;

	printf("wifi: 6: turning PCIe0 on\n");
	gcc = map("the clock controller", ASTON_GCC, ASTON_GCC_SIZE);
	if (gcc == NULL) {
		return false;
	}
	collapse = *(volatile uint32_t *)((uintptr_t)gcc + GCC_GDSC_VOTE);
	printf("wifi: 6: collapse vote was %08x\n", collapse);

	collapse &= ~(GCC_GDSC_VOTE_PCIE0 | GCC_GDSC_VOTE_PHY);
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_GDSC_VOTE) = collapse;
	printf("wifi: 6: collapse vote now %08x (pcie0 and phy uncollapsed)\n",
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_GDSC_VOTE));

	for (i = 0; i < 1000; i++) {
		uint32_t gdscr = *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_GDSCR);
		uint32_t phys = *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_PHY_GDSCR);

		if ((gdscr & (1u << 31)) && (phys & (1u << 31))) {
			printf("wifi: 6: both domains powered after %u polls\n", i);
			break;
		}
		delay(1000);
	}
	printf("wifi: 6: pcie0_gdscr now %08x, phy %08x\n",
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_GDSCR),
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_PHY_GDSCR));

	vote = *(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE);
	printf("wifi: 6: gate vote was %08x\n", vote);
	vote |= GCC_GATE_VOTE_PCIE0;
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) = vote;
	printf("wifi: 6: gate vote now %08x (slv_axi mstr_axi cfg_ahb aux pipe slv_q2a)\n",
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE));

	for (i = 0; i < 200; i++) {
		uint32_t halts = *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_SLV_AXI);

		if ((halts & (1u << 31)) == 0) {
			printf("wifi: 6: the clocks came out of halt after %u polls\n", i);
			break;
		}
		delay(1000);
	}
	printf("wifi: 6: slv_axi halt now %08x (bit 31 clear means running)\n",
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_SLV_AXI));

	printf("wifi: 6: reading the link state again\n");
	return step_parf(false);
}

/* Step 7: the sequence drivers/pci/controller/dwc/pcie-qcom.c runs for this controller
 * (init_2_7_0, the one SM8550 uses), plus the PHY's own list from the device tree.
 *
 * Order matters and is the driver's: hold the endpoint in reset, set the controller to root
 * complex mode, take the PHY out of power down, replay the PHY sequence, then release reset
 * and watch the link training state.
 */
static void
gpio_out(uint32_t *tlmm, unsigned pin, unsigned value)
{
	uint32_t cfg = TLMM_GPIO_CFG_FUNC_GPIO | TLMM_GPIO_CFG_DRIVE_8MA | TLMM_GPIO_CFG_OUTPUT_EN;
	uint32_t io;

	*(volatile uint32_t *)((uintptr_t)tlmm + pin * 0x1000) = cfg;
	io = *(volatile uint32_t *)((uintptr_t)tlmm + pin * 0x1000 + 4);
	io &= ~TLMM_GPIO_IO_OUT;
	if (value) {
		io |= TLMM_GPIO_IO_OUT;
	}
	*(volatile uint32_t *)((uintptr_t)tlmm + pin * 0x1000 + 4) = io;
}

static unsigned
gpio_in(uint32_t *tlmm, unsigned pin)
{
	uint32_t in = *(volatile uint32_t *)((uintptr_t)tlmm + 0x0b000u + 4u * (pin / 32));

	return (in >> (pin % 32)) & 1u;
}

/* The radio's own supplies. They are PMIC rails voted through the apps RSC, with the same
 * three-command AMC vote the touch driver uses. The keys are the device tree's regulator
 * node names run together -- rpmh-regulator-ldob15 becomes "ldob15", rpmh-regulator-smpe4
 * becomes "smpe4", which is the same shape as the "ldob4" the touch driver votes for. The
 * voltages are the ones that tree asks for. */
#define ASTON_RSC_DEFAULT 0x17a00000ul   /* apps_rsc, when soc_rsc says nothing */
#define ASTON_DB_DEFAULT  0x81c60000ul   /* the command DB the touch driver also reads */
#define ASTON_RSC_TCS     0x0d00u
#define ASTON_RSC_STRIDE  0x02a0u
#define ASTON_DB_SIZE     0x00100000ul

static const struct {
	const char *name;
	uint32_t    mv;
} wcn_rails[] = {
	{ "ldob15", 1800 },     /* vdd-wlan-io, pm_humu_l15 */
	{ "smpg2",   980 },     /* vdd-wlan-aon, pm_v6g_s2 */
	{ "smpe4",   966 },     /* vdd-wlan-dig, pm_v6e_s4 */
	{ "smpg4",  1350 },     /* vdd-wlan-rfa2, pm_v6g_s4 */
	{ "smpg6",  1900 },     /* vdd-wlan-rfa1, pm_v6g_s6 */
};

/* The controller's own supplies, from the device tree's vreg-* properties. */
static const struct {
	const char *name;
	uint32_t    mv;
} pcie_rails[] = {
	{ "ldoe3", 1200 },      /* vreg-1p2, pm_v6e_l3 */
	{ "ldoe1",  880 },      /* vreg-0p9, pm_v6e_l1 */
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
	unsigned s, i, k, len = (unsigned)strlen(name);

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

			if (len > 8) {
				continue;
			}
			for (k = 0; k < len; k++) {
				if (e[k] != (uint8_t)name[k]) {
					same = false;
					break;
				}
			}
			/* the rest of the key may be zero or space padded */
			for (k = len; same && k < 8; k++) {
				if (e[k] != 0 && e[k] != ' ') {
					same = false;
				}
			}
			if (same) {
				return le32(e + 16);
			}
		}
	}
	return 0;
}

/* Print the regulator keys in the command DB, packed into a few lines: only the tail of this
 * log survives the trip back, so one line per key would lose most of the list. */
static void __attribute__((unused))
db_dump(uint32_t *db, unsigned per_line)
{
	const uint8_t *base = (const uint8_t *)db;
	char line[256];
	unsigned s, i, total = 0, in_line = 0;

	line[0] = 0;
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
			char name[9];
			unsigned k;

			if (!((e[0] == 'l' && e[1] == 'd' && e[2] == 'o') ||
			    (e[0] == 's' && e[1] == 'm' && e[2] == 'p'))) {
				continue;
			}
			for (k = 0; k < 8; k++) {
				name[k] = (e[k] >= 32 && e[k] <= 126) ? e[k] : ' ';
			}
			while (k > 0 && name[k - 1] == ' ') {
				name[--k] = 0;
			}
			name[8] = 0;
			snprintf(line + strlen(line), sizeof(line) - strlen(line), " %s=%05x",
			    name, le32(e + 16) >> 8);
			total++;
			if (++in_line == per_line) {
				printf("wifi: 8: db %s\n", line);
				line[0] = 0;
				in_line = 0;
			}
		}
	}
	if (in_line) {
		printf("wifi: 8: db %s\n", line);
	}
	printf("wifi: 8: command DB holds %u regulator keys\n", total);
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

static bool
clk_root_on(uint32_t *gcc, const char *what, uint32_t base, uint32_t cfg)
{
	uint32_t cmd = 0, i;

	*(volatile uint32_t *)((uintptr_t)gcc + base + RCG_CFG_RCGR) = cfg;
	*(volatile uint32_t *)((uintptr_t)gcc + base + RCG_CMD) = RCG_CMD_UPDATE | RCG_CMD_ROOT_EN;
	for (i = 0; i < 100; i++) {
		cmd = *(volatile uint32_t *)((uintptr_t)gcc + base + RCG_CMD);
		if ((cmd & RCG_CMD_UPDATE) == 0) {
			break;
		}
		delay(100);
	}
	printf("wifi: 7: %s root: cmd %08x cfg %08x, %s\n", what, cmd,
	    *(volatile uint32_t *)((uintptr_t)gcc + base + RCG_CFG_RCGR),
	    (cmd & RCG_CMD_ROOT_OFF) ? "still off" : "running");
	return (cmd & RCG_CMD_ROOT_OFF) == 0;
}

static bool
step_link(void)
{
	uint32_t *gcc, *parf, *phy, *tlmm, i;
	uint32_t ltssm;

	printf("wifi: 7: bringing the controller and its PHY up\n");
	gcc = map("the clock controller", ASTON_GCC, ASTON_GCC_SIZE);
	if (gcc == NULL) {
		return false;
	}
	parf = map("the PCIe controller", ASTON_PCIE_PARF, ASTON_PCIE_PARF_SIZE);
	if (parf == NULL) {
		return false;
	}
	phy = map("the PCIe PHY", ASTON_PCIE_PHY, ASTON_PCIE_PHY_SIZE);
	if (phy == NULL) {
		return false;
	}
	tlmm = map("the pin controller", ASTON_TLMM, ASTON_TLMM_SIZE);
	if (tlmm == NULL) {
		return false;
	}

	printf("wifi: 7: voting the branches and starting the root generators\n");
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE) |= GCC_GATE_VOTE_PCIE0;
	*(volatile uint32_t *)((uintptr_t)gcc + 0x052000) |= (1u << 22);
	(void)clk_root_on(gcc, "aux", GCC_PCIE0_AUX_CMD_RCGR, RCG_CFG(0, 1));
	(void)clk_root_on(gcc, "rate change", GCC_PCIE0_RCHNG_CMD_RCGR, RCG_CFG(6, 3));
	delay(1000);
	printf("wifi: 7: votes %08x/%08x, halts aux %08x cfg_ahb %08x rchng %08x\n",
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_GATE_VOTE),
	    *(volatile uint32_t *)((uintptr_t)gcc + 0x052000),
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_AUX_HALT),
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_CFG_AHB_HALT),
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_RCHNG_HALT));

	printf("wifi: 7: holding PERST (gpio%u) low\n", TLMM_GPIO_PERST);
	gpio_out(tlmm, TLMM_GPIO_PERST, 0);

	printf("wifi: 7: asserting then releasing the two resets\n");
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_BCR) |= 1u;
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_PHY_BCR) |= 1u;
	delay(2000);
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_BCR) &= ~1u;
	*(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_PHY_BCR) &= ~1u;
	delay(2000);
	printf("wifi: 7: core bcr %08x, phy bcr %08x\n",
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_BCR),
	    *(volatile uint32_t *)((uintptr_t)gcc + GCC_PCIE0_PHY_BCR));

	printf("wifi: 7: setting root complex mode and the PARF bits the driver sets\n");
	*(volatile uint32_t *)((uintptr_t)parf + PARF_DEVICE_TYPE) = PARF_DEVICE_TYPE_RC;
	printf("wifi: 7: device type %08x\n",
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_DEVICE_TYPE));

	printf("wifi: 7: phy ctrl before %08x\n",
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_PHY_CTRL));
	*(volatile uint32_t *)((uintptr_t)parf + PARF_PHY_CTRL) &=
	    ~PARF_PHY_TEST_PWR_DOWN;
	printf("wifi: 7: phy ctrl after  %08x (test power down cleared)\n",
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_PHY_CTRL));

	*(volatile uint32_t *)((uintptr_t)parf + PARF_SYS_CTRL) &=
	    ~PARF_MAC_PHY_POWERDOWN_IN_P2_D_MUX_EN;
	printf("wifi: 7: sys ctrl            %08x\n",
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_SYS_CTRL));
	*(volatile uint32_t *)((uintptr_t)parf + PARF_MHI_CLOCK_RESET_CTRL) |= PARF_MHI_BYPASS;
	printf("wifi: 7: mhi clock reset ctrl %08x\n",
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_MHI_CLOCK_RESET_CTRL));
	*(volatile uint32_t *)((uintptr_t)parf + PARF_PM_CTRL) &= ~PARF_REQ_NOT_ENTR_L1;
	*(volatile uint32_t *)((uintptr_t)parf + PARF_AXI_MSTR_WR_ADDR_HALT_V2) |=
	    PARF_AXI_MSTR_WR_HALT_EN;
	printf("wifi: 7: pm ctrl %08x, wr halt %08x\n",
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_PM_CTRL),
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_AXI_MSTR_WR_ADDR_HALT_V2));

	printf("wifi: 7: replaying %u PHY writes from the device tree\n", ASTON_PHY_SEQ_LEN);
	for (i = 0; i < ASTON_PHY_SEQ_LEN; i++) {
		*(volatile uint32_t *)((uintptr_t)phy + aston_phy_seq[i].off) =
		    aston_phy_seq[i].value;
		if (aston_phy_seq[i].delay_us) {
			delay(aston_phy_seq[i].delay_us);
		}
	}
	printf("wifi: 7: phy done, releasing PERST\n");
	gpio_out(tlmm, TLMM_GPIO_PERST, 1);
	delay(2000);

	/* Bit 8 of PARF_LTSSM enables the training state machine. Until it is set the machine
	 * stays in detect-quiet, which is the zero this register has read all along. */
	*(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM) |= PARF_LTSSM_EN;
	printf("wifi: 7: ltssm enable written, register now %08x\n",
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM));

	for (i = 0; i < 500; i++) {
		ltssm = *(volatile uint32_t *)((uintptr_t)parf + PARF_LTSSM);
		if (i == 0 || i == 100) {
			printf("wifi: 7: ltssm %u ms: 1b0 %08x / 1c0 %08x\n", i, ltssm,
			    *(volatile uint32_t *)((uintptr_t)parf + 0x01c0));
		}
		if ((ltssm & 0x3f) != 0) {
			break;
		}
		delay(1000);
	}
	printf("wifi: 7: LTSSM %08x after %u ms, state %u, link up %s\n", ltssm, i,
	    ltssm & 0x3f, (ltssm & (1u << 6)) ? "yes" : "no");
	printf("wifi: 7: status %08x, interrupts %08x\n",
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_STATUS),
	    *(volatile uint32_t *)((uintptr_t)parf + PARF_INT_ALL_STATUS));

	if (ltssm & (1u << 6)) {
		printf("wifi: 7: the link came up\n");
		return true;
	}
	printf("wifi: 7: the link did not come up\n");
	return false;
}

/* Step 8: give the radio its power. The four rails in wcn_rails are the ones the device tree
 * hangs off the cnss node, and without them the endpoint is dark no matter what the host does.
 */
/* Step 9, part one: vote the controller's two supplies on through the same TCS path the radio
 * rails use. Nothing has ever voted these, so the PHY cannot leave reset.
 */
static bool
step_pcie_rails(void)
{
	uint32_t *rsc, *db, i, addr, rsc_base, db_base;

	printf("wifi: 9: voting the controller's own supplies\n");
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
			printf("wifi: 9: %s is not in the command DB\n", pcie_rails[i].name);
			continue;
		}
		addrs[0] = addr;
		addrs[1] = addr + 4;
		addrs[2] = addr + 8;
		values[0] = pcie_rails[i].mv;
		values[1] = 1;
		values[2] = 4;
		printf("wifi: 9: %s at %08x, %u mV, vote rc=%d\n", pcie_rails[i].name, addr,
		    pcie_rails[i].mv, tcs_vote(rsc, addrs, values));
	}
	delay(20000);
	return true;
}

/* Step 10, part one: flip on the reference clock buffer that feeds the module. */
static bool
step_clkref(void)
{
	uint32_t *tcsr, before;

	tcsr = map("the TCSR clock controller", ASTON_TCSR, ASTON_TCSR_SIZE);
	if (tcsr == NULL) {
		return false;
	}
	before = *(volatile uint32_t *)((uintptr_t)tcsr + TCSR_PCIE0_CLKREF_EN);
	*(volatile uint32_t *)((uintptr_t)tcsr + TCSR_PCIE0_CLKREF_EN) = before | 1u;
	printf("wifi: 10: pcie0 clkref was %08x, now %08x\n", before,
	    *(volatile uint32_t *)((uintptr_t)tcsr + TCSR_PCIE0_CLKREF_EN));
	delay(2000);
	return true;
}

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

	/* db_dump(db, 12);  key list is known now, and it was eating the log tail */

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
wifi_probe(uint32_t steps)
{
	unsigned done = 0;

	if (!is_the_phone()) {
		return;
	}
	if (steps >= 1) {
		if (!step_parf(steps < 5)) {
			printf("wifi: stopped at step 1\n");
			return;
		}
		done = 1;
	}
	if (steps >= 2) {
		if (!step_dbi()) {
			printf("wifi: stopped at step 2\n");
			return;
		}
		done = 2;
	}
	if (steps >= 3) {
		if (!step_elbi()) {
			printf("wifi: stopped at step 3\n");
			return;
		}
		done = 3;
	}
	if (steps >= 4) {
		if (!step_endpoint()) {
			printf("wifi: stopped at step 4\n");
			return;
		}
		done = 4;
	}
	if (steps >= 5) {
		if (!step_power()) {
			printf("wifi: stopped at step 5\n");
			return;
		}
		done = 5;
	}
	if (steps >= 6) {
		if (!step_power_on()) {
			printf("wifi: stopped at step 6\n");
			return;
		}
		done = 6;
	}
	printf("wifi: %u steps read\n", done);
}

/*
 * Called once while the system starts, from hakios_input_init(), which is where this port's
 * devices are brought up. Nothing happens unless the boot-arg asks for it.
 *
 * "aston_wifi_pause=<seconds>" holds the boot here after the steps have printed, so the screen
 * keeps what they said long enough to be photographed.
 */
extern void delay(int usec);

void
hakios_aston_wifi_init(void)
{
	uint32_t steps = 0, pause = 0, only = 0;

	if (!PE_parse_boot_argn("aston_wifi", &steps, sizeof(steps)) || steps == 0) {
		if (!PE_parse_boot_argn("aston_wifi_only", &only, sizeof(only)) || only == 0) {
			return;
		}
		wifi_probe_only(only);
	} else {
		wifi_probe(steps);
	}
	if (PE_parse_boot_argn("aston_wifi_pause", &pause, sizeof(pause)) && pause > 0 && pause <= 300) {
		printf("wifi: holding the screen for %u seconds\n", pause);
		for (uint32_t i = 0; i < pause * 10; i++) {
			delay(100000);          /* a tenth of a second at a time */
		}
		printf("wifi: the hold is over, the system carries on\n");
	}
}
