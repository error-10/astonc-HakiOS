#!/usr/bin/env python3
"""Make the battery display honest.

Three things were wrong, all of them visible on the phone:

  1. The loader's numbers stop moving the moment iOS owns the machine (the loader runs on the
     same core), but the kernel kept the last good reading for ever -- so the percentage froze at
     whatever the UEFI charger stack last said (10% on a 60% battery).
  2. An unknown voltage was passed on as 0 mV, and an unknown temperature as 0 degrees.
  3. iOS was told "Fully Charged" whenever the charger firmware said so -- which on this firmware
     it does even when the battery is at 10%.

Nothing here changes the loader; it only teaches the kernel to say "I do not know" instead of
repeating something it knew half a minute ago.  Idempotent: safe to run again.
"""
import io
import os
import sys

HS = os.environ.get('HS', '/home/chenyu/hackios/hackios-os')
C = os.path.join(HS, 'xnu/files/bsd/dev/hakios.battery.c')
CPP = os.path.join(HS, 'xnu/files/iokit/Kernel/hakios.battery.cpp')


def read(p):
    with io.open(p, encoding='utf-8') as f:
        return f.read()


def write(p, s):
    with io.open(p, 'w', encoding='utf-8') as f:
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


c = read(C)

# ---- 1. the counters that notice a cache which stopped moving -----------------------------------
c = sub(c, """static uint64_t battery_updates, battery_failures;""",
        """static uint64_t battery_updates, battery_failures;

/* A poll every 5 s, so 6 of them is half a minute without a new word from the loader. */
#define BATTERY_STALE_POLLS 6
static uint32_t battery_polls_seen;
static int battery_stale_polls, battery_stale_said;""", C)

# ---- 2. forgetting: the loader has gone quiet, so stop claiming what it said ----------------------
c = sub(c, """extern void HakiosBatteryReport(const void *state, unsigned size);\t/* iokit/Kernel/hakios.battery.cpp */""",
        """extern void HakiosBatteryReport(const void *state, unsigned size);\t/* iokit/Kernel/hakios.battery.cpp */

/*
 * The last words of a loader that is no longer answering are not the truth any more.  Keep the
 * percentage (there is nothing better to put in its place, and iOS dislikes a power source that
 * loses its charge), drop everything that has to be live -- the lightning bolt above all -- and let
 * iOS know the battery is on its own now.
 */
static void
battery_forget(void)
{
\tstruct hakios_battery_state b;

\tbattery_voltage_mv = -1;
\tbattery_current_ma = 0;
\tbattery_temperature_c = -273;
\tbattery_charging = 0;
\tbattery_charger_present = 0;
\tbattery_soc_estimated = 1;
\tbzero(&b, sizeof(b));
\tb.size = sizeof(b);
\tb.percent_hundredths = (battery_soc_percent < 0 ? 0 : battery_soc_percent) * 100;
\tb.present = 1;
\tb.status = 2;\t\t\t/* POWER_SUPPLY_STATUS_DISCHARGING: nothing is feeding us */
\tbattery_updates++;
\tHakiosBatteryReport(&b, sizeof(b));
}""", C)

# ---- 3. an unknown voltage or temperature is not zero --------------------------------------------
c = sub(c, """\tbattery_voltage_mv = (sample.flags & LOADER_BATTERY_VOLTAGE_VALID) ? sample.voltage_mv : -1;
\tbattery_current_ma = sample.current_ma;
\tbattery_temperature_c = sample.temperature_c;""",
        """\tbattery_voltage_mv = ((sample.flags & LOADER_BATTERY_VOLTAGE_VALID) && sample.voltage_mv > 0) ?
\t    sample.voltage_mv : -1;
\tbattery_current_ma = sample.current_ma;
\t/* 0 and -273 are how "the firmware could not read it" arrives; do not pass those on. */
\tbattery_temperature_c = (sample.temperature_c > -4000 && sample.temperature_c < 12000) ?
\t    sample.temperature_c : -273;""", C)

# ---- 4. notice when the loader's cache has stopped moving ---------------------------------------
c = sub(c, """\tbattery_updates++;
\tbattery_report_from_loader();""",
        """\tbattery_updates++;
\tif (sample.polls == battery_polls_seen) {
\t\tif (++battery_stale_polls >= BATTERY_STALE_POLLS && !battery_stale_said) {
\t\t\tbattery_stale_said = 1;
\t\t\tprintf("hakios: battery: the loader's cache has not moved for %d polls; forgetting it\\n",
\t\t\t    battery_stale_polls);
\t\t\tbattery_forget();
\t\t\treturn;
\t\t}
\t} else {
\t\tbattery_polls_seen = sample.polls;
\t\tbattery_stale_polls = 0;
\t\tbattery_stale_said = 0;
\t}
\tbattery_report_from_loader();""", C)

write(C, c)

# ---- the power source iOS reads ----------------------------------------------------------------
p = read(CPP)

# 5. "Fully Charged" only when it nearly is
p = sub(p, """\tflag("FullyCharged", b->external && (b->status == 4 || percent == 100));""",
        """\tflag("FullyCharged", b->external && (b->status == 4 || percent == 100) && percent >= 95);""", CPP)

# 6. do not publish a voltage of 0 mV
p = sub(p, """\tsetVoltage((unsigned) (b->voltage_uv / 1000));""",
        """\tif (b->voltage_uv > 0) {
\t\tsetVoltage((unsigned) (b->voltage_uv / 1000));
\t}""", CPP)

# 7. nor a temperature the firmware never measured
p = sub(p, """\tnumber("Temperature", b->temperature_hundredths);""",
        """\tif (b->temperature_hundredths > -4000 && b->temperature_hundredths < 12000) {
\t\tnumber("Temperature", b->temperature_hundredths);
\t}""", CPP)

# 8. an adapter with no numbers of its own borrows the battery's, and its type guessed from them
p = sub(p, """\t\tlong long mv = b->usb_voltage_uv / 1000, ma = b->usb_current_ua / 1000;
\t\tOSNumber * n;""",
        """\t\tlong long mv = (b->usb_voltage_uv > 0 ? b->usb_voltage_uv : b->voltage_uv) / 1000;
\t\tlong long ma = b->usb_current_ua > 0 ? b->usb_current_ua / 1000 : 0;
\t\tint type = b->usb_type;

\t\tif (type <= 0) {
\t\t\ttype = ma >= 500 ? 2 : 1;\t/* a charger rather than a computer's port */
\t\t}
\t\tOSNumber * n;""", CPP)

p = sub(p, """\t\t\tif ((n = OSNumber::withNumber((unsigned long long) family_code(b->usb_type), 32)) != NULL) {""",
        """\t\t\tif ((n = OSNumber::withNumber((unsigned long long) family_code(type), 32)) != NULL) {""", CPP)

write(CPP, p)
print('done')
