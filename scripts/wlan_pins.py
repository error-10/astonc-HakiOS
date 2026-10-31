import re

s = open('repos/Mu-Silicium/Resources/DTBs/aston.dts', encoding='utf-8', errors='ignore').read()

print('=== any *wlan*/*wl* gpio properties ===')
for m in re.finditer(r'[a-zA-Z0-9,._-]*wlan[a-zA-Z0-9,._-]* = <[^>]*>;', s):
    print(m.group(0))

print('=== pcie node pin props ===')
i = s.find('pcie@1c00000')
node = s[i:i + 6000]
for m in re.finditer(r'\b([a-z0-9,-]*(?:gpio|gpios|pinctrl)[a-z0-9,-]*) = ([^;]+);', node):
    print(m.group(1), '=', m.group(2))

print('=== wcnss / cnss node gpios ===')
for key in ['qcom,wcn', 'cnss', 'wcn6855', 'qca6490']:
    j = s.find(key)
    if j > 0:
        seg = s[j:j + 4000]
        for m in re.finditer(r'\b([a-z0-9,-]*gpio[a-z0-9,-]*) = ([^;]+);', seg):
            print(key, '|', m.group(1), '=', m.group(2))
        break
