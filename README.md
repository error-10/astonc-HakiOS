# HakiOS for OnePlus Ace 3

把 [HakiOS](https://github.com/oosexgang/hackios-xnu-kernel) 移植到一加 Ace 3（PJE110 / astonc，SM8550 / Snapdragon 8 Gen 2）。

自编译的 XNU 内核 + iOS 16.5 用户态，经 `fastboot boot` 全部载入内存运行。不写入任何分区。

> A port of HakiOS to the OnePlus Ace 3. The whole boot chain, XNU kernel and iOS 16.5 user space
> run from RAM after a single `fastboot boot`; no partition is written.

| | |
|---|---|
| 设备 | OnePlus Ace 3 / PJE110 / astonc（国际版 12R = CPH2585 / aston） |
| SoC | SM8550 "kalama" |
| 系统 | iOS 16.5（20F66）用户态，XNU xnu-8796.121.2 |
| 状态 | 实验性移植，可进 SpringBoard，外设仍在补 |
| 许可证 | XNU 补丁 APSL 2.0，其余 MIT |

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

2026-10-28 在国行 PJE110 上验证。国际版 12R 理论上适用，未实测。

| 功能 | 状态 | 说明 |
|---|---|---|
| UEFI（astonPkg + XnuLoader） | 可用 | 屏幕日志、内存地图、日志写入 logdump |
| xnuloader（platform_aston） | 可用 | GIC 步长补丁、`oem readlog` |
| XNU 内核 | 可用 | 8 核、内存映射、虚拟看门狗 |
| iOS 16.5 用户态 | 可用 | launchd / backboardd / SpringBoard |
| 显示 | 可用 | 1264×2780 @ `0xB8000000`，软件合成约 10 fps |
| 触摸 | 可用 | Synaptics S3910，点击 / 拖动 / 双指缩放 / 边缘手势 |
| 电源 / 电池 / 充电 | 做到一半 | loader 从 UEFI 自带的 charger 栈取到读数，桥成共享页交给内核，iOS 这边的电源接口也通了。差的是把固件的字段布局和半毫伏换算上机核对一遍，所以现在显示的数字可能偏。 |
| Wi-Fi / 蓝牙 | 未移植 | |
| 音频 / 麦克风 | 未移植 | |
| GPU / Metal | 有结论，还没点亮 | CX 域能开；GX 域归 GMU 固件管（mainline 里 `gpu_cc_gx_gdsc` 的 power_on 就是个空函数），软件硬开不开，所以 RBBM 一直读 0。下一步是拉 `a740_gmu.bin`，照 `hakios.adreno.c` 的路子走 GMU。 |
| 蜂窝 / SIM | 未移植 | |
| Apple ID / 激活 | 不支持 | 无 Secure Enclave |

冷启动到桌面约 3.5 分钟，SpringBoard 约 10 fps。触屏驱动仍带诊断输出。

## 引导链

```
fastboot boot out/boot-aston-xnu.img          boot image header v4
  └─ BootShim                                 UEFI FD → 0xA7100000，XNUP payload → 0xE2000000
     └─ Mu-Silicium UEFI (astonPkg)           初始化屏幕日志、中和虚拟看门狗、跳过 BDS 存储扫描
        └─ XnuLoader                          打印 CPU/显示/内存地图，解析 XNUP，加载 loader.efi
           └─ xnuloader (platform_aston)      USB fastboot 命令，GIC 步长补丁，合成 Apple 风格设备树
              └─ XNU (xnu-8796.121.2)         8 核启动，root = md0（RAM 中的 system.apfs）
                 └─ launchd → backboardd → SpringBoard
```

三处不能照抄上游的地址：

- UEFI FD 基址 `0xA7100000`，大小 `0x300000`
- XNUP payload 基址 `0xE2000000`。上游使用 `0xF0000000`，但 Aston 的 Trusted VM 占用
  `0xF3800000–0xF7AFC000`，照抄会导致 UEFI 首次读取即异常
- GIC：dist `0x17100000`、redist `0x17180000`、步长 `0x40000`、共 `0x200000`。内核硬编码为
  `0x20000`，由 loader 在内存中修改 `add` 指令的立即数

## 硬件参数

| 项目 | 值 |
|---|---|
| 内存 | `0x80000000` (2 GB) + `0x880000000` (6 GB) + `0xA00000000` (16 GB) |
| CPU | 3× Silver MPIDR `0x000–0x200`，3× Gold `0x300–0x500`，2× Prime `0x600–0x700` |
| 显示 | 1264×2780，帧缓冲 `0xB8000000`（Display_Reserved） |
| 触摸 | Synaptics S3910，QUP1 SE4，TLMM GPIO 44/45/46/47，INT 25，RST 24，AVDD 10，IO 供电 L4B |
| RSC | `0x17a20000`（drv-2，TCS offset `0xd00`） |
| cmd-db | `0x81c60000` |
| UFS | ufshc `0x1d84000` |
| 分区 | 存在 `logdump`，loader 的内核日志写入此处 |

## 环境要求

- 已解锁 BL 的 Ace 3。本移植在运行 PixelOS + SukiSU 的机器上验证
- Windows + WSL2 Ubuntu 24.04，或原生 Linux x86-64
- 约 40 GB 空闲磁盘
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

上游源码（默认放在 `~/hackios`，可用 `HACKIOS_HOME` 覆盖）：

```bash
mkdir -p ~/hackios && cd ~/hackios
git clone --depth 1 https://github.com/oosexgang/hackios-xnu-kernel.git hackios-os
git clone --recursive https://github.com/Project-Silicium/Mu-Silicium.git
cd Mu-Silicium
git checkout 4cba43c90e02cdbefbcd9fcdbda33d2328deaec0
git submodule update --init --recursive --depth 1
```

Mu-Silicium 的 commit 记录在 `port/devices/oneplus-aston/uefi/BASE`。检出体积约 5 GB。

## 构建

完整流程由 `scripts/rebuild_aston_all.sh` 串起：

```bash
wsl.exe -d Ubuntu -u chenyu -- bash -lc 'bash scripts/rebuild_aston_all.sh'
```

顺序为 `build_uefi_aston.sh` → `build_loader_aston.sh` → `install_touch_aston.sh` +
`build_kernel_aston.sh` → `build_payload_aston.sh`，缺少镜像时再执行 `build_images_aston.sh`。
UEFI 与内核各需 8–10 分钟，结束时打印 `REBUILD_ASTON_ALL_OK`。

以下为各步说明。

### 1. 获取 iOS 16.5 IPSW

```bash
cd ~/hackios/hackios-os
make fetch
```

从 Apple 服务器下载 7.4 GB 的 16.5 IPSW 并解包，产出 `sysimage/` 下的 rootfs 与各 cryptex。

### 2. 生成用户态镜像

```bash
cd ~/hackios/hackios-os
REST=1 userland/build.sh
```

需要支持 APFS 的 7z（23.01 及以上）。产出：

| 文件 | 大小 |
|---|---|
| `userland/system.apfs` | 2,476,728,320 |
| `userland/root.apfs` | 4,194,304 |

复制到 `out/`，或通过环境变量指定路径。

### 3. 编译 UEFI

```bash
bash scripts/build_uefi_aston.sh
```

脚本将 `port/devices/oneplus-aston/uefi/files/` 套用到 Mu-Silicium，建立 venv 并安装
`pip-requirements.txt`。构建流程依赖 Mono 运行 nasm，若环境无 Mono，脚本会在
`Mu_Basecore/BaseTools/Bin/mu_nasm_extdep/Linux-x86-64` 下写入 `extdep_state.yaml`
并将 `nasm`、`ndisasm` 链接到系统版本。

产物：`Build/astonPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd`，3,145,728 字节。

在该 UEFI 中我们做了四件事：BootShim 增加将 XNUP payload 复制到 `0xE2000000` 的代码；
内存地图为 payload 预留 64 MB；XnuLoader 在 BeforeConsole 初始化屏幕日志、中和虚拟看门狗、
跳过 BDS 存储扫描，AfterConsole 直接加载 `loader.efi`；日志写入 `logdump` 分区。

### 4. 编译 xnuloader

```bash
python3 port/patch_hackios_loader.py     # 幂等，可重复执行
bash scripts/build_loader_aston.sh
```

补丁内容：新增 `platform_aston`；按 GOP `fb_base` 落在 `0xB8000000..0xBAB00000` 识别平台；
GIC redistributor 步长由 `0x20000` 改为 `0x40000`（指令级二进制补丁）；`PAYLOAD_BASE` 改为
`0xE2000000`；虚拟看门狗处理改为对 QEMU 以外的平台生效；新增 `oem readlog`。

产物：`out/loader-aston.efi`，约 68 KB。

### 5. 编译内核

```bash
bash scripts/install_touch_aston.sh
bash scripts/build_kernel_aston.sh
```

首次构建会执行 `xnu/apply.sh` 与 `xnu-deps/setup.sh`，后者需编译 mig、unifdef、tcsh 等
工具，耗时 15–20 分钟。构建末尾可能出现 `check_all_exports` / `Error 2` 报错，属导出符号表
检查，不影响产物，上游 CI 同样以 `|| true` 处理。

产物：`xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837`，
15,290,440 字节。

### 6. 打包 boot.img

```bash
bash scripts/build_payload_aston.sh
```

| 文件 | 大小 | 内容 |
|---|---|---|
| `out/boot-aston-uefi.img` | 2,064,384 | 仅 UEFI，首测与排障 |
| `out/boot-aston-xnu.img` | 2,097,152 | UEFI + loader，配合 `ramdisk` / `run` |
| `out/boot-aston-auto.img` | 7,770,112 | 一体化：loader + 内核 + cmdline |

镜像为 boot image header v4，kernel = gzip(BootShim + FD + XNUP payload) + aston.dtb。

## 真机运行

手机进入 ABL fastboot（关机，音量上+下同时按住后插线）：

```bash
fastboot devices
# 67ecf92e        fastboot

python port/hackios-aston.py boot-loader
# loader is up (product: xnuloader)

python port/hackios-aston.py ramdisk
# 上传 2362 MB，约 91 秒，25.7 MB/s

python port/hackios-aston.py run --secs 900
```

`--secs` 指定内核运行时长，到点后控制权交还 loader 并回到 Android。需要提前结束时长按电源
12 秒。

时间线：数秒内出现 loader 日志，约 3.5 分钟进入 SpringBoard，随后触摸可用。

`run` 使用的 cmdline 固定为：

```
debug=0x8 cpus=8 rd=md0 hv_wdt_pet=1 aston_touch=1 aston_touch_ldo=1
```

其后自动追加 `devices/oneplus-aston/soc.args` 中的全部 `soc_*` 参数。需要详细内核输出时在
`--cmdline` 中显式追加 `-v`，注意日志会直接绘制到屏幕上。

仅测试 UEFI 时使用 `boot-uefi` 命令。

## 日志与调试

内核日志由 loader 写入 `logdump` 分区，重启后仍然存在：

```bash
python port/hackios-aston.py readlog
```

读取 2 MB 到 `out/logdump.log`。

内核 console 的保留窗口从 `init` 启动开始。在 bsd init 阶段打印的内容不会进入日志，因此触摸
驱动线程先等待 9 秒，待 init 启动后再探测。

## 注意事项

以下问题在移植过程中实际出现过，修改 loader 或驱动时容易再犯。

**虚拟看门狗。** Aston 的 Gunyah 虚拟看门狗约 30 秒未喂则复位。禁用寄存器不可写，但
`SET_TIME` 与 `PET` 可用，loader 每 5 秒喂一次，cmdline 中 `hv_wdt_pet=1` 与之对应。

**内核运行期间 loader 的 USB 不可用。** 此时 `fastboot devices` 显示 `????????????`，命令报
`Write to device failed (no link)`。等待 `--secs` 到点或长按电源。

**内核日志窗口。** 只有 `init` 之后的日志会被保留，早期打印会被丢弃。

**GIC 步长。** 内核硬编码 `0x20000`，SM8550 为 `0x40000`。若不修补，内核在 GIC 初始化阶段
触发 external abort。loader 通过匹配 `add` 指令及其后的 `cmp` 定位并修改立即数。

**cmd-db 越界。** cmd-db 映射最初为 128 KB，边界检查不严导致 data abort（`esr 0x96000010`）。
现映射为 256 KB 并收紧边界。

**RSC 地址。** 内核驱动沿用 redwood 的 `0x18220000`，Aston 为 `0x17a20000`（drv-2）。使用
`0x17a00000` 会触发 external abort。

**默认单核。** payload 未指定 `cpus=` 时 loader 会追加 `cpus=1`，启动明显变慢。

**触摸供电投票与 probe 的变量复用。** 早期版本中两者共用一个 `rc`，供电成功将其置 0，导致
probe 循环未执行。现使用独立的 `probe_rc`，见 `port/kernel/hakios.aston_touch.c`。

## 排障

| 现象 | 处理 |
|---|---|
| `fastboot devices` 显示 `????????????` | 内核运行中或已挂死；等待 `--secs` 或长按电源 12 秒 |
| 屏幕静止，时钟不走 | 内核挂死，帧缓冲保留最后一帧；长按电源 |
| 约 30 秒后自动重启 | 虚拟看门狗未被喂；检查 cmdline 是否含 `hv_wdt_pet=1` |
| 日志中没有触摸驱动输出 | 打印位于 init 之前的窗口；驱动会先等待 9 秒 |
| 仅有 `vdd_io ... rc=0`，无 `probe mux=` | 变量复用的历史 bug；检查 `probe_rc` |
| `s3910: ... header=00 00 00 00` | SPI 读回全 0；检查 L4B 投票（`rc=0 status=0x2`）、GPIO 10、mux 是否为 2 |
| loader 的 fastboot 中 `fastboot boot` 报 unknown command | loader 仅实现 `oem run/download/reboot/get_staged/readlog`；换镜像需回到 ABL fastboot |
| 构建时提示找不到 cctools / theos | 检查 `THEOS` 路径及 `~/theos/toolchain/linux/iphone` |
| 构建卡在 Mono 或 nasm 报错 | `mu_nasm_extdep` 处理未生效；重新执行 `build_uefi_aston.sh` |

## 仓库结构

```
port/
  devices/oneplus-aston/
    soc.args                 内存映射参数，自动拼入 cmdline
    uefi/files/              打入 Mu-Silicium 的文件（BootShim、MemoryMapLib、XnuLoader）
    uefi/{apply.sh,BASE}     将上述文件套用到指定 Mu-Silicium commit
  kernel/
    hakios.aston_touch.c     S3910 触摸驱动
    hakios.aston_touch_hw.h  引脚、寄存器、RSC、cmd-db 常量
  patch_hackios_loader.py    为上游 xnuloader 添加 aston 支持（幂等）
  mkboot-aston.py            打包 boot image（header v4）
  hackios-aston.py           主机侧脚本：boot-uefi / boot-loader / ramdisk / run / readlog
scripts/                     构建、校验、打包、内核安装
docs/STATUS.md               开发日志，逐轮实测结论
```

`port/hackios-aston.py` 支持环境变量覆盖默认路径：

| 变量 | 默认 |
|---|---|
| `MKPAYLOAD` | `<repo>/repos/hackios-xnu-kernel/xnuloader/mkpayload.py` |
| `KERNEL` | `<repo>/out/mach.development.bcm2837` |
| `LOADER` | `<repo>/out/loader-aston.efi` |
| `FASTBOOT` | `fastboot` |

构建脚本使用 `HACKIOS_HOME`（默认 `$HOME/hackios`）与 `THEOS`（默认 `$HOME/theos`）。

## 致谢

- [oosexgang/hackios-xnu-kernel](https://github.com/oosexgang/hackios-xnu-kernel)、
  [hackios-xnu-userland](https://github.com/oosexgang/hackios-xnu-userland)：HakiOS 本体
- [Project-Silicium/Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium)：
  astonPkg、BootShim、aston.dtb
- [jiganomegsdfdf/ubuntu-oneplus-aston](https://github.com/jiganomegsdfdf/ubuntu-oneplus-aston)、
  `OnePlus_aston_Touch_WOA_S3910`：同机型的 `fastboot boot` 先例与触摸参考
- [UniXNU](https://github.com/UniXNU/UniXNU)、`YiKongk/HackiOS-Ace5`、
  `wuxianlin/hackios-os_devices_oneplus-dodge`：平台常量、GIC 步长补丁、虚拟看门狗处理、
  移植流程范本

设备树取证来自 OnePlusOSS 的 `android_kernel_modules_and_devicetree_oneplus_sm8550`
（`aston-23801-*` overlay）与 Mu-Silicium 的 `Resources/DTBs/aston.dtb`。

## 许可证

XNU 相关补丁遵循 Apple Public Source License 2.0，其余代码为 MIT。

本仓库不包含、也不分发任何 Apple 专有组件或手机固件。运行所需的 iOS 镜像必须由使用者使用
自己合法持有的 IPSW 在本地生成。

## 免责声明

研究性移植，不保证稳定性，不提供激活或 Apple 服务，不用于绕过任何授权或版权保护。
解锁 BL 与相关操作会清除数据，请自行备份并承担风险。本移植不写入任何分区，最坏情况为长按
电源 12 秒回到 Android。
