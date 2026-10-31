#!/usr/bin/env bash
M=/home/chenyu/hackios/Mu-Silicium/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib
P=/mnt/c/Users/96943/Desktop/ios/port/devices/oneplus-aston/uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib
B=/home/chenyu/hackios/Mu-Silicium/Build/astonPkg/RELEASE_CLANGPDB/AARCH64/SiliciumPkg/Library/BootManagerLib/BootManagerLib/OUTPUT
echo "== sources"
ls -l "$M"/XnuLoader.c "$M"/BootManager.c "$P"/XnuLoader.c
echo "== md5"
md5sum "$M"/XnuLoader.c "$P"/XnuLoader.c "$M"/BootManager.c
echo "== objects"
ls -l "$B"/XnuLoader.obj "$B"/BootManager.obj
echo "== strings in XnuLoader.obj"
python3 /mnt/c/Users/96943/Desktop/ios/scripts/check_strings.py "$B"/XnuLoader.obj "XNULOADER LOG v2" "[vwdt]" "loader.efi" "rawdump" "p l o a d"
