#!/usr/bin/env python3
"""Rewrite the working copies' absolute paths to repo-relative ones (publication staging only)."""
import pathlib
import re

D = pathlib.Path(r"C:\Users\96943\Desktop\ios\repos\astonc-HakiOS")
HEADER = ('ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)\n'
          'H=${HACKIOS_HOME:-$HOME/hackios}\n')

for p in sorted((D / "scripts").glob("*.sh")):
    s = p.read_text(encoding="utf-8").replace("\r\n", "\n")
    s = s.replace("H=/home/chenyu/hackios\n", "")
    s = s.replace("/mnt/c/Users/96943/Desktop/ios", "$ROOT")
    s = s.replace("/home/chenyu/hackios", "$H")
    s = s.replace("/home/chenyu/theos", "${THEOS:-$HOME/theos}")
    if "ROOT=$(cd" not in s:
        anchor = "set -euo pipefail\n"
        if anchor in s:
            s = s.replace(anchor, anchor + HEADER, 1)
        else:
            lines = s.split("\n", 2)
            s = lines[0] + "\n" + HEADER + (lines[1] if len(lines) > 1 else "") + "\n" + (lines[2] if len(lines) > 2 else "")
    p.write_text(s, encoding="utf-8", newline="\n")
    print("sanitized", p.name)
