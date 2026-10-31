"""Find the cmd-db style name (rpmh-regulator-*) that wraps each WLAN rail node.

cmd-db keys are derived from these node names: rpmh-regulator-ldob16 -> ldo.b16,
rpmh-regulator-smpe4 -> smps.e4.
"""
import re

DT = 'repos/Mu-Silicium/Resources/DTBs/aston.dts'
text = open(DT, encoding='utf-8', errors='replace').read()

wanted = ['pm_humu_l15', 'pm_v6e_s4', 'pm_v6g_s4', 'pm_v6g_s6']

for name in wanted:
    idx = text.find('regulator-name = "%s"' % name)
    if idx < 0:
        print(name, 'not found')
        continue
    # walk backwards to the nearest "rpmh-regulator-" node name
    before = text[:idx]
    matches = list(re.finditer(r'(rpmh-regulator-[a-z0-9]+)\s*\{', before))
    node = matches[-1].group(1) if matches else '?'
    print('%-12s %s' % (name, node))
