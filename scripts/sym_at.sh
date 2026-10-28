#!/bin/bash
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
H=${HACKIOS_HOME:-$HOME/hackios}
# Map a kernel virtual address (from a panic PC) to the nearest preceding symbol.
# usage: sym_at.sh <kernel-file> <hex-offset-from-text-base>
set -e
K="$1"; OFF="$2"
nm -n --defined-only "$K" | awk -v off="$OFF" '
BEGIN { target = strtonum("0x" off); best="" }
{
  a = strtonum("0x" $1)
  if (a <= target) best = $0
}
END { print "nearest symbol below", off, ":", best }
'
