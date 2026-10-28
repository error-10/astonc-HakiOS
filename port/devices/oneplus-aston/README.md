# OnePlus Ace 3 / 12R (aston, SM8550) — HakiOS port

Status: **planned / bring-up not started** (target device: OnePlus Ace 3 PJE110, ColorOS, PixelOS+SukiSU, bootloader unlocked).

## Device facts (from the phone's own vendor device tree, not guesses)

Sources: `OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8550`, branch
`oneplus/sm8550_b_16.0.0_ace_3`; commits copied to `repos/ace3-dt/` on the build host.

| Item | Value | Where it comes from |
|---|---|---|
| SoC | SM8550 (kalama), 8 cores | `oplus/aston-23801-kalama-overlay.dts` (`model = "...,aston"`, `oplus,project-id = <23801>`) |
| GIC distributor | `0x17100000`, size `0x10000` | `qcom/kalama.dtsi` `intc: interrupt-controller@17100000` |
| GIC redistributor | `0x17180000`, size `0x200000`, **stride `0x40000`** | same node, `redistributor-stride = <0x0 0x40000>` |
| GIC ITS | `0x17140000`, size `0x20000` | same node |
| UFS host controller | `ufshc@1d84000` (`ufs_mem` 0x3000), ICE `0x1d88000`, 2 lanes, ref clk 19.2 MHz | `qcom/kalama.dtsi` — **same HC_PA 0x1d84000 as the POCO X5 Pro (redwood)**, so the upstream loader constant works |
| CPUs | `cpu@0/100/200` silver (capacity 820), `cpu@300/400/500` gold (1800), `cpu@600/700` prime; MPIDR = core<<8 → `0x000..0x700`, continuous | `qcom/kalama.dtsi` cpus{} |
| Slower cores | cores 0,1,2 → `small_cores = 0x07` | capacity-dmips-mhz values |
| Display reserved | `0xB8000000` (Display_Reserved in Mu-Silicium aston MemoryMapLib; `disp_rdump_region@b8000000` in kalama.dtsi) → GOP `fb_base` is expected to be `0xB8000000`, which identifies the platform | astonPkg `Library/MemoryMapLib/MemoryMapLib.c` |
| UEFI FD window | `0xA7100000`, size `0x00300000` — identical to dodge, so BootShim can use `FD_BASE=0xA7100000 FD_SIZE=0x300000` | aston MemoryMapLib (UEFI FD entry) |
| Kernel window (ABL loads boot.img kernel here) | `0xA8000000`, size `0x10000000` | aston MemoryMapLib (Kernel entry) |
| Touch | Synaptics **S3910** over GENI QUP1 SE4 SPI; tlmm gpio 44 MISO / 45 MOSI / 46 CLK / 47 CS, functions `qup1_se4_l0..l3` | `oplus/tp/aston-oplus_tp-23801.dtsi`; WOA driver `jiganomegsdfdf/OnePlus_aston_Touch_WOA_S3910` |
| Modem/IPA | see `soc.args` | `kalama-ipa.dtsi`, `kalama.dtsi` |
| Display panel | 1264x2780 class panel; command mode; no `cont_splash` reserved region in the DT snippets we have (log must go elsewhere until proven) | `vendor/qcom/proprietary/display-devicetree/oplus/aston-23801-display-kalama-overlay.*` |

Existing UEFI support: **Mu-Silicium already has `Platforms/OnePlus/astonPkg`** (OnePlus 12R / Ace 3,
contributors Robotix + jiganomegsdfdf, state `Inactive`). `Status.md` for aston: Display ✅,
Internal Storage ✅, Side Buttons ✅, USB Device ✅, Mass Storage ✅, Windows Boot ✅, Linux Boot ✅,
USB Host ❌, USB Power Delivery ❌. A working `fastboot boot` Ubuntu image for this exact model
exists (`jiganomegsdfdf/ubuntu-oneplus-aston`, `boot.img` with `--header_version 4`), which is the
proof that `fastboot boot` works here.

## Boot chain (planned, mirrors the dodge port)

```
fastboot boot boot.img            # boot image header v4
  -> BootShim  copies UEFI FD (3 MB) to 0xA7100000, XNUP payload to 0xE2000000
  -> Mu-Silicium astonPkg UEFI
  -> AfterConsole hook: XnuLoaderMain() instead of BDS
  -> xnuloader platform_aston (fb_base 0xB8000000) builds Apple device tree, jumps to XNU
```

Open decisions / risks, in the order they must be resolved:

1. **PAYLOAD_BASE cannot be 0xF0000000** (the dodge/redwood value): on aston,
   `Trusted VM` occupies `0xF3800000..0xF7A00000` (aston MemoryMapLib) and the XNUP payload
   would land inside it. Chosen gap: `0xE1200000..0xE6440000` (TZApps Reserved ends 0xE1200000,
   HW Fence starts 0xE6440000). Plan: `PAYLOAD_BASE=0xE2000000`, `PAYLOAD_MAX=0x04000000`,
   plus a `{"XNU_Payload", 0xE2000000, 0x04000000, ...}` entry in aston MemoryMapLib.
2. **GIC redistributor stride `0x40000`**: XNU hardcodes 0x20000 (redwood has 8 cores at 0x20000).
   The loader must pass the real redistributor size and binary-patch the kernel's stride, exactly
   as the dodge port does (`gic_redist_size` field + `add ... lsl#12` / `cmp` pattern patch in
   `run_kernel()`).
3. **Watchdog**: dodge needed the virtual watchdog (`hh_virt_wdt`, SMC 0x86000005..8) neutralised
   and pet every 5 s. Whether aston has the same `hh_virt_wdt` (Gunyah) is unknown — check the
   `virt_wdt` SMC presence in the UEFI log once it boots.
4. **Touch**: adapt `hakios.dodge_touch.c` (Synaptics TCM over bit-banged SPI) to the aston pins
   above; the Linux driver in `aston-oplus_tp-23801.dtsi` + the WOA driver confirm S3910.
5. **Log channel**: dodge used the `rawdump` partition. Aston partition table still unknown —
   read it from the phone (`fastboot getvar all`, or `adb shell ls /dev/block/by-name`) before
   choosing; falling back to the UEFI console/GOP is enough for the first boot.

## Build artifacts (host: WSL2 Ubuntu 24.04, `~/hackios/`)

- `hackios-os/` — hackios-xnu-kernel (shallow clone) + theos toolchain; XNU build via
  `xnu/apply.sh` → `xnu-deps/setup.sh` → `./xnu-build.sh -j$(nproc) -k`
- `Mu-Silicium/` — UEFI, built with `python3 build_uefi.py -d aston -r RELEASE`
  → `Build/astonPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd`
- `boot.img` — assembled from BootShim + FD + XNUP payload, header v4 (script to be written here)

## Reference ports

- `wuxianlin/hackios-os_devices_oneplus-dodge` (OnePlus 13, SM8750): full boot chain + UEFI patches;
  closest OnePlus template.
- `YiKongk/HackiOS-Ace5` (OnePlus Ace 5, SM8650): touch (S3910), Adreno, RAM boot, docs in Chinese.
- `peter8889/hackios-ishtar` (Xiaomi 13 Ultra, SM8550 kalama): kalama platform constants, QEMU-only.
- `hanzi123-bilp/uefi-fuxi` (Xiaomi 13, SM8550): UEFI port precedent for kalama.
