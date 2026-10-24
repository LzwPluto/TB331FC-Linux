# TB331FC Mainline Linux Port

把主线 Linux 移植到 **联想小新 Pad 2024（Lenovo Xiaoxin Pad 2024, TB331FC）**
—— 高通 SM6225（骁龙 685）+ INX 1200×1920 面板。

> **状态：能跑，但驱动未完成。** 显示、GPU、桌面环境已经可用；
> 触控、WiFi、蓝牙仍卡在具体的技术点上。这个仓库的目的是**把这些卡点和已有的
> 全部排查数据公开出来**，让社区一起推。

---

## 1. 设备信息

| 项目 | 值 |
|---|---|
| 型号 | Lenovo TB331FC（小新 Pad 2024） |
| SoC | Qualcomm SM6225-AD（Snapdragon 685，`khaje` 平台） |
| 面板 | INX `p255_inx`，1200×1920，90Hz（当前用 60Hz），DSC 压缩，DCS 背光 |
| 触控 | Novatek NT36523，**SPI**（`spi0.1`），PID `0x84D3` |
| WiFi/蓝牙 | Qualcomm WCN3990（WiFi 走 ath10k_snoc，蓝牙走 hci_qca over UART） |
| 存储 | UFS（65 分区，A/B 双槽） |
| 原系统 | Android（HyperOS），**A 槽全程只读，用作回滚和参照** |

---

## 2. 能用的部分 ✅

| 功能 | 状态 | 关键点 |
|---|---|---|
| **主线内核启动** | ✅ | 需要给 base DTB 补 `__symbols__` stub，否则 ABL 拒绝加载 overlay |
| **显示（原生 DSI）** | ✅ | 1200×1920 @60Hz，DSC 压缩，**必须由 host 下发标准 PPS** |
| **背光** | ✅ | DCS 控制，0–3767 可调 |
| **GPU** | ✅ | freedreno FD610，OpenGL 4.6 / GLES 3.2 |
| **桌面** | ✅ | Niri 25.11 正常出图 |
| **USB 串口控制台** | ✅ | CDC-ACM gadget → `/dev/ttyGS0`，电脑上是个 COM 口 |
| **SD 卡** | ✅ | 需要把 `cd-gpios` 极性从 ACTIVE_LOW 改成 ACTIVE_HIGH |
| **ADSP 协处理器** | ✅ | 需要 `adsp.mbn` → `adsp.mdt` 的符号链接技巧（见下） |
| **根文件系统** | ✅ | 放在 FAT32 SD 卡上的 ext4 镜像文件，losetup + switch_root |

## 3. 卡住的部分 ❌

| 功能 | 卡点 | 已排除 |
|---|---|---|
| **触控** | 固件下载时 **DLM 段回读 CRC 不符**（ILM 段完全正确） | SPI 传输可靠性、芯片识别、内存映射、固件文件、传输块大小、SPI 频率 |
| **WiFi** | `ath10k_snoc` probe 停在 iommu 之后，无固件请求、无 wiphy | 固件缺失、稳压器、ADSP 未启动 |
| **蓝牙** | 芯片对 `0xFC00` 无应答（`tx timeout`） | UART 实例、引脚 mux、serdev、hci0、4 路稳压器、电压 |
| **90Hz** | 未切换（面板原生支持） | — |

详细的排查过程、每个假设的实验结果、以及采集到的全部原始数据见
[`docs/PORTING-NOTES.zh-CN.md`](docs/PORTING-NOTES.zh-CN.md)（约 2100 行，中文）。

---

## 4. 仓库内容

```
patches/                 ← 内核补丁（GPL-2.0，已验证可干净应用）
  0001-panel-himax-hx83102.patch   p255_inx 面板 + DSC + 标准 PPS
  0002-dsi_host.patch              DSI 压缩相关
  0003-msm_mdss.patch              sm6225 关闭 UBWC（否则合成器花屏）
  0004-nt36523_ts.patch            Novatek 触控：trim ID 读取、CRC 重启检测、SPI 自检、remove 修复
  0005-nt36523.patch               触控固件传输块 63KB → 4KB

dtb/CANONICAL.dts        ← 目前可用的完整设备树（含全部修复）
dtb/*.py                 ← 一批 DTB/config 修改脚本（每个都对应一个具体问题）

initramfs/               ← 自己写的 init（C）+ gadget.sh + switchroot.sh
tools/                   ← 构建、固件提取、打包脚本

docs/PORTING-NOTES.zh-CN.md   ← 完整移植笔记（含所有实验记录）
docs/FIRMWARE.md              ← 如何从你自己的设备提取厂商固件
```

**本仓库不包含任何厂商固件二进制**（版权原因）。请按
[`docs/FIRMWARE.md`](docs/FIRMWARE.md) 从你自己的设备提取。

---

## 5. 快速上手

### 5.1 准备

* 一台 TB331FC，**A 槽原系统保持不动**（全程只写 B 槽）
* Linux 构建机（本文用的 WSL2 Ubuntu 24.04）
* 内核基线：[`linux-next-tb128fu-hx83102-panel-port`](https://github.com/)（6.14.0-rc5，
  由 tb128fu 移植项目修改而来，SM6225 同平台兄弟机型 TB128FU）

### 5.2 打补丁 + 编译

```sh
cd linux-next-tb128fu-hx83102-panel-port
for p in /path/to/repo/patches/*.patch; do patch -p1 < "$p"; done

# 关键 config（详见 tools/build_kernel.sh）
./scripts/config --enable SPI_QCOM_GENI --enable INPUT_HIMAX_V3_MMI \
                 --enable BACKLIGHT_PWM --enable VFAT_FS --enable MSDOS_FS \
                 --enable EXT4_FS --enable BLK_DEV_LOOP \
                 --enable USB_CONFIGFS --enable USB_CONFIGFS_ACM \
                 --enable CFG80211 --enable MAC80211 --enable ATH10K \
                 --enable BT --enable BT_HCIUART --enable BT_HCIUART_QCA --enable BT_QCA
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc) Image modules
```

### 5.3 生成镜像

```sh
# boot.img：未压缩 arm64 Image
python3 dtb/mkv4.py --mode boot --kernel arch/arm64/boot/Image --out boot_b.img

# vendor_boot.img：initramfs + 我们改过的 DTB + cmdline
python3 dtb/mkv4.py --mode vendor_boot \
    --vendor-ramdisk initramfs.cpio \
    --dtb dtb/CANONICAL.dtb \
    --cmdline 'console=tty0 keep_bootcon clk_ignore_unused pd_ignore_unused rdinit=/init earlycon=qcom_geni,0x4a90000 panic=10' \
    --out vendor_boot_b.img
```

### 5.4 刷机（只写 B 槽）

```sh
fastboot --set-active=b
fastboot flash boot_b        boot_b.img
fastboot flash vendor_boot_b vendor_boot_b.img
fastboot flash dtbo_b        dtbo_minimal.img   # 只需 vendor overlay 条目 {0,2}
fastboot flash vbmeta_b      vbmeta_stock.img   # 原厂 vbmeta
fastboot reboot
```

**回滚**：`fastboot --set-active=a && fastboot reboot`

---

## 6. 几个反直觉的关键发现（可能对同平台其他机型有用）

### 6.1 ABL 拒绝加载，原因不是 DTB 内容而是缺 `__symbols__`

TB331FC 的 ABL 会应用 dtbo 里的 vendor overlay，而 overlay 用
`__fixups__` 引用 base DTB 的 `__symbols__` 标签。纯主线 DTB 没有这些标签时，
overlay 应用失败 → ABL 直接拒绝启动（表现为 fastboot 卡 5 秒后自动重启）。

**解法**：在 base DTB 里加一个 `abl-stubs` 子树，塞进约 120 个空的带标签节点，
并用 `dtc -@` 重新编译，让 `__symbols__` 齐全。

### 6.2 显示花屏（满屏蓝绿网格）的根因是 **DPU 核心时钟被错误降频**

症状：fbcon 静态文字正常，任何合成器（Niri）一跑就满屏蓝绿网格。

原因链：DT 的 OPP 表写的是 200/300/383/470/560 MHz，而 dispcc 实际只支持
**19.2/192/256/307.2/384 MHz** → `clk_set_rate` 返回 `-EINVAL` → 时钟掉到最低档
**19.2 MHz** → 带不动全屏逐帧刷新。

**解法**：把 DPU 的 OPP 表**只留 384 MHz 一档**，频率被钉死。

### 6.3 DSC 面板必须由 host 主动下发标准 PPS

只靠面板初始化序列里的寄存器写是不够的。必须在 `0x11`（sleep out）**之前**
发送 `drm_dsc_pps_payload_pack()` + `mipi_dsi_picture_parameter_set()` +
`mipi_dsi_compression_mode_ext()`。缺这一步，无论怎么调 slice 参数都是花屏/半帧。

### 6.4 合成器花屏还可能是 UBWC

主线的 `sm6225-mdss` 继承了 `sm6115_data` 的 UBWC 参数（enc 1.0 / dec 2.0 /
swizzle 7），在这颗芯片上不正确。给 sm6225 单独一份 mdss data（不宣告 UBWC），
合成器就会退回线性缓冲。

### 6.5 DSP 固件：`.mdt` 伪装成 `.mbn`

厂商固件是分片格式（`adsp.mdt` + 35 个 `adsp.bNN`），而 DT 里写的是 `adsp.mbn`，
主线 `qcom_q6v5_pas` **不会自动回退**去找 `.mdt`。因为 `.mdt` 本身就是 ELF 头 +
分片索引，**建个符号链接就能加载**：

```sh
ln -sf adsp.mdt adsp.mbn
echo start > /sys/class/remoteproc/remoteproc1/state   # 无需重启
```

---

## 7. 需要帮助的地方 🙏

按"离成功最近"排序：

### 7.1 触控：DLM 段写入 CRC 不符

```
ilm: bin crc = 0xF4FD5D35, golden = 0xF4FD5D35, result = 0xF4FD5D35   ✅
dlm: bin crc = 0x49618174, golden = 0x49618174, result = 每次不同      ❌
```

* 芯片：Novatek NT36523（trim ID `17 20 00 23 65 03`，命中主线 `trim_id_table`）
* 已排除：SPI 传输（连读 20 次完全一致）、`spi-rd-fast-addr`、SPI 频率、
  传输块大小（63KB 和 4KB 都失败）、DMA、4 个原厂固件变体
* **最需要**：Novatek **SPI 版** nt36523 厂商驱动源码，用来逐行对比
  `nvt_write_sram()` / `nvt_set_page()` 的时序与 DLM 写入前后的额外命令
  （注意：Lenovo TB128FU 的厂商内核是 **I2C 版**，不能直接用）

### 7.2 蓝牙：芯片对 `0xFC00` 无应答

软件侧已全部验证正确：

```
UART 实例 4a8c000 ✅  引脚 gpio8-11/qup3 ✅  serdev ✅  hci0 ✅
稳压器 l9/l16/l17/l23 全部 enabled ✅  电压 l9=1.8 l16=1.7 l17=1.304 l23=3.2 ✅
GPIO 87 = 状态反馈脚（非使能脚）
```

* **最需要**：用示波器/逻辑分析仪看 UART 波形；或提取 Android 侧
  geni UART 控制器寄存器配置逐位对比

### 7.3 WiFi：`ath10k_snoc` probe 卡住

probe 停在 `Adding to iommu group 7` 之后，既不请求固件也不报错。
固件（`wlanmdsp.mbn` + `bdwlan.*`）已就位，ADSP 已 running。

* 怀疑：CDSP 未起来导致 WLAN 的 QMI 服务不可用
  （cdsp 加载时报 `-22 reading firmware metadata`）
* 或需要正确配置 `qcom,wlan-msa-fixed-region`

### 7.4 其它

* 切换到面板原生 90Hz
* DPU 核心时钟钉在最高频的功耗优化（应该做成按需升频）

---

## 8. 免责与法律

* 本仓库**不含任何厂商固件二进制**。`docs/FIRMWARE.md` 只提供提取脚本，
  固件需从**你自己的设备**中提取（`/vendor/firmware`、`NON-HLOS.bin`、`BTFM.bin`）。
* 内核补丁为 **GPL-2.0-or-later**；文档与脚本为 **MIT**。
* 刷机有变砖风险。**全程只写 B 槽，A 槽保持原系统不动**，这样随时可以
  `fastboot --set-active=a` 回滚。
* 本项目与联想、高通、Novatek 均无隶属关系。

---

## 9. 致谢

* [tb128fu 主线移植项目](https://github.com/) —— 提供了 SM6225 同平台的内核基线
* 所有在 Qualcomm 平台上做主线移植的开源项目（pmOS、LineageOS 主线分支等）

---

## English summary

Mainline Linux on the **Lenovo Xiaoxin Pad 2024 (TB331FC)**, Qualcomm SM6225.

**Working**: mainline kernel boot (needs `__symbols__` stubs for ABL), native DSI
display 1200×1920 with DSC (host must send the standard PPS), backlight, GPU
(freedreno FD610), Niri compositor, USB CDC-ACM serial console, SD card, ADSP
remoteproc.

**Broken**: touch (Novatek NT36523 SPI - firmware DLM segment readback CRC never
matches), WiFi (`ath10k_snoc` stalls after iommu setup), Bluetooth (chip never
answers `0xFC00` over UART despite correct pins/regulators/voltage).

Kernel patches are in `patches/` (verified to apply cleanly).
Full porting log (Chinese, ~2100 lines) in `docs/PORTING-NOTES.zh-CN.md`.
