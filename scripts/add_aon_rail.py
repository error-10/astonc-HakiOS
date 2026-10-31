"""Add the AON rail the device tree asks for and we never voted.

vdd-wlan-aon goes to pm_v6g_s2 (smpg2) at 980 mV. Without it the module's always-on domain is
dead, which looks exactly like a module that never answers on the link.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

if 'smpg2' in s:
    print('already there')
else:
    anchor = '{ "ldob15", 1800 },'
    i = s.index(anchor)
    end = s.index('\n', i) + 1
    line = '\t{ "smpg2",   980 },     /* vdd-wlan-aon, pm_v6g_s2 */\n'
    s = s[:end] + line + s[end:]
    open(p, 'w', encoding='utf-8', newline='').write(s)
    print('aon rail added')

for row in open(p, encoding='utf-8').read().split('wcn_rails[] = {')[1].split('};')[0].splitlines():
    print(row)
