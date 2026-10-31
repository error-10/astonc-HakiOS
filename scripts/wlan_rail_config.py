import re

s = open('repos/Mu-Silicium/Resources/DTBs/aston.dts', encoding='utf-8', errors='ignore').read()

i = s.find('vdd-wlan-rfa2-supply')
seg = s[max(0, i - 3000):i + 2000]

for m in re.finditer(r'qcom,[a-zA-Z0-9_-]*config = <[^>]+>;', seg):
    print(m.group(0))

print('---- supplies in this window ----')
for m in re.finditer(r'vdd-wlan[a-zA-Z0-9-]*supply = <[^>]+>;', seg):
    print(m.group(0))
