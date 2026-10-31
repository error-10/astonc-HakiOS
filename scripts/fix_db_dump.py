"""Make the command-DB dump print every regulator-ish key, not the first 120 keys overall.

The first dump only showed the beginning of one segment, which is why the rail names still were
not visible. Print everything whose name starts with "ldo" or "smp".
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

old_filter = '''			if (e[0] < 32 || e[0] > 126) {
				continue;
			}'''
new_filter = '''			if (e[0] < 32 || e[0] > 126) {
				continue;
			}
			if (!((e[0] == 'l' && e[1] == 'd' && e[2] == 'o') ||
			    (e[0] == 's' && e[1] == 'm' && e[2] == 'p'))) {
				continue;
			}'''
assert old_filter in s
s = s.replace(old_filter, new_filter, 1)

s = s.replace('\tdb_dump(db, 120);', '\tdb_dump(db, 200);', 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('dump narrowed to regulators')
