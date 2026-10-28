# OnePlus Ace 3 (PJE110) 上的 HakiOS 移植 — 进度

更新时间：2026-10-28 11:45 (+08:00)

## 一句话状态

**离线能验的全部通关**：UEFI 引导固件、XNUP loader、XNU 内核、boot.img、iOS 用户态镜像（root.apfs /
system.apfs）全部构建完成，并且在 QEMU 里用「我们自己的 loader + 我们自己编译的 XNU 内核 + 我们生成的
iOS 16.5 镜像」跑到了 `launchd.ios` 启动 SpringBoard 的阶段。
**下一步只剩真机 `fastboot boot`**（等手机连电脑），全程只进 RAM，不写任何分区。

## QEMU 端到端验证（2026-10-28 11:40，关键里程碑）

- 命令：`QEMU_INSTANCE=9 ./qemu/run-ios-own3.sh 60`
- 日志：`~/hackios/hackios-os/logs/qemu-own3.log`
- 证据链：`XNULOADER v3` → 平台识别 `platform qemu-virt` → 内核
  `Darwin Kernel Version 22.5.0 ... chenyu:xnu-8796.121.2`（我们编的内核）→ `root device md0` →
  `/sbin/launchd.ios` 运行（`hello from launchd.ios.1`）→
  `com.apple.SpringBoard` 服务被 launchd 导入并 elide xpcproxy。
- 对照：官方预编译 loader + 官方内核 + 同一套镜像同样跑到 SpringBoard（`logs/qemu-pristine2.log`），
  说明镜像本身没问题。
- 踩坑与结论：`launchd` 的 `errno 8 (ENOEXEC)` panic **不是** loader 的 bug。loader 把常驻根镜像放在
  `win_base + 0x08000000`；我们的 payload 在 `0xE2000000`，于是 QEMU 里内核窗口基址是 `0xE6000000`，
  常驻镜像必须预载到 `0xEE000000`（脚本原写死 `0xFC000000` 只对应官方 payload 在 `0xF0000000` 的情况）。
  修正 RD_ADDR 后一次通过。真机没有这个 QEMU 预载假设（镜像是 `xl ramdisk` 经 USB 写入窗口的）。

## 已核实的事实

- Ace 3（国行 PJE110 / astonc）= OnePlus 12R（CPH2585 / aston），SoC SM8550 (kalama)。
- Mu-Silicium 已有 `Platforms/OnePlus/astonPkg`（Status.md 记 Display/UFS/Buttons/USB Device/
  Linux+Windows Boot 全部可用）；同机型 `fastboot boot` 的先例是
  `jiganomegsdfdf/ubuntu-oneplus-aston`（boot header **v4**）。
- Mu-Silicium 自己的 `Resources/Configs/aston.toml` 给出的打包参数：
  UEFI FD base `0xA7100000` size `0x300000`、kernel `gzip` + `append_dtb = true`、
  boot image `header_version = 4`、`os_version 16.0.0 / 2026-06` —— 本移植完全照此。
- 触摸 Synaptics S3910（GENI QUP1 SE4，tlmm gpio 44-47）；UFS HC `0x1d84000`（与 redwood 相同）；
  GIC dist `0x17100000` / redist `0x17180000`（stride `0x40000`，共 `0x200000`）；
  显示保留区 `0xB8000000`。
- 分区表里**没有** logdump 分区，所以 XnuLoader 的日志按 `rawdump` / `logdump` / `oplusrawdump`
  依次尝试，并同时打到 UEFI 控制台（屏幕）。

## 已产出的东西（`out/`）

| 文件 | 大小 | 说明 |
|---|---|---|
| `SILICIUM_UEFI-aston.fd` | 3145728 | 打补丁的 Mu-Silicium UEFI（astonPkg） |
| `boot-aston-uefi.img` | 2064384 | **首测用**：BootShim + UEFI FD + aston.dtb |
| `boot-aston-xnu.img` | 2097152 | 再加 XNUP payload（loader.efi + usb）：常驻 loader |
| `boot-aston-auto.img` | 7766016 | **一次性**：loader + 内核 + cmdline（含 soc_*），`fastboot boot` 后自己跑 XNU |
| `boot-aston-full.img` | 7766016 | 与 auto 相同（旧名字，保留兼容） |
| `boot-aston-full-win.img` | 7769088 | Windows 端重打包的同一镜像（校验用） |
| `loader-aston.efi` | 68608 | xnuloader（aston 补丁版，PAYLOAD_BASE=0xE2000000） |
| `mach.development.bcm2837` | 15290096 | XNU 内核（xnu-8796.121.2，我们自己编译） |
| `root.apfs` / `system.apfs` | 4194304 / 2476728320 | iOS 16.5 用户态镜像（md1 / md0） |
| `aston.dtb` / `BootShim-aston.bin` / `ramdisk` | 821752 / 176 / 5 | boot.img 的三个输入 |
| `hakios-qemu-springboard.png` | — | QEMU 里跑到 SpringBoard 阶段的屏幕截图（如生成） |

结构校验（`port/inspect_bootimg.py` / `inspect_payload.py`）：

- 两个镜像 `ANDROID!`、header v4、os_version `16.0.0` + patch `2026-06`；
- kernel 区是 gzip，解压后依次是 BootShim（176B）、UEFI FD（0x300000）、可选 XNUP；
- gzip 流之后紧跟 821752 字节的真实 `aston.dtb`（FDT 魔数 `d00dfeed`）——`append_dtb` 约定；
- `boot-aston-xnu.img` 的 payload 里是 `loader.efi`(68608) + `usb`(2)，loader 会驻留走 USB 命令；
- `boot-aston-auto.img` 的 payload 里是 `loader.efi` + `kernel`(15290096) + `cmdline`(376)，
  cmdline 实测为：`-v hv_wdt_pet=1 bootcpu=7 cpus=8 ufs=2 soc_ipa_base=0x3e40000 … soc_ipa_fw=ipa_fws`
  （soc_* 由 `port/devices/oneplus-aston/soc.args` 自动拼入，与上游 `xl` 的做法一致）；
- 运行 payload（`port/hackios-aston.py payload`）里是 `kernel` + `cmdline`，与上游 `xl run` 一致。

## 移植补丁清单（全部在本仓 `port/` 下）

- `port/devices/oneplus-aston/uefi/files/`：BootManager.c（BeforeConsole 里 `XnuLogInit() +
  WdtNeutralize()` 并去掉存储引导项扫描；AfterConsole 直接 `XnuLoaderMain()` 跳过 BDS）、
  XnuLoader.c/h（屏幕日志 + CPU/显示/内存地图打印 + XNUP 解析 + LoadImage loader.efi + 日志写
  rawdump）、MemoryMapLib.c（在 `0xE2000000` 插 64MB `XNU Payload` 保留区）、BootShim.S（把
  XNUP 拷到 `PAYLOAD_BASE`）、BootManagerLib.inf。
- `port/patch_hackios_loader.py`：给上游 xnuloader 打 aston 补丁 —— `platform_aston`
  （GIC `0x17100000`/`0x17180000`、`gic_redist_size = 0x200000`、8 核、MPIDR `core<<8`、
  `small_cores = 0x07`）、按 GOP `fb_base` 落在 `0xB8000000..0xBAB00000`（Display_Reserved）
  选平台、GIC redistributor 步长二进制补丁（内核硬编码 `0x20000` → `0x40000`）、
  `PAYLOAD_BASE` 从 `0xF0000000` 改到 `0xE2000000`（aston 的 `0xF0000000` 落在 Trusted VM 里）、
  虚拟看门狗 `wdt_arm()` 从「只对 redwood 生效」改成「除 QEMU 外都生效」——否则 OnePlus 的
  Gunyah 看门狗约 30 秒咬一次，loader 跑完就被复位。
- `port/mkboot-aston.py`、`port/hackios-aston.py`（主机侧驱动脚本）。
- `scripts/build_port_aston.sh`、`build_loader_aston.sh`、`build_kernel_aston.sh`、
  `pack_aston_images.sh`、`build_images_aston.sh`、`qemu_validate_final.sh`（QEMU 验证辅助）。

## 真机首测步骤（等手机连上电脑）

1. 手机关机，按住 **音量下 + 电源** 进 fastboot，数据线插电脑，`fastboot devices` 看到序列号。
2. `python port\hackios-aston.py boot-uefi` —— 只写给 RAM。预期：Mu-Silicium 启动、屏幕出画面，
   XnuLoader 打印 CPU/显示/内存地图（或写进 rawdump）。这一步失败只需长按电源回 Android。
3. 通过后 `python port\hackios-aston.py boot-loader` —— 常驻 loader，`getvar product` 应为
   `xnuloader`。若 loader 没在 USB 上应答，改用 `python port\hackios-aston.py boot-auto`
   （一次性镜像，loader 自己启动内核，屏幕上看内核日志）。
4. `python port\hackios-aston.py ramdisk`（把 system.apfs 传到 RAM）→
   `python port\hackios-aston.py run --secs 60 --follow 5`（内核 + root.apfs + cmdline 跑起来，
   边跑边取日志）。
5. 看日志判断卡在哪：GIC/UFS/CPU 还是 iOS 用户态。

## 下一步（按优先级）

1. **等手机**：真机 `fastboot boot` 三级测试（UEFI → loader → XNU 内核日志）。
2. 首次拿到真机 fdt 后，用 `tools/soc-args.py` 校正 `port/devices/oneplus-aston/soc.args`
   （只有 `soc_pas_mpss` 是推断值）；并按真机日志把 cpufreq / adsp 里 `0x18220000` 的 RSC
   硬编码改成读 `soc_rsc`。
3. 之后逐项补硬件：UFS 驱动确认 → 触摸（S3910，参照 Ace 5 移植）→ 屏幕/GPU（Adreno 740，
   UniXNU 有现成驱动）→ Wi-Fi/音频/按键。

## 风险

- `fastboot boot` 可能被 ABL 的 dtbo overlay 校验拒绝（raphael issue #26 那类）；只影响镜像，
  不写分区，换镜像再试即可。
- 最坏情况是卡 UEFI 黑屏/重启：长按电源 10 秒回 Android，无损。
- OnePlus 的 Gunyah 虚拟看门狗在真机上可能比 QEMU 更凶（约 30 s），loader 已加 `hv_wdt_pet=1`
  喂狗，但第一次真机跑仍要盯「重启周期」这一现象。
- 触摸/音频/Wi-Fi/基带在 aston 上尚未移植；第一阶段目标是「UEFI 有画面 + XNU 跑到等 rootfs」。

---

## 里程碑 2（2026-10-28 12:09）：真机跑到 iOS 桌面 ✅

命令序列（手机在 fastboot）：
1. `python port\hackios-aston.py boot-loader` -> product: xnuloader
2. `python port\hackios-aston.py ramdisk` -> 2362 MB @ 25.8 MB/s（92 秒传完）
3. `python port\hackios-aston.py run --secs 600 --follow 15`

结果：
- 屏幕先是 XNU 内核日志刷屏 + Apple logo（见 out\evidence\ace3-01-kernel-log.jpg）
- 随后 **SpringBoard 起来，显示 iOS 16.5 主屏/桌面**（见 out\evidence\ace3-02-springboard.jpg）
  天气/日历小组件、FaceTime/Calendar/Photos/Mail/Notes/Reminders/Clock/News/TV/Podcasts/App Store/Maps/Health/Wallet/Settings、Dock（电话/Safari/信息/音乐）全部渲染。

即：our UEFI -> our xnuloader -> our patched XNU -> launchd/backboardd/SpringBoard 全链路在 real OnePlus Ace 3 (astonc, SM8550) 上跑通，纯 RAM、未写任何分区。

当前缺失（下一步）：触摸（无输入）、电池/充电显示、Wi-Fi、音频、GPU/Metal、蜂窝。

---

## 里程碑 3（2026-10-28 13:18）：S3910 触摸调通 ✅（用户确认点击/拖动/双指缩放手势全部正常）

驱动移植：`port/kernel/hakios.aston_touch.c` + `hakios.aston_touch_hw.h`（从 Ace 5 的 giulia_s3910 移植到
aston 的位拆 SPI：TLMM `0x0f100000`、QUP1 SE4 引脚 44/45/46/47、INT 25 / RST 24 / AVDD 10、
RSC `0x17a20000` + TCS `0xd00`、cmd-db `0x81c60000`、LDO L4B 投票）。
`scripts/install_touch_aston.sh` 把它挂进 xnu 树（`bsd/dev/hakios.aston_touch.c`、`bsd/conf/files`、
`xnu/hakios.patch`、`hakios.input.{c,h}` 的调用与声明），`scripts/build_kernel_aston.sh` 重编内核。

本次定位到的真正 bug（前几轮全在追错方向，日志已留档 `out/ld3.bin`）：
- `s39_touch_thread()` 里用一个 `rc` 同时承接「供电投票」和「probe」结果。LDO 投票成功把 `rc` 置 0，
  于是 `for (... && rc)` 的 probe 循环一次都没进 → 日志里只有
  `s3910: vdd_io (L4B) vote rc=0 status=0x2` 和 `TouchComm v1 ... build=0`、随即
  `s3910: stopped rc=-20`，看起来像 SPI/mux 不通，实际是**根本没探测**。
- 修法：`probe_rc` 独立变量、供电失败直接 `goto failed`、probe 成功后才打印固件版本。重编后一次通过。

固化（本次改动）：
- `port/hackios-aston.py` 的 `BASE_CMDLINE` 已加入 `aston_touch=1 aston_touch_ldo=1`，即普通
  `python port\hackios-aston.py run --secs 300` 就会带触摸跑。
- `out/boot-aston-auto.img` / `boot-aston-full.img` 已用新内核（`mach.development.bcm2837` 15,290,440 B）
  和带触摸参数的 cmdline 重新打包（7,770,112 B）。
- 内核：`mach.development.bcm2837` 15,290,440 B（含 `s3910: ...` 全部诊断字符串）。

复现命令（手机在 Android，关机进 fastboot）：
1. `python port\hackios-aston.py boot-loader`
2. `python port\hackios-aston.py ramdisk`（2362 MB，约 91 s）
3. `python port\hackios-aston.py run --secs 300`
4. 结束后 `python port\hackios-aston.py readlog` 可取回本轮内核日志（logdump 分区）。

已知限制（下一阶段再做）：
- 开机约 3～4 分钟（内核基线未优化），SpringBoard 10 fps（无 GPU 加速）。
- 电池/充电、Wi-Fi、音频、GPU/Metal、蜂窝、蓝牙均未移植。
- 触摸驱动仍带较多元日志；定位新问题时可保留，稳定后可降为 `aston_touch=-1` 静默。

## 从源码重编全链（一条命令）

```bash
wsl.exe -d Ubuntu -u chenyu -- bash -lc 'bash scripts/rebuild_aston_all.sh'
```

脚本按顺序串起已经逐项验证过的步骤：`build_uefi_aston.sh` → `build_loader_aston.sh` →
`install_touch_aston.sh` + `build_kernel_aston.sh` → `build_payload_aston.sh` →（缺
`out/system.apfs` 时）`build_images_aston.sh`，最后打印 `REBUILD_ASTON_ALL_OK`。每一步都可单独重跑；
UEFI 与内核各约 8～10 分钟。当前固化产物（2026-10-28 13:20 重编）：

| 文件 | 大小 | md5 / 说明 |
|---|---|---|
| `out/SILICIUM_UEFI-aston.fd` | 3145728 | 打补丁 UEFI（XnuLoader 版） |
| `out/boot-aston-uefi.img` | 2064384 | UEFI-only 冒烟镜像 |
| `out/boot-aston-xnu.img` | 2097152 | UEFI + loader（USB 常驻），配 `ramdisk`/`run` 用 |
| `out/boot-aston-auto.img` = `boot-aston-full.img` | 7770112 | 一体化：payload 里 `loader.efi`(68608) + `kernel`(15290440) + `cmdline`(408) |
| `out/mach.development.bcm2837` | 15290440 | 当前内核，md5 `14F2EC35C8F557B00BEBB347D9C44576` |
| `out/loader-aston.efi` | 68608 | platform_aston + `oem readlog` |
| `out/system.apfs` / `root.apfs` | 2476728320 / 4194304 | iOS 16.5 用户态 |
| `out/evidence/ace3-0*.jpg` | — | 真机内核日志与 SpringBoard 照片 |

触摸驱动源码在 `port/kernel/hakios.aston_touch.c` + `_hw.h`（驱动「变量复用」bug 的修复已在内），
`scripts/install_touch_aston.sh` 负责把它挂进 xnu 树；所有 aston 设备参数在
`port/devices/oneplus-aston/soc.args`（`soc_rsc=0x17a20000` 为本次修正值）。

**当前状态：到此告一段落。** 下一步按优先级：GPU/Metal（Adreno 740，参照 UniXNU）→ 电池/充电 →
Wi-Fi → 音频 → 蜂窝；另外可把开机时间（约 3.5 分钟）和 SpringBoard 帧率一起优化。
