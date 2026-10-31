# OnePlus Ace 3 (PJE110) 上的 HakiOS 移植记录

更新时间：2026-10-31 15:20 (+08:00)

本文档按时间顺序记录实测结论，包括失败的尝试。数值均来自真机日志。

## 当前进度

引导链、内核、用户态镜像全部可用，真机能进 iOS 16.5 桌面，触摸可操作。显示为软件合成，约 10 fps。

外设方面：触摸与按键可用；电池与充电部分可用，数值不准；Wi-Fi 停在 PCIe 链路层，模块无响应；
GPU 的 GX 供电域由 GMU 固件管理，宿主侧无法点亮；音频与蜂窝尚未开始。

## 已核实的事实

- Ace 3（国行 PJE110 / astonc）与 OnePlus 12R（CPH2585 / aston）为同一硬件，SoC 为 SM8550（kalama）。
- Mu-Silicium 已提供 `Platforms/OnePlus/astonPkg`，其 Status.md 记录 Display、Internal Storage、
  Side Buttons、USB Device、Mass Storage 可用，Windows 与 Linux 均可引导。
- `jiganomegsdfdf/ubuntu-oneplus-aston` 证明本机型可用 `fastboot boot` 加载外部 boot.img，
  因此不需要改动 bootloader 或分区表。
- Mu-Silicium 自带 `Resources/DTBs/aston.dtb` 与 `aston.dts`，设备树取证全部基于该文件。
- OnePlusOSS 的 `android_kernel_modules_and_devicetree_oneplus_sm8550` 中包含 `aston-23801-*`
  与 `aston-23861-*` overlay，其中 23801 对应 Ace 3，23861 对应 12R。

## 关键地址

| 项目 | 值 | 来源 |
|---|---|---|
| UEFI FD 基址 / 大小 | `0xA7100000` / `0x300000` | aston MemoryMapLib（UEFI FD 区） |
| XNUP payload 基址 | `0xE2000000`，上限 64 MB | 自行选定，避开 Trusted VM |
| Trusted VM 占用 | `0xF3800000–0xF7AFC000` | aston MemoryMapLib |
| Display_Reserved | `0xB8000000` + `0x02B00000` | aston MemoryMapLib |
| GIC dist / redist | `0x17100000` / `0x17180000` | aston.dts |
| GIC redist 步长 / 总长 | `0x40000` / `0x200000` | aston.dts |
| 帧缓冲 | `0xB8000000`，1264×2780 | UEFI GOP 实测 |
| RSC（apps） | `0x17a20000`（drv-2），TCS 偏移 `0xd00`，步长 `0x2a0` | aston.dts + 实测 |
| cmd-db | `0x81c60000` | aston.dts |
| UFS 控制器 | `0x1d84000` | aston.dts |
| 触摸 | TLMM GPIO 44/45/46/47，INT 25，RST 24，AVDD 10，IO 供电 L4B | `aston-oplus_tp-23801.dtsi` |

## 时间线

### 2026-10-28 上午：QEMU 端到端验证

用自编译的 loader、自编译的 XNU 内核与自行生成的 iOS 16.5 镜像，在 QEMU 中跑到 launchd 启动
SpringBoard。命令为 `QEMU_INSTANCE=9 ./qemu/run-ios-own3.sh 60`，日志在 `logs/qemu-own3.log`。

期间解决了 `launchd` 的 `errno 8 (ENOEXEC)` panic：loader 把常驻根镜像放在 `win_base + 0x08000000`，
payload 在 `0xE2000000` 时窗口基址为 `0xE6000000`，常驻镜像必须预载到 `0xEE000000`。
脚本原先写死 `0xFC000000`，只适用于上游 payload 位于 `0xF0000000` 的情况。修正后通过。

### 2026-10-28 中午：真机第一阶段

`fastboot boot out/boot-aston-uefi.img` 成功，屏幕显示 XnuLoader 的日志，`fastboot getvar product`
返回 `xnuloader`。随后上传 loader 与内核 payload，XNU 以 8 核启动，读到 GIC 与内存地图。

### 2026-10-28 12:09：进入 iOS 桌面

上传 2362 MB 的 system.apfs 后执行 `run --secs 600`，内核挂载 md0 作为根设备并启动 launchd，
最终进入 SpringBoard。屏幕显示 iOS 16.5 主屏，但此时触摸不可用。

### 2026-10-28 13:40：S3910 触摸调通

移植基于 `YiKongk/HackiOS-Ace5` 的 giulia S3910 驱动与 dodge 的位拆 SPI 实现。数据以位拆 SPI
（mode 0，MSB）传输，TouchComm 命令 0x20/0x06/0x24/0x26/0x25/0x05 依次完成识别与上报配置。

遇到的问题：

- 电源投票与 probe 共用变量 `rc`，供电成功把 `rc` 置 0，probe 循环未执行。改为独立的 `probe_rc`。
- L4B 需要经 RSC TCS 投票 `{1800, 1, 4}` 才能上电，`rc=0 status=0x2` 表示已通电。
- 引脚 mux 需要写 `0x2`，SPI 四线由 GPIO 44–47 位拆驱动。

调通后点击、拖动、双指缩放、边缘手势均正常，实测约 125 Hz。

### 2026-10-28 下午：SoC 地址参数化

多个驱动硬编码 redwood 的 `0x18220000`（RSC）与 `0x80860000`（cmd-db）。新增
`hakios_soc_rsc()` 与 `hakios_soc_cmd_db()`，从 boot-arg `soc_rsc`、`soc_cmd_db` 取值，
默认值保持上游数值。cpufreq、goodix、camera、wifi、adsp 五处改为调用该接口。

### 2026-10-28 晚：电池显示

loader 的 charger 路径（`battery=1`）从 UEFI 的 QcomChargerDxeLA 取电压、电流、温度与充电状态，
经共享页传给内核。真机上显示 10% 且带充电标志，而实际电量在 60% 以上，说明字段布局与换算不对。
读取到的电压值是半毫伏单位，且首次取样必须跳过。

后续增加了若干保护：连续 6 次读数不变则清空状态、电压或温度异常时不发布、`FullyCharged` 需电量
大于等于 95% 才置位、适配器回退到 charger 状态。

### 2026-10-29 至 10-30：GPU 与电量计研究

- GPU：`aston.dts` 中 `qcom,chipid = <0x43050a01>`、`gpu-model = "Adreno740v2"`、
  `compatible = "qcom,adreno-gpu-gen7-2-1"`。CX 供电域 `gpu_cc_cx_gdsc`（`GCC_GPU_CC_CX_GDSC`，
  `0x0af018`）可正常投票；GX 域 `gpu_cc_gx_gdsc` 的 `power_on` 在 mainline 中为空函数，GX 由 GMU 接管。
  宿主机写 GX 寄存器后 RBBM 读回全 0，符合 GX 未上电的表现。
  本机系统分区中有 `a740_sqe.fw`（76,724 字节）、`a740_zap.mbn`，以及 `/vendor/firmware/` 下的
  `gmu_gen70200.bin`（66,844 字节）与 `gmu_gen70e00.bin`（67,368 字节），但没有 `a740_gmu.bin`。
- 电量计：BQ28Z610 挂在 `i2c@880000`，地址 `0x55`。真机读过一次：`capacity=90`、
  `voltage_now=4283000`、`current_now=-48`、`temp=341`、`charge_full=5280000`、`charge_counter=4514000`、
  `cycle_count=5`、`status=Charging`、`health=Good`。
  ADSP 侧 `adsp.mdt` 共 59 个分段，`paddrs` 覆盖 `0x9ea00000–0xa3280000`，需要把
  `ADSP_MEMORY` 改为 `0x9ea00000`、大小改为 `0x04880000`、`MAX_SEGMENTS` 改为 64 才能加载。

### 2026-10-31：Wi-Fi 链路

控制器侧已完成：GCC 中 PCIe0 的 GDSC、分支时钟投票、复位、PHY 的 111 条初始化序列、TLMM 引脚、
TCSR 的 `pcie_0_clkref_en`（`0x15100`，bit0）、PARF 的 DBI 与路由配置。

链路状态机可以走到 DETECT_ACT：

- 未写 `PARF_LTSSM`（`0x1b0`）的 bit8（`LTSSM_EN`）时，`PARF_LTSSM` 始终为 0。
- 写入 bit8 后状态变为 `0x101`（state 1，DETECT_ACT），等待也不会进入 POLLING。释放 PERST 后至少
  需要保持 100 ms，代码中给了 2 ms 后延时加 2 s 采样。
- DBI 读到 `id 011317cb`、`link ctrl 00030120`，说明控制器作为 RC 的身份正常。
- WCN 模块的五路供电（`ldob15` 1800 mV、`smpg2` 980 mV、`smpe4` 966 mV、`smpg4` 1350 mV、
  `smpg6` 1900 mV）通过 RSC TCS 投票均返回 `rc=0`，但 SPMI 直读 PMIC 的 SMPS 寄存器显示输出为关闭，
  说明投票没有真正生效。已确认投票走的是 drv-2 的 ACTIVE TCS（`0x17a20d00`）。
- 引脚侧曾因 TLMM 基址写错（`0x0f100000`，实际为 `0x0f000000`）导致读回全 0；修正后 perst、
  clkreq、wlan_en 仍读到 0。
- `aston_wifi_only=22`（仅上电与引脚配置）会使内核在 25 秒自动交还之前挂死，导致 loader 一同失联。
  `aston_wifi_only=24`（完整流程）同样如此。

### 2026-10-31：中文界面、电源键与看门狗

中文界面。系统镜像有两处把中文丢掉了。`sysimage/select-system.py` 的 `KEEP_LANG` 只保留英文与 Base，
根文件系统里 `zh-Hans.lproj` 的数量是 0；另外 `fetch.sh` 会调 `font_trim.py` 把 PingFang 精简到
Regular 与 Semibold 两个字重，主屏图标名用的是 Medium，找不到就退回不含中文字形的字体，显示成方框。
把 `KEEP_LANG` 扩到 `zh_CN` 等目录、PingFang 保留全部 18 个字面（74.3 MB）之后重新解包并重编
`system.apfs`（2,525,704,192 字节），界面与图标名都正常。语言仍由 `userland/src/init.c` 的
`seed_language()` 在每次开机时写进 `/private/var` 的 ramfs，因为那一层每次开机都是新建的。

电源键与音量键。SM8550 的 PMIC 仲裁器是版本 7，和内核里原来那套版本 5 的实现不是一回事：APID 表在
`0x0c400000 + 0x2000`，读走 `0x0c440000` 的 observer 区（每个 APID 0x20 字节，命令字 13<<27），
写通道在 `0x0c500000`。原来的代码把 core 当成 `0x0c440000`、observer 当成 `0x0e600000`，版本检查
还会拒绝 7，所以这两个键从来没工作过。这次把一加 13 移植里对应的改动整段搬了过来，编译通过，真机上电源键与音量键均正常。

看门狗。为了排查冻屏，另外做了一个不武装 Gunyah 虚拟看门狗的 loader，`wdt_arm()` 直接返回。崩溃后
不再 60 秒自动复位，屏幕停在最后一帧，可以拍照取证。代价是死机只能长按电源。

冻屏没有解决。把电池路径关掉（`battery=0 battery_qcom=0`）跑满十分钟仍然在中途失去响应；GPU 在缺少
`/fw/a660_gmu.bin` 时不会启动，也已经排除。

## 已知问题

| 问题 | 现象 | 现状 |
|---|---|---|
| GPU GX 域 | 写 GX 寄存器后 RBBM 恒为 0 | 需要 GMU 固件与 KGSL 驱动，本机缺少 `a740_gmu.bin` |
| Wi-Fi 模块供电 | SPMI 读回输出为关闭 | RSC 投票返回成功但未生效，怀疑 mode 值与使能顺序 |
| Wi-Fi 链路 | LTSSM 停在 DETECT_ACT | 模块未上电或未响应，与上一条相关 |
| 电池数值 | 显示 10%，实际 60% 以上 | 字段布局与半毫伏换算未核对 |
| 运行中冻结 | 长时间运行后画面静止、USB 失联 | 未定位。已排除电池路径与 GPU；改用不武装看门狗的 loader 抓 panic |
| 音频 | 无声音 | 未开始，需要 ADSP、SMP2P、GLINK、QRTR |
| 蜂窝 | 无信号 | 未开始，需要 Modem、IPA 与 SIM 相关支持 |

## 开发过程中的约束

这些限制决定了调试方式，记录在此以免重复摸索。

- 一次完整的真机测试约需 5 分钟：引导 loader、上传 2362 MB 镜像（约 91 秒）、运行内核。
- 内核运行时 loader 的 USB 不可用，只能等 `--secs` 到点或长按电源 12 秒。
- 内核 console 只保留后段约 9.7 KB，`init` 之前的输出会丢失。
- 探针必须把 `--secs` 控制在 30 秒以内，让内核在进入桌面前交还控制权，否则日志取不回来。
- Gunyah 虚拟看门狗 30 秒复位，loader 每 5 秒喂狗，内核侧由 `hv_wdt_pet=1` 接续。

## 下一步

1. Wi-Fi：确认 PMIC SMPS 输出为何未开启，检查 RSC 投票的 mode 参数与使能顺序，必要时用 SPMI 直接写
   寄存器验证；然后处理模块上电与链路训练。
2. 电池：核对 charger 协议的字段布局与单位，改为从 BQ28Z610 取真实电量。
3. GPU：评估移植 GMU 固件与 KGSL 驱动的可行性，需要先确认 Gunyah 是否允许宿主访问 GX 域。
4. 音频与蜂窝暂不开始。
