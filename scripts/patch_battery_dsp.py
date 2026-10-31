#!/usr/bin/env python3
"""Make the audio DSP's battery manager usable, and keep the loader as its stand-in.

Android shows 90% and iOS shows 10% because iOS reads the loader's voltage estimate: the
launcher's cmdline says battery=1, and bsd/dev/hakios.adsp.c:2822 therefore refuses to start
battmgr_thread() at all ("not with battery=1: the battery is asked about the loader's way").
The numbers Android shows come from the DSP's battery manager (Qualcomm's battmgr, channel
PMIC_RTR_ADSP_APPS), which the code in adsp.c already asks, and passes to
hakios_battery_report() in bsd/dev/hakios.battery.c.

Four edits, no new files, no new paths to the battery:

  1. battmgr=3 may ask the DSP even when the cmdline still says battery=1 (the old guard is
     otherwise untouched: adsp=1 with no battery=1 already reached battmgr_start()).
  2. A missing USB_ONLINE answer no longer throws away the whole battery reading -- the port's
     numbers are asked for on their own, and "external = 0" says no more than it knows.
  3. A marked TODO where the USB property ids are still unverified on this phone's firmware.
  4. Three rounds in a row without a usable answer hand the battery back to the loader
     (hakios_battery_dsp_lost() in hakios.battery.c), instead of iOS being left with a power
     source nobody is updating.

Idempotent: each edit prints already/patched/MISS and running it twice changes nothing.
"""
import io
import os

HS = os.environ.get('HS', '/home/chenyu/hackios/hackios-os')
ADSP = os.path.join(HS, 'xnu/files/bsd/dev/hakios.adsp.c')
BATT = os.path.join(HS, 'xnu/files/bsd/dev/hakios.battery.c')


def read(p):
    # newline='': the tree is LF, and a Windows python must not translate it into CRLF on the way out.
    with io.open(p, encoding='utf-8', newline='') as f:
        return f.read()


def write(p, s):
    with io.open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(s)


def sub(s, old, new, path):
    if new in s:
        print('  already: %s' % old.splitlines()[0][:60])
        return s
    if old not in s:
        print('  MISS   : %s' % old.splitlines()[0][:60])
        return s
    print('  patched: %s' % old.splitlines()[0][:60])
    return s.replace(old, new, 1)


a = read(ADSP)

# ---- 1. two boot-arg meanings and the misses that hand the battery back (after adsp.c:2652) ------
a = sub(a, """#define BATTMGR_SECONDS         10""",
        """#define BATTMGR_SECONDS         10
#define BATTMGR_WITH_LOADER     3               /* battmgr=3: ask the DSP even with battery=1 in the cmdline */
#define BATTMGR_MISS_LIMIT      3               /* rounds in a row without a usable answer: the loader's stand in */

extern void hakios_battery_dsp_lost(void);\t/* bsd/dev/hakios.battery.c: the loader's numbers stand in again */""", ADSP)

# ---- 2. the guard that keeps the DSP out when the cmdline says battery=1 (adsp.c:2822) -----------
a = sub(a, """\tif (option("battery")) {
\t\t/* (the loader's way, through Qualcomm's UEFI charger drivers: one way to the battery at a time) */
\t\ttell("adsp: battmgr: not with battery=1: the battery is asked about the loader's way\\n");
\t\treturn;
\t}""",
        """\tif (option("battery") && wanted != BATTMGR_WITH_LOADER) {
\t\t/* (the loader's way, through Qualcomm's UEFI charger drivers: one way to the battery at a time;
\t\t * battmgr=3 asks the DSP anyway, for a launcher whose cmdline still says battery=1) */
\t\ttell("adsp: battmgr: not with battery=1: the battery is asked about the loader's way\\n");
\t\treturn;
\t}""", ADSP)

# ---- 3. a missing USB answer is not a missing battery (adsp.c:2757) ------------------------------
a = sub(a, """\t\tbool good = battmgr_get(BATTMGR_BATTERY_GET, BATT_CAPACITY, &capacity) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_STATUS, &status) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_PRESENT, &present) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_VOLT_NOW, &volt) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_CURR_NOW, &curr) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_TEMP, &temp) &&
\t\t    battmgr_get(BATTMGR_USB_GET, USB_ONLINE, &usb);""",
        """\t\tbool good = battmgr_get(BATTMGR_BATTERY_GET, BATT_CAPACITY, &capacity) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_STATUS, &status) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_PRESENT, &present) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_VOLT_NOW, &volt) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_CURR_NOW, &curr) &&
\t\t    battmgr_get(BATTMGR_BATTERY_GET, BATT_TEMP, &temp);

\t\t/* (the port's answer is not part of "usable": a USB_ONLINE nobody answers must not keep the
\t\t * charge off the screen -- external is then 0, which says "on the battery" and no more) */
\t\t(void)battmgr_get(BATTMGR_USB_GET, USB_ONLINE, &usb);""", ADSP)

# ---- 4. the TODO for the port's property ids (adsp.c:2769) ---------------------------------------
a = sub(a, """\t\t\tif (usb) {
\t\t\t\t(void)battmgr_get(BATTMGR_USB_GET, USB_TYPE, &usb_type);""",
        """\t\t\tif (usb) {
\t\t\t\t/* TODO(unknown property ids): USB_TYPE = 6, USB_VOLT_NOW = 1, USB_CURR_NOW = 3 are
\t\t\t\t * Linux's qcom_battmgr.c order and are NOT checked against this phone's firmware (only
\t\t\t\t * BATT_* 0..18 were, see the block's comment). battmgr=2 prints every number these ids
\t\t\t\t * answer; compare them with dumpsys and /sys/class/power_supply/usb before trusting
\t\t\t\t * usb_type/usb_voltage_uv/usb_current_ua. 0 is passed on while they answer nothing. */
\t\t\t\t(void)battmgr_get(BATTMGR_USB_GET, USB_TYPE, &usb_type);""", ADSP)

# ---- 5. the counter of rounds without an answer (adsp.c:2756) ------------------------------------
a = sub(a, """\t\tstatic uint32_t full, design, cycles;""",
        """\t\tstatic uint32_t full, design, cycles;
\t\tstatic uint32_t battmgr_misses;\t/* (rounds in a row without a usable answer) */""", ADSP)

# ---- 6. three missed rounds: the loader's numbers stand in again (adsp.c:2799) -------------------
a = sub(a, """\t\tif (round < 3 || round % 6 == 0 || !good) {""",
        """\t\tif (good) {
\t\t\tbattmgr_misses = 0;
\t\t} else if (++battmgr_misses == BATTMGR_MISS_LIMIT) {
\t\t\t/* (nothing usable for three rounds: what the loader last said is nearer the truth than a
\t\t\t * battery nobody is counting -- bsd/dev/hakios.battery.c takes the power source back.
\t\t\t * Said once per outage: == and never reset, or the line would come every third round) */
\t\t\ttell("adsp: battmgr: nothing usable for %u rounds: the loader's numbers stand in again\\n", battmgr_misses);
\t\t\thakios_battery_dsp_lost();
\t\t}
\t\tif (round < 3 || round % 6 == 0 || !good) {""", ADSP)

write(ADSP, a)

# ---- 7. giving the battery back to the loader (hakios.battery.c:205) -----------------------------
b = read(BATT)

b = sub(b, """\tbattery_source_dsp = 1;
\tbattery_updates++;
\tHakiosBatteryReport(b, sizeof(*b));
}""",
        """\tbattery_source_dsp = 1;
\tbattery_updates++;
\tHakiosBatteryReport(b, sizeof(*b));
}

/*
 * The DSP's battery manager has gone quiet (bsd/dev/hakios.adsp.c, battmgr_thread: rounds in a
 * row without a usable answer).  The loader's last numbers stand in again rather than a power
 * source that nobody updates; the next word from either of them says which one it is.
 */
void
hakios_battery_dsp_lost(void)
{
\tif (battery_source_dsp) {
\t\tprintf("hakios: battery: the DSP's battery manager is quiet; the loader's numbers stand in\\n");
\t}
\tbattery_source_dsp = 0;
}""", BATT)

write(BATT, b)
print('done')
