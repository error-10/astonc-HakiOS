"""Write make_phy_seq.py's output straight to a file as UTF-8 without a BOM.

The generator prints to stdout, and PowerShell's redirection turned that into UTF-16, which
clang refuses to read. Collecting the lines here keeps the encoding under our control.
"""
import runpy
import sys

GEN = 'scripts/make_phy_seq.py'
OUT = 'port/kernel/hakios.aston_pcie_phy_seq.h'

lines = []


class Collect:
    def write(self, text):
        lines.append(text)
        return len(text)

    def flush(self):
        pass


real = sys.stdout
sys.stdout = Collect()
try:
    runpy.run_path(GEN, run_name='__main__')
finally:
    sys.stdout = real

text = ''.join(lines).replace('\r\n', '\n')
open(OUT, 'w', encoding='utf-8', newline='\n').write(text)
print('wrote %s, %d lines, %d bytes' % (OUT, text.count('\n'), len(text.encode())))
