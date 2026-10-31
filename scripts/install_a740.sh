#!/usr/bin/env bash
# Put the A740 probe (hakios.a740.c) into the kernel tree and wire it up.
#
#   bash scripts/install_a740.sh
#
# Idempotent: run it as often as you like. It edits both copies of the tree -- xnu/files,
# which is this port's source of truth, and xnu-src/xnu-8796.121.2, which is what actually
# gets compiled -- and it keeps xnu/hakios.patch in step so that a fresh clone of the
# upstream tree gets the same file.
set -euo pipefail

HACKIOS=${HACKIOS:-/home/chenyu/hackios/hackios-os}
SRC=/mnt/c/Users/96943/Desktop/ios/port/kernel/hakios.a740.c
XNU_SRC=$HACKIOS/xnu-src/xnu-8796.121.2

[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }
[ -d "$XNU_SRC" ] || { echo "missing $XNU_SRC (build the kernel once first)" >&2; exit 1; }

for tree in "$HACKIOS/xnu/files" "$XNU_SRC"; do
	echo "== $tree"
	cp "$SRC" "$tree/bsd/dev/hakios.a740.c"

	python3 - "$tree" <<'PY'
import pathlib, sys
tree = pathlib.Path(sys.argv[1])

# bsd/conf/files only exists in the full tree (xnu-src); the port's xnu/files keeps just the
# files this port touches, and its diff against upstream lives in xnu/hakios.patch.
conf = tree / "bsd/conf/files"
if conf.exists():
    text = conf.read_text()
    if "bsd/dev/hakios.a740.c" not in text:
        anchor = "bsd/dev/hakios.aston_touch.c"
        i = text.index(anchor)
        end = text.index("\n", i) + 1
        text = text[:end] + "bsd/dev/hakios.a740.c\tstandard\n" + text[end:]
        conf.write_text(text)
        print("  bsd/conf/files: added hakios.a740.c")
    else:
        print("  bsd/conf/files: already there")
else:
    print("  bsd/conf/files: not in this tree (xnu/hakios.patch carries it)")

head = tree / "bsd/sys/hakios.input.h"
text = head.read_text()
if "hakios_a740_init" not in text:
    anchor = "void hakios_aston_touch_init(void);"
    if anchor in text:
        text = text.replace(anchor, anchor + "\nvoid hakios_a740_init(void);", 1)
    else:
        text = text.rstrip("\n") + "\n\nvoid hakios_a740_init(void);\n"
    head.write_text(text)
    print("  bsd/sys/hakios.input.h: declared")
else:
    print("  bsd/sys/hakios.input.h: already declared")

inp = tree / "bsd/dev/hakios.input.c"
text = inp.read_text()
if "hakios_a740_init();" not in text:
    anchor = "\thakios_adreno_init();"
    if anchor not in text:
        sys.exit("  bsd/dev/hakios.input.c: no hakios_adreno_init() call to sit after")
    text = text.replace(anchor, anchor + "\n\thakios_a740_init();", 1)
    inp.write_text(text)
    print("  bsd/dev/hakios.input.c: called")
else:
    print("  bsd/dev/hakios.input.c: already called")
PY
done

echo "== xnu/hakios.patch"
python3 - "$HACKIOS/xnu/hakios.patch" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
text = p.read_text()
if "bsd/dev/hakios.a740.c" in text:
    print("  already there")
    sys.exit(0)
anchor = "+bsd/dev/hakios.aston_touch.c\tstandard\n"
if anchor not in text:
    sys.exit("  no aston_touch line in the patch to sit after")
text = text.replace(anchor, anchor + "+bsd/dev/hakios.a740.c\tstandard\n", 1)
old, new = "@@ -109,6 +109,42 @@", "@@ -109,6 +109,43 @@"
if old not in text:
    sys.exit(f"  hunk header {old!r} not found: fix the counts by hand")
text = text.replace(old, new, 1)
p.write_text(text)
print("  added hakios.a740.c and bumped the hunk to +43")
PY

echo "done: hakios.a740.c installed; build with ./xnu-build.sh -j8 -k"
