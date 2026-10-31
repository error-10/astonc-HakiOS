#!/bin/bash
# Which of the kernel sources we care about are ours (not in upstream hackios)?
UP=$(ls /mnt/c/Users/96943/Desktop/ios/repos/hackios-xnu-kernel/xnu/files/bsd/dev/ 2>/dev/null)
for f in hakios.aston_wifi.c hakios.aston_pcie_phy_seq.h hakios.a740.c hakios.battery.c \
         hakios.adsp.c hakios.input.c hakios.cpufreq.c hakios.goodix.c hakios.camera.c \
         hakios.wifi.c hakios.mpss.c hakios.aston_touch.c hakios.aston_touch_hw.h; do
	if echo "$UP" | grep -qx "$f"; then
		echo "UPSTREAM $f"
	else
		echo "OURS     $f"
	fi
done
