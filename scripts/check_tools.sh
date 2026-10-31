#!/bin/bash
# Report the userland-image build toolchain state in the WSL build tree.
for t in 7z 7zz lz4 cc make python3 dtc xz unzip; do
	p=$(command -v "$t" 2>/dev/null)
	printf '%-6s %s\n' "$t" "${p:-MISSING}"
done
H="$HOME/hackios/hackios-os"
echo "--- userland/"
ls "$H/userland" 2>/dev/null | head -20
echo "--- xnu-deps host tools"
ls "$H/xnu-deps/host/bin" 2>/dev/null
echo "--- theos sdk"
ls "$HOME/theos/sdks" 2>/dev/null
echo "--- sysimage state"
ls -l "$H/sysimage" 2>/dev/null | head -20
