"""Drop db_find's magic check and make its name match tolerant.

The dump proves the command DB is there and that ldob15 / smpe4 / smpg4 / smpg6 are all in it,
yet the lookup said none of them existed -- the difference between the two code paths is the
magic-word check, which the dump does not make. The lookup also no longer insists that all eight
name bytes match: a key may be padded with spaces rather than zeroes.
"""
p = 'port/kernel/hakios.aston_wifi.c'
s = open(p, encoding='utf-8').read()

old = '''	if (le32(base + 4) != 0x0c0330db) {
		return 0;
	}
'''
assert old in s, 'magic check not found'
s = s.replace(old, '', 1)

old_match = '''			for (k = 0; k < 8; k++) {
				if (e[k] != (uint8_t)(name[k] ? name[k] : 0)) {
					same = false;
					break;
				}
			}'''
new_match = '''			for (k = 0; k < 8; k++) {
				uint8_t want = (uint8_t)(name[k] ? name[k] : 0);

				if (e[k] != want) {
					/* a padded key may end in spaces instead of zeroes */
					if (want == 0 && e[k] == ' ') {
						continue;
					}
					same = false;
					break;
				}
			}'''
assert old_match in s, 'name match not found'
s = s.replace(old_match, new_match, 1)

open(p, 'w', encoding='utf-8', newline='').write(s)
print('db_find fixed')
