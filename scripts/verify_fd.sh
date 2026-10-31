#!/usr/bin/env bash
# Check that the XnuLoader hooks really made it into the BdsDxe module of the built FD.
D=/home/chenyu/hackios/Mu-Silicium/Build/astonPkg/RELEASE_CLANGPDB/FV/Ffs/6D33944A-EC75-4855-A54D-809C75241F6CBdsDxe
ls -l "$D"
for f in "$D"/*.efi; do
  echo "== $f"
  strings -a -el "$f" | grep -E 'bds|XNU|loader|vwdt|payload' | head -8
done
