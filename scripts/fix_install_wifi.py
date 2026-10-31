"""Teach install_aston_wifi.sh to copy the generated PHY sequence header too."""
p = 'scripts/install_aston_wifi.sh'
s = open(p, encoding='utf-8', newline='').read()

old = 'SRC=/mnt/c/Users/96943/Desktop/ios/port/kernel/hakios.aston_wifi.c'
new = (old + '\nSRC_H=/mnt/c/Users/96943/Desktop/ios/port/kernel/'
       'hakios.aston_pcie_phy_seq.h')
assert old in s, 'SRC line not found'
s = s.replace(old, new, 1)

old2 = '\tcp "$SRC" "$tree/bsd/dev/hakios.aston_wifi.c"'
new2 = (old2 + '\n\tif [ -f "$SRC_H" ]; then '
        'cp "$SRC_H" "$tree/bsd/dev/hakios.aston_pcie_phy_seq.h"; fi')
assert old2 in s, 'cp line not found'
s = s.replace(old2, new2, 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('updated')
