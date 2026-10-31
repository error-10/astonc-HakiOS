import re

s = open('repos/Mu-Silicium/Resources/DTBs/aston.dts', encoding='utf-8', errors='ignore').read()

TARGETS = ['0x2f7', '0x2fe', '0x305', '0x307', '0x308', '0x309']

for ph in TARGETS:
    m = re.search(r'phandle = <' + ph + r'>;', s)
    if not m:
        print(ph, 'missing')
        continue
    brace = s.rfind('{', 0, m.start())
    # walk back to the line that opens this node
    line_start = s.rfind('\n', 0, brace) + 1
    header = s[line_start:brace].strip()
    block = s[brace:brace + 900]
    comp = re.search(r'compatible = "([^"]+)"', block)
    node = block[:block.find('};')] if '};' in block else block
    volts = re.findall(r'regulator-(min|max)-microvolt = <([^>]+)>', node)
    parent = ''
    pm = re.search(r'parent-supply = <([^>]+)>', node)
    print(ph, '->', header, '|', comp.group(1) if comp else '?', '|', volts, '| parent', pm.group(1) if pm else '-')
