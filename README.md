# HakiOS for OnePlus Ace 3

把 [HakiOS](https://github.com/oosexgang/hackios-xnu-kernel) 移植到一加 Ace 3（PJE110 / astonc，SM8550 / Snapdragon 8 Gen 2）。

自编译的 XNU 内核与 iOS 16.5 用户态，通过 `fastboot boot` 全部载入内存运行，不写入任何分区。

> A port of HakiOS to the OnePlus Ace 3. The whole boot chain, XNU kernel and iOS 16.5 user space
> run from RAM after a single `fastboot boot`; no partition is written.

| | |
|---|---|
| 设备 | OnePlus Ace 3 / PJE110 / astonc（国际版 12R = CPH2585 / aston） |
| SoC | SM8550 "kalama" |
| 系统 | iOS 16.5（20F66）用户态，XNU xnu-8796.121.2 |
| 状态 | 实验性移植，可进 SpringBoard，外设仍在补 |
| 许可证 | XNU 补丁 APSL 2.0，其余 MIT |

## 仓库内容

本仓库只包含已在实机上验证到 iOS 桌面的部分：引导链（UEFI 补丁与 XnuLoader）、xnuloader 的 aston 平台实现、
触摸驱动、打包与启动脚本，以及文档。

Wi-Fi、GPU、音频和蜂窝的调试代码仍在开发中，未包含在此。按本文档操作可以复现“手机进入 iOS 桌面并可触摸操作”
这一状态；这些外设功能目前均不可用。

## 目录

- [当前状态](#当前状态)
- [引导链](#引导链)
- [硬件参数](#硬件参数)
- [环境要求](#环境要求)
- [构建](#构建)
- [真机运行](#真机运行)
- [日志与调试](#日志与调试)
- [注意事项](#注意事项)
- [排障](#排障)
- [仓库结构](#仓库结构)
- [致谢](#致谢)
- [许可证](#许可证)

## 当前状态

以下结果于 2026-10-28 在国行 PJE110 上实测得到。国际版 12R 硬件相同，但未实测。

| 功能 | 状态 | 说明 |
|---|---|---|
| UEFI（astonPkg + XnuLoader） | 可用 | 屏幕日志、内存地图，日志写入 logdump 分区 |
| xnuloader（platform_aston） | 可用 | GIC 步长补丁、`oem readlog` |
| XNU 内核 | 可用 | 8 核启动，内存映射与虚拟看门狗已处理 |
| iOS 16.5 用户态 | 可用 | 可启动至 launchd、backboardd、SpringBoard |
| 显示 | 可用 | 1264×2780，帧缓冲位于 `0xB8000000`，软件合成，约 10 fps |
| 触摸 | 可用 | Synaptics S3910，点击、拖动、双指缩放与边缘手势均正常 |
| 中文界面 | 可用 | 系统镜像需保留 `zh_CN.lproj` 与 PingFang 全部字重，否则图标名显示为方框 |
| 电源键 / 音量键 | 已移植，待验证 | PMIC 仲裁器 v7：`0x0c400000` 的 APID 表、`0x0c440000` 的 observer、`0x0c500000` 的写通道 |
| 电源 / 电池 / 充电 | 部分可用 | loader 通过 UEFI charger 协议取得电压电流，经共享页传给内核，iOS 侧电源接口已接通。固件的字段布局与半毫伏换算尚未核对，因此显示的数值有偏差。 |
| Wi-Fi / 蓝牙 | 未移植 | PCIe 控制器侧已配置完成，链路状态机停在 DETECT_ACT，模块无响应。模块几路供电在 SPMI 上读回为关闭状态，通过 RSC 投票返回成功但未生效。 |
| 音频 / 麦克风 | 未移植 | |
| GPU / Metal | 未移植 | CX 供电域可开启，GX 域由 GMU 固件管理（mainline 中 `gpu_cc_gx_gdsc` 的 `power_on` 为空函数）。从宿主侧写 GX 寄存器时 RBBM 恒读 0。本机系统分区内没有 `a740_gmu.bin`。 |
| 蜂窝 / SIM | 未移植 | |
| Apple ID / 激活 | 不支持 | 无 Secure Enclave |

冷启动到桌面约需 3.5 分钟，SpringBoard 帧率约 10 fps。触摸驱动当前仍输出诊断日志。

## 引导链

```
fastboot boot out/boot-aston-xnu.img          boot image header v4
  └─ BootShim                                 UEFI FD → 0xA7100000，XNUP payload → 0xE2000000
     └─ Mu-Silicium UEFI (astonPkg)           初始化屏幕日志、中和虚拟看门狗、跳过 BDS 存储扫描
        └─ XnuLoader                          打印 CPU/显示/内存地图，解析 XNUP，加载 loader.efi
           └─ xnuloader (platform_aston)      USB fastboot 命令，GIC 步长补丁，合成设备树
              └─ XNU (xnu-8796.121.2)         8 核启动，root = md0（内存中的 system.apfs）
                 └─ launchd → backboardd → SpringBoard
```

地址有三处不能沿用上游设置：

- UEFI FD 基址为 `0xA7100000`，大小 `0x300000`
- XNUP payload 基址为 `0xE2000000`。上游使用 `0xF0000000`，但 Aston 的 Trusted VM 占用
  `0xF3800000–0xF7AFC000`，沿用该地址会导致 UEFI 首次访问即触发异常
- GIC 的 dist 为 `0x17100000`，redist 为 `0x17180000`，步长 `0x40000`，总长 `0x200000`。内核中该步长
  硬编码为 `0x20000`，由 loader 在内存中修改 `add` 指令的立即数

## 硬件参数

| 项目 | 值 |
|---|---|
| 内存 | `0x80000000` (2 GB) + `0x880000000` (6 GB) + `0xA00000000` (16 GB) |
| CPU | 3× Silver MPIDR `0x000–0x200`，3× Gold `0x300–0x500`，2× Prime `0x600–0x700` |
| 显示 | 1264×2780，帧缓冲 `0xB8000000`（Display_Reserved） |
| 触摸 | Synaptics S3910，QUP1 SE4，TLMM GPIO 44/45/46/47，INT 25，RST 24，AVDD 10，IO 供电 L4B |
| RSC | `0x17a20000`（drv-2，TCS 偏移 `0xd00`） |
| cmd-db | `0x81c60000` |
| UFS | ufshc `0x1d84000` |
| 分区 | 存在 `logdump` 分区，loader 将内核日志写入其中 |

## 环境要求

- 已解锁 BL 的 Ace 3。本次验证的机器运行 PixelOS + SukiSU
- Windows + WSL2 Ubuntu 24.04，或原生 Linux x86-64
- 约 40 GB 可用磁盘空间
- 可访问 GitHub 与 Apple 服务器

依赖：

```bash
sudo apt install build-essential clang lld llvm nasm lz4 \
  gcc-aarch64-linux-gnu mtools dosfstools uuid-dev python3-venv p7zip-full
```

theos 与 iOS 内核头文件：

```bash
git clone https://github.com/theos/theos.git ~/theos
mkdir -p ~/theos/toolchain/linux/iphone
curl -fsSL https://github.com/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-x86_64.tar.xz \
  | tar -xJ -C ~/theos/toolchain/linux/iphone --strip-components=2
git clone --depth 1 --filter=blob:none --sparse https://github.com/theos/sdks.git /tmp/sdks
cd /tmp/sdks && git sparse-checkout set iPhoneOS16.5.sdk
mv /tmp/sdks/iPhoneOS16.5.sdk ~/theos/sdks/
```

上游源码默认放在 `~/hackios`，可用 `HACKIOS_HOME` 修改：

```bash
mkdir -p ~/hackios && cd ~/hackios
git clone --depth 1 https://github.com/oosexgang/hackios-xnu-kernel.git hackios-os
git clone --recursive https://github.com/Project-Silicium/Mu-Silicium.git
cd Mu-Silicium
git checkout 4cba43c90e02cdbefbcd9fcdbda33d2328deaec0
git submodule update --init --recursive --depth 1
```

Mu-Silicium 所使用的 commit 同时记录在 `port/devices/oneplus-aston/uefi/BASE`。完整 clone 约 5 GB。

## 构建

一条命令完成全部构建：

```bash
wsl.exe -d Ubuntu -u chenyu -- bash -lc 'bash scripts/rebuild_aston_all.sh'
```

该脚本依次执行 `build_uefi_aston.sh`、`build_loader_aston.sh`、`install_touch_aston.sh` 与
`build_kernel_aston.sh`、`build_payload_aston.sh`；若 `out/` 中缺少镜像，还会调用 `build_images_aston.sh`。
UEFI 与内核各需 8–10 分钟，结束时输出 `REBUILD_ASTON_ALL_OK`。

以下分步说明用于单独重跑某一步骤。

### 1. 获取 iOS 16.5 IPSW

```bash
cd ~/hackios/hackios-os
make fetch
```

从 Apple 服务器下载 7.4 GB 的 16.5 IPSW 并解包，产物位于 `sysimage/`，包含 rootfs 与若干 cryptex。

### 2. 生成用户态镜像

```bash
cd ~/hackios/hackios-os
REST=1 userland/build.sh
```

需要支持 APFS 的 7z，版本 23.01 及以上。产物：

| 文件 | 大小 |
|---|---|
| `userland/system.apfs` | 2,476,728,320 |
| `userland/root.apfs` | 4,194,304 |

将其复制到 `out/`，或通过环境变量指定其他位置。

### 3. 编译 UEFI

```bash
bash scripts/build_uefi_aston.sh
```

脚本把 `port/devices/oneplus-aston/uefi/files/` 中的文件应用到 Mu-Silicium 上，并创建 venv 安装
`pip-requirements.txt`。构建流程通过 Mono 运行 nasm；若系统未安装 Mono，脚本会在
`Mu_Basecore/BaseTools/Bin/mu_nasm_extdep/Linux-x86-64` 写入一份 `extdep_state.yaml`，把 `nasm` 与
`ndisasm` 软链接到系统版本。

产物为 `Build/astonPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd`，3,145,728 字节。

UEFI 侧共有四处改动：BootShim 增加把 XNUP payload 复制到 `0xE2000000` 的代码；内存地图为该 payload
预留 64 MB；XnuLoader 在 BeforeConsole 阶段初始化屏幕日志、中和虚拟看门狗并跳过 BDS 的存储扫描，
在 AfterConsole 阶段直接加载 `loader.efi`；日志写入 `logdump`。

### 4. 编译 xnuloader

```bash
python3 port/patch_hackios_loader.py     # 幂等，可重复执行
bash scripts/build_loader_aston.sh
```

补丁做以下几件事：新增 `platform_aston`；根据 GOP 的 `fb_base` 是否落在 `0xB8000000..0xBAB00000` 判断平台；
将 GIC redistributor 步长由 `0x20000` 改为 `0x40000`（指令级二进制补丁）；把 `PAYLOAD_BASE` 改为
`0xE2000000`；虚拟看门狗改为对除 QEMU 之外的平台均生效；新增 `oem readlog` 命令。

产物为 `out/loader-aston.efi`，约 68 KB。

### 5. 编译内核

```bash
bash scripts/install_touch_aston.sh
bash scripts/build_kernel_aston.sh
```

首次构建会先执行 `xnu/apply.sh` 与 `xnu-deps/setup.sh`，后者编译 mig、unifdef、tcsh 等工具，约需 15–20 分钟。
结束时可能出现 `check_all_exports` 或 `Error 2`，原因是导出符号表检查失败，不影响产物；上游 CI 同样以
`|| true` 忽略该错误。

产物为 `xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837`，
15,290,440 字节。

需要注意：`xnu-build.sh` 编译的是 `xnu-src/xnu-8796.121.2`，修改 `xnu/files` 中的文件不会自动同步，
必须先复制过去。遗漏这一步会生成不含修改的内核，导致测试结果无效。

### 6. 打包 boot.img

```bash
bash scripts/build_payload_aston.sh
```

| 文件 | 大小 | 内容 |
|---|---|---|
| `out/boot-aston-uefi.img` | 2,064,384 | 仅 UEFI，用于首次测试与排障 |
| `out/boot-aston-xnu.img` | 2,097,152 | UEFI 与 loader，配合 `ramdisk`、`run` 使用 |
| `out/boot-aston-auto.img` | 7,770,112 | 一体化镜像：loader、内核与 cmdline |

三个镜像均为 boot image header v4，kernel 部分为 gzip(BootShim + FD + XNUP payload) 后接 `aston.dtb`。

## 真机运行

先进入 ABL fastboot：关机后同时按住音量上、音量下再插入数据线。

```bash
fastboot devices
# 67ecf92e        fastboot

python port/hackios-aston.py boot-loader
# loader is up (product: xnuloader)

python port/hackios-aston.py ramdisk
# 上传 2362 MB，约 91 秒，25.7 MB/s

python port/hackios-aston.py run --secs 900
```

`--secs` 指定内核运行时长，到时后控制权交还 loader，随后可返回 Android。若需提前结束，长按电源键 12 秒。

时间上，loader 日志在数秒内出现，约 3.5 分钟进入 SpringBoard，之后触摸可用。

`run` 使用的 cmdline 固定为：

```
debug=0x8 cpus=8 rd=md0 hv_wdt_pet=1 aston_touch=1 aston_touch_ldo=1
```

其末尾会自动追加 `devices/oneplus-aston/soc.args` 中所有 `soc_*` 项。若需详细内核输出，在 `--cmdline`
中加入 `-v`，日志会输出到屏幕。

仅测试 UEFI 时使用 `boot-uefi`。

## 日志与调试

内核日志由 loader 写入 `logdump` 分区，重启后仍保留：

```bash
python port/hackios-aston.py readlog
```

该命令读取 2 MB 到 `out/logdump.log`。

内核 console 的保留缓冲区在 `init` 启动后才生效，bsd init 阶段之前的输出不会进入日志。因此触摸驱动线程
会先等待 9 秒，待 init 启动后再开始探测。

## 注意事项

以下几条都是实际遇到过的问题，修改 loader 或驱动时容易再次触发。

虚拟看门狗。Aston 的 Gunyah 虚拟看门狗在 30 秒无人喂狗后复位，禁用寄存器不可写，但 `SET_TIME` 与 `PET`
可用。loader 每 5 秒喂一次，cmdline 中的 `hv_wdt_pet=1` 用于让内核侧继续喂狗。

内核运行期间 loader 的 USB 不可用。`fastboot devices` 会显示 `????????????`，命令返回
`Write to device failed (no link)`。需等待 `--secs` 到时或长按电源。

内核日志只保留后段。`init` 之前的打印会丢失，因此无法据此观察 bsd 启动阶段。

GIC 步长。内核中硬编码为 `0x20000`，SM8550 实际为 `0x40000`。未打补丁时内核在 GIC 初始化阶段触发
external abort。loader 通过匹配 `add` 指令及其后的 `cmp` 指令定位并修改立即数。

cmd-db 越界。最初映射 128 KB 且边界检查不严格，越界读取会触发 data abort（`esr 0x96000010`）。现在映射
256 KB，并收紧了边界检查。

RSC 地址。上游驱动按 redwood 硬编码为 `0x18220000`，Aston 为 `0x17a20000`（drv-2）。写成 `0x17a00000`
会触发 external abort。

默认单核。payload 中未指定 `cpus=` 时 loader 会补上 `cpus=1`，启动速度明显下降。

触摸驱动的变量复用问题。早期版本中供电投票与 probe 共用变量 `rc`，供电成功后 `rc` 被置 0，
导致 probe 循环一次也没有执行。现在使用独立的 `probe_rc`，见 `port/kernel/hakios.aston_touch.c`。

## 排障

| 现象 | 处理 |
|---|---|
| `fastboot devices` 显示 `????????????` | 内核正在运行或已挂起。等待 `--secs` 到时，或长按电源 12 秒 |
| 屏幕画面静止，时钟不走 | 内核挂起，帧缓冲保留最后一帧。长按电源键重启 |
| 约 30 秒后自动重启 | 虚拟看门狗未被喂食，检查 cmdline 是否包含 `hv_wdt_pet=1` |
| 日志中没有触摸驱动输出 | 输出落在 init 之前的丢失窗口，驱动会先等待 9 秒 |
| 只有 `vdd_io ... rc=0`，没有 `probe mux=` | 即上文变量复用问题，检查 `probe_rc` |
| `s3910: ... header=00 00 00 00` | SPI 读回全 0。检查 L4B 投票（`rc=0 status=0x2`）、GPIO 10 以及 mux 是否为 2 |
| loader 的 fastboot 中 `fastboot boot` 报 unknown command | loader 只实现 `oem run`、`download`、`reboot`、`get_staged`、`readlog`。更换镜像需回到 ABL fastboot |
| 构建提示找不到 cctools 或 theos | 检查 `THEOS` 路径与 `~/theos/toolchain/linux/iphone` |
| 构建卡在 Mono 或 nasm 报错 | `mu_nasm_extdep` 步骤未生效，重新执行 `build_uefi_aston.sh` |

## 仓库结构

```
port/
  devices/oneplus-aston/
    soc.args                 内存映射参数，自动拼进 cmdline
    uefi/files/              打入 Mu-Silicium 的文件（BootShim、MemoryMapLib、XnuLoader）
    uefi/{apply.sh,BASE}     把这些文件应用到指定 Mu-Silicium commit
  kernel/
    hakios.aston_touch.c     S3910 触摸驱动
    hakios.aston_touch_hw.h  引脚、寄存器、RSC、cmd-db 常量
  patch_hackios_loader.py    为上游 xnuloader 增加 aston 支持（幂等）
  mkboot-aston.py            打包 boot image（header v4）
  hackios-aston.py           主机侧脚本：boot-uefi / boot-loader / ramdisk / run / readlog
scripts/                     构建、校验、打包、安装内核
docs/STATUS.md               开发记录，逐轮实测结论
```

`port/hackios-aston.py` 的默认路径均可通过环境变量覆盖：

| 变量 | 默认值 |
|---|---|
| `MKPAYLOAD` | `<repo>/repos/hackios-xnu-kernel/xnuloader/mkpayload.py` |
| `KERNEL` | `<repo>/out/mach.development.bcm2837` |
| `LOADER` | `<repo>/out/loader-aston.efi` |
| `FASTBOOT` | `fastboot` |

构建脚本识别 `HACKIOS_HOME`（默认 `$HOME/hackios`）与 `THEOS`（默认 `$HOME/theos`）。

## 致谢

- [oosexgang/hackios-xnu-kernel](https://github.com/oosexgang/hackios-xnu-kernel)、
  [hackios-xnu-userland](https://github.com/oosexgang/hackios-xnu-userland)：HakiOS 本体
- [Project-Silicium/Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium)：
  astonPkg、BootShim、aston.dtb
- [jiganomegsdfdf/ubuntu-oneplus-aston](https://github.com/jiganomegsdfdf/ubuntu-oneplus-aston)、
  `OnePlus_aston_Touch_WOA_S3910`：同机型的 `fastboot boot` 先例与触摸参考
- [UniXNU](https://github.com/UniXNU/UniXNU)、`YiKongk/HackiOS-Ace5`、
  `wuxianlin/hackios-os_devices_oneplus-dodge`：平台常量、GIC 步长补丁、虚拟看门狗处理与移植流程参考

设备树取证使用了 OnePlusOSS 的 `android_kernel_modules_and_devicetree_oneplus_sm8550`
（`aston-23801-*` overlay）以及 Mu-Silicium 的 `Resources/DTBs/aston.dtb`。

## 许可证

XNU 相关补丁遵循 Apple Public Source License 2.0，其余代码为 MIT。

仓库不包含也不分发任何 Apple 专有组件或手机固件。运行所需的 iOS 镜像需自行使用合法持有的 IPSW 在本地生成。

## 免责声明

本项目为研究性移植，不保证稳定，不提供激活，不涉及 Apple 服务。解锁 BL 会清除数据，请自行备份。
整个流程不写入分区，最坏情况是长按电源 12 秒回到 Android。
