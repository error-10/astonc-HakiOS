#!/bin/bash
# Install the HakiOS OnePlus Ace 3 (aston) port into ../../../Mu-Silicium.
#
#   ./apply.sh          clone Mu-Silicium at BASE (shallow, submodules included) if absent,
#                       then copy files/. over the tree
#
# The copied files are the whole port:
#   files/BootShim/BootShim.S                                    XNUP payload copy to PAYLOAD_BASE
#   files/Platforms/OnePlus/astonPkg/Library/MemoryMapLib/MemoryMapLib.c
#                                                                reserve the payload DDR range
#   files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/*   XnuLoader + BDS hook
set -e
cd "$(dirname "$(readlink -f "$0")")"
MU=../../../Mu-Silicium
BASE=$(cat BASE)

if [ -d "$MU/.git" ]; then
	if [ "$(git -C "$MU" rev-parse HEAD)" != "$BASE" ]; then
		echo "apply.sh: $MU is at $(git -C "$MU" rev-parse HEAD), expected $BASE" >&2
		echo "apply.sh: remove that tree to clone it again" >&2
		exit 1
	fi
else
	echo "apply.sh: cloning Mu-Silicium ($BASE), shallow"
	git init -q "$MU"
	git -C "$MU" remote add origin https://github.com/Project-Silicium/Mu-Silicium.git
	git -C "$MU" fetch -q --depth 1 origin "$BASE"
	git -C "$MU" checkout -q FETCH_HEAD
	git -C "$MU" submodule update --init --recursive --depth 1
fi

cp -r files/. "$MU/"
echo "apply.sh: port installed into $MU"
