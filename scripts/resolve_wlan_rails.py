"""Print the node text around each WLAN rail phandle so the names can be read off."""
import re

DT = 'repos/Mu-Silicium/Resources/DTBs/aston.dts'
text = open(DT, encoding='utf-8', errors='replace').read()

for ph in ['0x2f7', '0x2fe', '0x307', '0x309']:
    for m in re.finditer(r'phandle = <' + ph + r'>', text):
        start = text.rfind('{', 0, m.start())
        # walk back to the line that opened this node
        line_start = text.rfind('\n', 0, start) + 1
        print('==', ph, 'at', m.start())
        print(text[line_start:line_start + 320].strip())
        print()
        break
