import re

s = open('repos/Mu-Silicium/Resources/DTBs/aston.dts', encoding='utf-8', errors='ignore').read()

print('=== context around each wlan-en-gpio ===')
for m in re.finditer(r'wlan-en-gpio = <0x1f 0x50 0x00>;', s):
    seg = s[max(0, m.start() - 2600):m.start() + 900]
    status = re.findall(r'status = "([^"]+)"', seg)
    comp = re.findall(r'compatible = "([^"]+)"', seg)
    rc = re.findall(r'qcom,wlan-rc-num = <([^>]+)>', seg)
    print('--- match at', m.start(), 'status', status[-3:], 'rc', rc, 'compat', comp[-2:])
    for line in seg.splitlines()[-40:]:
        if 'gpio' in line or 'rc-num' in line or 'status' in line or 'wsa' in line:
            print('   ', line.strip())
