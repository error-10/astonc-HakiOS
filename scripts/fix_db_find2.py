"""Rewrite db_find to bound the key comparison by strlen(name).

The old loop read name[6] and name[7] past the end of a seven-byte string literal ("ldob15"), so
the eighth byte compared against whatever followed the literal in .rodata. That is why the dump --
which only reads the entry side -- could list ldob15 while the lookup insisted it was absent.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

start = s.index('/* Look a cmd-db key up and return the address its three commands live at, or 0. */')
end = s.index('/* Print the regulator keys in the command DB, packed into a few lines')
new = r'''/* Look a cmd-db key up and return the address its three commands live at, or 0. */
static uint32_t
db_find(uint32_t *db, const char *name)
{
	const uint8_t *base = (const uint8_t *)db;
	unsigned s, i, k, len = (unsigned)strlen(name);

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
			bool same = true;

			if (len > 8) {
				continue;
			}
			for (k = 0; k < len; k++) {
				if (e[k] != (uint8_t)name[k]) {
					same = false;
					break;
				}
			}
			/* the rest of the key may be zero or space padded */
			for (k = len; same && k < 8; k++) {
				if (e[k] != 0 && e[k] != ' ') {
					same = false;
				}
			}
			if (same) {
				return le32(e + 16);
			}
		}
	}
	return 0;
}

'''
s = s[:start] + new + s[end:]
open(p, 'w', encoding='utf-8', newline='').write(s)
print('db_find rewritten')
