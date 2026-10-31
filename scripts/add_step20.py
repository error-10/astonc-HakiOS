# 给 Wi-Fi 探针加 step 20：通过 SPMI 仲裁器的 observer 通道**只读** PMIC 寄存器。
#
# 为什么：RSC 投票只告诉我们"命令被接受"（rc=0），不告诉我们 PMIC 有没有真的输出。
# 读法来自 dodge 移植（SM8750）实测过的 v8 仲裁器流程，地址按 aston.dts:14219 换成
# 我们这台机器的四个窗口：
#   cnfg 0xc42d000 / core 0xc400000 / chnls 0xc500000 / obsrvr 0xc440000
#
# 用法：aston_wifi_only=20 -v   -> 打印 smpe4/smpg2/smpg4/smpg6 四路 SMPS 的类型、
#        使能位、设定电压、实测电压、模式。只读，不写任何 PMIC 寄存器。
import sys

P = r'C:\Users\96943\Desktop\ios\port\kernel\hakios.aston_wifi.c'
t = open(P, encoding='utf-8').read()

# ---------- 1. 前置声明 ----------
anchor_decl = 'static bool step_wcn_power(void);\n'
if anchor_decl not in t:
    print('forward-decl anchor missing')
    sys.exit(1)
if 'step_pmic_read' in t:
    print('already patched')
    sys.exit(0)
t = t.replace(anchor_decl, anchor_decl + 'static bool step_pmic_read(void);\n', 1)

# ---------- 2. 函数本体，插在 wifi_probe_only 之前 ----------
anchor_fn = 'static void\nwifi_probe_only(uint32_t which)\n'
if anchor_fn not in t:
    print('wifi_probe_only anchor missing')
    sys.exit(1)

fn = r'''
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
'''

t = t.replace(anchor_fn, fn + '\n' + anchor_fn, 1)

# ---------- 3. 新常量 ----------
anchor_const = '#define ASTON_TCSR_SIZE       0x00030000ul\n'
if anchor_const not in t:
    print('TCSR const anchor missing')
    sys.exit(1)
t = t.replace(anchor_const, anchor_const + '''
#define ASTON_SPMI_CORE       0x0c400000ul      /* dt: spmi@c42d000 reg-names "core" */
#define ASTON_SPMI_CORE_SIZE  0x00003000ul
#define ASTON_SPMI_OBS        0x0c440000ul      /* "obsrvr": one channel per APID */
#define ASTON_SPMI_OBS_SIZE   0x00080000ul
''', 1)

# ---------- 4. case 20 ----------
anchor_case = '\tcase 16:\n'
if anchor_case not in t:
    print('case 16 anchor missing')
    sys.exit(1)
t = t.replace(anchor_case, '''\tcase 20:
\t\t(void)step_pmic_read();
\t\tbreak;
''' + anchor_case, 1)

open(P, 'w', encoding='utf-8', newline='\n').write(t)
print('patched step 20 into', P)
