#!/bin/bash
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}
# Disassemble a window of the unstripped kernel around a virtual address.
# usage: disasm.sh <kernel> <start-hex> <len-bytes>
set -e
K="$1"; START="$2"; LEN="$3"
END=$(python3 -c "print(hex(int('$START',16)+int('$LEN',16)))")
llvm-objdump -d --no-show-raw-insn --start-address="$START" --stop-address="$END" "$K"
