"""Make the command-DB dump compact.

Only the tail of the kernel log survives the trip back (about ten kilobytes), so a dump that
prints one line per key loses most of itself. Pack the regulator keys into a few long lines
instead: name and RSC address per key, twelve per line.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

start = s.index('/* Print every key in the command DB')
end = s.index('/* One three-command vote through an idle ACTIVE TCS slot')
new = r'''/* Print the regulator keys in the command DB, packed into a few lines: only the tail of this
 * log survives the trip back, so one line per key would lose most of the list. */
static void
db_dump(uint32_t *db, unsigned per_line)
{
	const uint8_t *base = (const uint8_t *)db;
	char line[256];
	unsigned s, i, total = 0, in_line = 0;

	line[0] = 0;
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

			if (!((e[0] == 'l' && e[1] == 'd' && e[2] == 'o') ||
			    (e[0] == 's' && e[1] == 'm' && e[2] == 'p'))) {
				continue;
			}
			for (k = 0; k < 8; k++) {
				name[k] = (e[k] >= 32 && e[k] <= 126) ? e[k] : ' ';
			}
			while (k > 0 && name[k - 1] == ' ') {
				name[--k] = 0;
			}
			name[8] = 0;
			snprintf(line + strlen(line), sizeof(line) - strlen(line), " %s=%05x",
			    name, le32(e + 16) >> 8);
			total++;
			if (++in_line == per_line) {
				printf("wifi: 8: db %s\n", line);
				line[0] = 0;
				in_line = 0;
			}
		}
	}
	if (in_line) {
		printf("wifi: 8: db %s\n", line);
	}
	printf("wifi: 8: command DB holds %u regulator keys\n", total);
}

'''
s = s[:start] + new + s[end:]
s = s.replace('\tdb_dump(db, 200);', '\tdb_dump(db, 12);', 1)
open(p, 'w', encoding='utf-8', newline='').write(s)
print('compact dump in place')
