#!/usr/bin/env python3
"""Second pass: put battery_forget() after the forward declaration of HakiosBatteryReport()."""
import io, os

C = os.path.join(os.environ.get('HS', '/home/chenyu/hackios/hackios-os'),
                 'xnu/files/bsd/dev/hakios.battery.c')
s = io.open(C, encoding='utf-8').read()

if 'static void\nbattery_forget(void)' in s:
    print('already there')
else:
    anchor = 'extern void HakiosBatteryReport(const void *state, unsigned size);'
    i = s.find(anchor)
    if i < 0:
        raise SystemExit('anchor not found')
    eol = s.find('\n', i) + 1
    body = """
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
}
"""
    s = s[:eol] + body + s[eol:]
    io.open(C, 'w', encoding='utf-8').write(s)
    print('inserted after line %d' % s[:eol].count('\n'))
