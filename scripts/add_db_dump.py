"""Add a command-DB dump to the Wi-Fi probe.

Step 8 looked for ldo.b15 / smps.e4 / smps.g4 / smps.g6 and found none of them, so the next run
should print what the DB actually holds instead of guessing again.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

dump = r'''/* Print every key in the command DB, so the rail names can be read off the device itself
 * rather than guessed from the device tree. */
static void
db_dump(uint32_t *db, unsigned limit)
{
	const uint8_t *base = (const uint8_t *)db;
	unsigned s, i, shown = 0, total = 0;

	for (s = 0; s < 8; s++) {
		const uint8_t *d = base + 8 + s * 16;
		unsigned off = le16(d + 2), n = le16(d + 6);

		if (!le16(d) || !n || n > 512) {
			continue;
		}
		if (off + n * 24 + 32 > ASTON_DB_SIZE - 144) {
			continue;
		}
		for (i = 0; i < n; i++) {
			const uint8_t *e = base + 144 + off + 24 * i;
			char name[9];
			unsigned k;

			if (e[0] < 32 || e[0] > 126) {
				continue;
			}
			for (k = 0; k < 8; k++) {
				name[k] = (e[k] >= 32 && e[k] <= 126) ? e[k] : ' ';
			}
			name[8] = 0;
			total++;
			if (shown < limit) {
				printf("wifi: 8: db[%u] %s %08x\n", s, name, le32(e + 16));
				shown++;
			}
		}
	}
	printf("wifi: 8: command DB holds %u keys, %u shown\n", total, shown);
}

'''

anchor = '/* One three-command vote through an idle ACTIVE TCS slot'
assert anchor in s, 'vote comment not found'
s = s.replace(anchor, dump + anchor, 1)

old = '\tfor (i = 0; i < sizeof(wcn_rails) / sizeof(wcn_rails[0]); i++) {'
assert old in s, 'rail loop not found'
s = s.replace(old, '\tdb_dump(db, 120);\n\n' + old, 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('dump added')
