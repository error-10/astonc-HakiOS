import io
import re
import sys

path = sys.argv[1]
since = float(sys.argv[2])
pat = re.compile(sys.argv[3])

for line in io.open(path, encoding='utf-8', errors='replace'):
    m = re.match(r'\s*\[\s*([0-9]+)\.([0-9]+)\]:\s*(.*)', line.rstrip('\n'))
    if not m:
        continue
    t = float(m.group(1) + '.' + m.group(2))
    if t < since:
        continue
    if pat.search(m.group(3)):
        print('%.3f %s' % (t, m.group(3)))
