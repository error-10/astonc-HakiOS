"""Fix the rail keys: this platform's command DB has no dot in its names.

The dump from the phone showed keys like "ldod1", "smpe1", "smpd4", "vrm.gfx" -- type and PMIC
letter run together, which is also why the touch driver looks for "ldob4" rather than "ldo.b4".
So the four Wi-Fi rails are ldob15 / smpe4 / smpg4 / smpg6.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

replacements = [
    ('\t{ "ldo.b15", 1800 },    /* vdd-wlan-io, pm_humu_l15 */',
     '\t{ "ldob15", 1800 },     /* vdd-wlan-io, pm_humu_l15 */'),
    ('\t{ "smps.e4",  966 },    /* vdd-wlan-dig, pm_v6e_s4 */',
     '\t{ "smpe4",   966 },     /* vdd-wlan-dig, pm_v6e_s4 */'),
    ('\t{ "smps.g4", 1350 },    /* vdd-wlan-rfa2, pm_v6g_s4 */',
     '\t{ "smpg4",  1350 },     /* vdd-wlan-rfa2, pm_v6g_s4 */'),
    ('\t{ "smps.g6", 1900 },    /* vdd-wlan-rfa1, pm_v6g_s6 */',
     '\t{ "smpg6",  1900 },     /* vdd-wlan-rfa1, pm_v6g_s6 */'),
]
for old, new in replacements:
    assert old in s, old
    s = s.replace(old, new, 1)

s = s.replace(''' * three-command AMC vote the touch driver uses; the command DB keys come from the names of the
 * device tree's regulator nodes (rpmh-regulator-ldob15 -> ldo.b15, rpmh-regulator-smpe4 ->
 * smps.e4), and the voltages are the ones that tree asks for. */''',
              ''' * three-command AMC vote the touch driver uses. The keys are the device tree's regulator
 * node names run together -- rpmh-regulator-ldob15 becomes "ldob15", rpmh-regulator-smpe4
 * becomes "smpe4", which is the same shape as the "ldob4" the touch driver votes for. The
 * voltages are the ones that tree asks for. */''', 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('rail keys fixed')
