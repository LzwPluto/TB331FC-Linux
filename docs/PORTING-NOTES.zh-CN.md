# TB331FC Mainline Linux —— 已验证可启动的完整配方

> 状态：**用户态稳定运行**（`[init] alive #N uptime=Xs` 持续累加，无崩溃无重启）
> 日期：2025-10-22
> 设备：Lenovo 小新 Pad 2024 / TB331FC / SM6225-AD (khaje) / 8+128 / 11" 1200x1920

---

## 一、三个分区分别刷什么

| 分区 | 内容 | 构建命令 |
|---|---|---|
| `boot_b` | 主线内核（**未压缩** Image，GKI v4 头） | `mkv4.py --mode boot --kernel ref_Image_padded` |
| `init_boot_b` | **空 cpio**（占位，避免和 vendor_ramdisk 重复） | `mkv4.py --mode init_boot --ramdisk tiny_ramdisk.cpio` |
| `vendor_boot_b` | **vendor_ramdisk = 我们的 initramfs** + dtb = 带 stubs 的主线 DTB + 我们自己的 cmdline | `mkv4.py --mode vendor_boot --vendor-ramdisk initramfs_q.cpio --dtb ref_dtbargs.dtb --cmdline <见下>` |
| `dtbo_b` | 原厂 dtbo 里**只保留条目 {0,2}** | `mkdtbo.py --src fw\dtbo.img --entries 0,2` |
| `vbmeta_b` | **原厂** vbmeta（自制零 descriptor 的会被硬拒） | `fw\vbmeta.img` |

---

## 二、cmdline（vendor_boot 头部）

```
console=tty0 keep_bootcon nomodeset ignore_loglevel loglevel=8
clk_ignore_unused pd_ignore_unused rdinit=/init
earlycon=qcom_geni,0x4a90000 androidboot.hardware=qcom panic=10
```

各参数作用：
- `nomodeset` —— 不让 KMS 驱动接管
- `clk_ignore_unused pd_ignore_unused` —— **关键**，否则内核会关掉 ABL 留下的显示时钟/电源域，屏幕变黑
- `rdinit=/init` —— 用 initramfs 里的 init
- **不要写 `root=`**，也**不要写 `noinitrd`**

---

## 三、DTB 必须做的四件事（缺一不可）

### 1. 补 `__symbols__`（最关键，`abl-stubs`）
TB331FC 的 ABL 会把原厂 dtbo 的 overlay 应用到基础 DTB 上，而 overlay 通过
`__fixups__` 按标签名引用节点，libufdt 靠基础 DTB 的 `__symbols__` 解析。
主页 DTB 没有这些符号 → overlay 应用失败 → **ABL 拒启**。

做法：导出 dtbo 条目 #0/#2 需要全部符号（共 **120 个**），在主线 DTS 里加一个
`abl-stubs` 子树，每个符号一个空节点并显式给唯一 phandle，用 **`dtc -@`** 编译：

```
tools\overlay_needs.py                     # 导出符号表 -> dump\symbols.txt
tools\add_stubs.py <dts> <symbols.txt> <out.dts>   # 生成 abl-stubs 子树（phandle 从 max+0x100 起）
dtc -@ -I dts -O dtb -o out.dtb out.dts
```
验证：`__symbols__` 条目数 == 120，零缺失。

### 2. 删掉 `/chosen/bootargs` 里的 `noinitrd` 和 `root=/dev/sda18`
TB128FU 的 DTB 自带
`bootargs = "root=/dev/sda18 rw rootwait noinitrd init=/sbin/init console=tty0 PMOS_NOSPLASH"`
**`noinitrd` 会让内核完全忽略 initramfs**，`root=` 又会让它空等不存在的分区。
（可原地改写：新串更短，用 0 填充，**绝对不要改变长度**，否则整个 FDT 偏移错位）

### 3. 修 framebuffer 几何
`/chosen/framebuffer@5c000000`：`reg = <0 0x5c000000 0 0x8ca000>`，
`width=1200`、`height=1920`、`stride=4800`、`format="a8r8g8b8"`。
（控制台会显示 `Console: ... 150x125`，说明 simpledrm 已接管）

### 4. 禁用两个会抢显示的驱动
- `display-subsystem@5e00000`（mdss）→ `status = "disabled"`
- `clock-controller@5f00000`（dispcc）→ `status = "disabled"`

否则主线 msm 驱动会接管显示但从 simpledrm 手里抢走 fb，表现为**白屏/黑屏有背光**。
工具：`tools\disable_node.py <in.dts> <out.dts> "<节点头>"`

---

## 四、initramfs

用**静态** aarch64 二进制，不用 busybox：
```
aarch64-linux-gnu-gcc -static -O2 -o init init_quiet.c
mkdir root && cp init root/init && (cd root && find . | cpio -o -H newc) > initramfs_q.cpio
```
**必须放在 `vendor_ramdisk`（vendor_boot）里，不能只放 init_boot。**
原因：原厂 `vendor_ramdisk` 是 **LZ4 压缩**的 cpio，ABL 把
`vendor_ramdisk + init_boot ramdisk` 拼起来交给内核，内核只解第一层压缩，
后面明文的 cpio 会被丢弃 → 找不到 `/init` → `VFS: Unable to mount root fs`。

---

## 五、ABL 判定信号（调试时看这个）

| 现象 | 含义 |
|---|---|
| ~5.3 s 回 fastboot | **ABL 拒绝** |
| 4.06 s 回 fastboot + `unbootable: yes` | vbmeta 缺 descriptor（硬拒） |
| 进 **900E**（Qualcomm HS-USB Diagnostics） | ABL 接受、内核启动（原厂内核时） |
| 屏幕出企鹅/日志 | 内核在跑 |

---

## 六、当前已知未完成项

| 项 | 状态 | 备注 |
|---|---|---|
| `sync_state() pending due to abl-stubs` | ⚠️ 副作用 | stub 被当成 consumer，阻塞 sync_state；可尝试去掉 `abl-stubs` 父节点的 `compatible` |
| 背光 | ❌ `/sys/class/backlight` 为空 | 面板能出图，但亮度不可控 |
| 触控 | ❌ 未绑定 | 内核里 himax 驱动已加载，但 DTB 缺 HX83102 的 SPI 节点 |
| 持久根文件系统 | ❌ 仅 initramfs | 需要放 rootfs 到分区或在 initramfs 里装完整系统 |
| WiFi / 音频 / 电池 | ❌ | 后续 |
| 面板驱动 | ❌ 只用 simpledrm | 要真正 90Hz/背光/DSC 需写 DSI panel 驱动 |

---

## 七、安全回滚

```
fastboot --set-active=a && fastboot reboot     # 秒回 HyperOS，A 槽从未被写入
```
B 槽 retry 耗尽后 ABL 会自动回落 A 槽（设计好的保护）。
若进 900E：**拔 USB → 长按电源 30–40 秒 → 按住音量下插 USB**。

---

# 附录：第二轮 —— 用户态 / SD 卡 / 脚本通道

## A. SD 卡能用了：卡检测极性

`mmc@4784000` 的 `cd-gpios` 极性必须改成 **ACTIVE_HIGH**（flag=0）：

```
旧（TB128FU）: cd-gpios = <0x28 0x58 0x01>;   ← 一直认为没卡
新（本机需要）: cd-gpios = <0x28 0x58 0x00>;
```

依据：厂商 overlay #2 的 `fragment@10`（target = sdhc_2）给的是 `<&tlmm 0x58 0x00>`。

改完 dmesg 立刻出现：

```
mmc0: new high speed SDHC card at address 0001
mmcblk0: mmc0:0001 AS1C 7.28 GiB
mmcblk0: p1
```

## B. 文件系统挂不上 → 用原始扫描取脚本

`mount()` 对 `/dev/mmcblk0p1` 返回 **errno=14 (EFAULT / Bad address)**，
不是缺 vfat 驱动。不要在这上面纠缠。

**解决办法（已实现，可靠）**：`init` 直接扫原始块设备前 64 MiB，
找标记对 `TB331FC-SCRIPT-BEGIN` / `TB331FC-SCRIPT-END`，
把中间内容写进 `/tmp/run.sh` 再执行。完全不依赖任何文件系统驱动。

于是得到**免刷机迭代通道**：

```
1. 电脑上编辑 SD 卡根目录的 run.sh（必须带上面两个标记行）
2. 卡插回平板
3. 重启平板
4. 屏幕上直接看到脚本输出
```

## C. 已确认可用的硬件

| 部件 | 状态 | 证据 |
|---|---|---|
| UFS | ✅ | sda..sdf、sde1..sde65 全枚举 |
| SD 卡 | ✅ | mmcblk0 / mmcblk0p1，7.28 GiB |
| 显示（simpledrm） | ✅ | 控制台 150x125，稳定不闪 |
| 电池电量计 | ✅ | `/sys/class/power_supply/bq27541-0` |
| 温区 | ✅ | thermal_zone0/1/10/11/12 |
| USB 控制器 | ✅ | xhci bus1/bus2 注册成功，dr_mode=host 生效 |
| 稳压器 | ✅ | 全表可读，vbus_p1 = enabled |

## D. 明确卡住的三处（下一步）

### D1. 触控 HX83102
- `spi@4a80000` 是 `status="okay"`，里面 `touchscreen@0` 用 `compatible = "himax,hxcommon"`
- dmesg: `SPI driver himax_tp has no spi_device_id for himax,hxcommon`
- 中断表里**没有任何 SPI 中断** → 驱动没真正接管
- 待查：驱动期望的 compatible 是什么；`vdd-supply`/pinctrl 是否解析成功
- 另注：DTB 里 `himax,panel-coords = <0 0x4b0 0 0x7d0>`（1200x2000，TB128FU 的值），
  本机面板是 1200x**1920**，需要改成 `0x780`

### D2. 背光
- `pm6125_pwm` 在我们的 DTB 里**只是 abl-stubs 中的占位节点**，没有真实 PWM 节点
- `/sys/class/pwm` 和 `/sys/class/backlight` 都是空的
- 待做：在 PMIC 下补真实 PWM 节点（SPMI 基址 0xc000 一类），再做 backlight 节点引用它

### D3. USB 取电（插键盘没电）
- 本机 USB-C 由 **rt1711h**（TCPC，i2c）管理，我们的 DTB 里是 **rt1715**，型号不匹配
- `vbus_p1` 这个 fixed regulator 已 `enabled`，但键盘仍无电 → 它不是真实 VBUS 开关
- 待做：把 i2c 节点 compatible 改成 `richtek,rt1711h`，恢复使能，走 tcpm + role-switch

## E. 仍然不可用的

WiFi（wcn3990）、音频、面板 DSI 驱动（现在只有 simpledrm）、摄像头、指纹。

## F. 当前镜像清单（B 槽）

| 分区 | 文件 |
|---|---|
| boot_b | `build\v4_boot_b.img`（主线内核） |
| init_boot_b | `build\init_boot_empty.img`（空 cpio 占位） |
| vendor_boot_b | `build\vb_v11.img`（initramfs: init + busybox + diag.sh，DTB 已含全部修复） |
| dtbo_b | `build\dtbo_02.img`（只含条目 0,2） |
| vbmeta_b | 原厂 `fw\vbmeta.img` |

DTB 修复链（`ref_cd_final.dtb` 之前的来源）：
`ref.dts` → 补 pmic-id → 加 120 个 abl-stubs 符号 → 禁 mdss → 禁 dispcc →
去 abl-stubs 的 compatible → 改 bootargs（去 noinitrd/root=）→ dr_mode=host →
禁 rt1715 → vbus_p1 always-on → **cd-gpios 极性改为 0**

---

# 附录：第三轮 —— 外设的天花板是"内核配置"，不是 DTB

## 决定性证据

`run.sh` 探针结果：

```
geni-spi platform driver: 0
geni-spi name match     : geni_i2c geni_se_qup qcom_geni_serial
spi_master count        : 0
modules                 : 0          (/proc/modules 为空，/lib/modules 为空)
```

**这个内核没有编译 GENI SPI 控制器驱动**（`CONFIG_SPI_GENI_QCOM` 未启用，
或编成模块但我们没有 modules）。所以 `spi@4a80000` 永远不会注册 `spi_master`，
触控设备也就永远不会创建 —— **和 DTB 无关，改 DTB 无用**。

平台驱动列表里同样没有 LPG PWM（背光需要），WiFi 需要的 wcn3990 相关驱动也未确认。

## 结论

这个内核是 `6.14.0-rc5-next-20250306-tb128fu+`，是给 **TB128FU** 裁的配置。
TB128FU 的触控可能走 I2C，所以 SPI 控制器驱动被关掉了。

**已经拿到的东西与内核配置无关，全部有效**：
ABL 放行、内核启动、simpledrm 显示、UFS、SD 卡、脚本通道、电池/温区、USB host 模式。

**卡住的东西都是驱动不存在**：SPI 触控、PWM 背光、WiFi、DSI 面板。

## 下一步的三个选项

### A. 自己编译内核（正路，推荐）
拉 postmarketOS 的 `linux-lenovo-tb128fu` 源码，打开需要的配置：

```
CONFIG_SPI_GENI_QCOM=y        # 触控（himax on SPI）
CONFIG_PWM_QCOM_LPG=y         # 背光
CONFIG_ATH10K / WCN3990 相关   # WiFi
CONFIG_DRM_MSM=y              # 以后做面板驱动
```
交叉编译 aarch64（WSL 里 `aarch64-linux-gnu-` 工具链已就绪），
产出 Image + modules，打进 initramfs。

耗时：1–2 小时（主要是首次全量编译）。

### B. 补模块（快，前提是有构建产物）
如果能拿到**同一版本内核构建**的 `/lib/modules/6.14.0-rc5-.../`（例如 TB128FU 的
pmOS 镜像或 kernel 包），把需要的 `.ko` 放进 initramfs 再 `insmod` 即可。
10 分钟的事，但需要那个具体版本的模块文件。

### C. 换路径
触控改走 I2C（需硬件确认本机触控是否同时连了 I2C）；背光用 GPIO 直控。
不确定性高，且面板 DSI 驱动仍然缺。

## 交付物清单（截至第三轮）

| 文件 | 作用 |
|---|---|
| `WORKING-BOOT-RECIPE.md` | 完整可复现配方 + 三轮发现 |
| `rootfs/run.sh` | 卡上自动执行的探针脚本（免刷机迭代） |
| `rootfs/busybox` | aarch64 静态 busybox |
| `build/vb_*.img` | 各阶段 vendor_boot（当前可用：`vb_spi.img`） |
| `initramfs/init_v5.c` | init 源码（挂载、原始扫描、诊断、shell） |
| `tools/*.py` | dtbo/mkv4/FDT/overlay 分析工具链 |

---

# 附录：第四轮 —— 自编译内核（SPI/触控已通到最后一米）

## A. 内核源码与构建

来源：`C:\Users\Pluto\Desktop\linux-next-tb128fu-hx83102-panel-port.zip`
（291.7 MB / 94,393 文件，内核 **6.14.0-rc5**，与设备上跑的版本完全一致）

解压到 WSL 内部 ext4（`~/kbuild/`，不要在 /mnt 下编译）：

```sh
unzip -q -o /mnt/c/Users/Pluto/Desktop/linux-next-...zip
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- tb128fu_defconfig
```

**关键改动**（`/mnt/d/TB331FCLinux/tools/build_kernel.sh` 已固化）：

| 配置 | 原值 | 改为 | 原因 |
|---|---|---|---|
| `SPI_QCOM_GENI` | `=m` | **`=y`** | 否则没有 spi_master，触控永远绑不上 |
| `INPUT_HIMAX_V3_MMI` | `=m` | **`=y`** | 触控驱动 |
| `BACKLIGHT_PWM` | `=m` | **`=y`** | 背光 |
| `VFAT_FS`/`MSDOS_FS`/`EXFAT_FS` | `=m` | **`=y`** | 挂 SD 卡 |
| `USB_CONFIGFS`/`ACM` | — | **`=y`** | USB 串口 gadget 控制台 |
| `DEBUG_INFO_BTF` | `=y` | `=n` | 省掉 pahole 依赖，编译更快 |

编译实测：`make -j10 Image` 约 **3 分 19 秒**（24 核 / 9 GB WSL）。
产物：`arch/arm64/boot/Image`，约 37.5 MB，arm64 magic `41524d64`。
打包：`mkv4.py --mode boot --kernel Image-new --out boot_newkernel.img` → 刷 `boot_b`。

## B. 结果：SPI 与触控驱动全部打通

```
spi_master : spi0
spi_devices: spi0.0 -> himax_tp [BOUND]
input names: "gpio-keys"          ← 触控还没注册成输入设备
```

注意 **SPI 是异步探测**，脚本要等几秒再看，否则会误判为"没有 spi_master"。

## C. 触控为什么还不行：TDDI 依赖显示

himax 驱动日志：

```
[HXTP] DT->bus_type=SPI
[HXTP] DT->himax,irq-gpio = 80, himax,rst-gpio = 86
[HXTP] IC_DATA:max_x/y : 0 0, 1200 2000
[HXTP] hx83102_pin_reset: Now reset the Touch chip.
[HXTP] hx83102_sense_off: Check enter_save_mode data[0]=FF   （重复，全是 0xFF）
[HXTP][ERROR] hx83102_chip_detect:hx83102_sense_off Fail!
[HXTP][ERROR] himax_chip_common_init: chip detect failed!
```

`data[0]=FF` = 总线上没有芯片应答。

为什么：`TB128FU.md` 原文——
> The HX83102 is a **TDDI**: bringing the display-driver up is **required** for the
> himax touch controller (SPI) to be detected.

**触控是触显一体，显示部分不初始化，触控侧就不应答。** 这是硬件依赖，无法绕开。

补充：driver 里那个 "panel must already be registered" 的门槛**已被主线移植移除**
（只喂给一个从未被读取的 `himax_active_panel`），所以触控驱动本身不拦，是芯片不应答。

## D. 最后一块拼图：p255_inx 面板驱动

目标：让 mdss + DSI 面板驱动真正点亮这块屏，从而同时解决显示与触控。

现成材料：

1. **原厂面板初始化序列**：`tb331fc_stock.dts` 中
   `qcom,mdss_dsi_panel_p255_inx_fhd_video` 节点，含
   `qcom,mdss-dsi-on-command` / `off-command` / 时序 / 电压。
2. **主线面板驱动框架**：`drivers/gpu/drm/panel/panel-himax-hx83102.c`
   已支持 7 种面板（boe,hx83102p-2k / boe,nv110wum-l60 / csot,pna957qt1-1 /
   ivo,t109nw41 / kingdisplay,kd110n11-51ie / starry,2082109qfh040022-50e /
   starry,himax83102-j02），结构为 `mode + desc + init sequence`。
3. 本机面板参数：**1200 x 1920**（`qcom,mdss-dsi-panel-width/height` = 0x4b0 / 0x780），
   90 Hz，INX。

要做的：新增 `lenovo,p255-inx` 条目，把原厂 init sequence 翻译进驱动；
DTB 里把 `display-subsystem@5e00000`（mdss）和 `clock-controller@5f00000`（dispcc）
重新打开，面板节点指向新 compatible。

风险：mdss 一旦接管，simpledrm 的消费级控制台会消失。回退办法：刷回
`vb_spi.img`（mdss 禁用版）+ `v4_boot_b.img` 即可恢复当前可用状态。

## E. 当前可回退的两个稳定状态

| 状态 | boot_b | vendor_boot_b | 特点 |
|---|---|---|---|
| A（最稳） | `v4_boot_b.img` | `vb_v11.img` | 原厂内核 + simpledrm 控制台 + 脚本通道 |
| B（最新） | `boot_newkernel.img` | `vb_spi.img` 或 `vb_v11.img` | 自编译内核，SPI/触控驱动已内置 |

---

# 附录：第五轮 —— USB 串口控制台（调试体验质变）

## A. USB CDC-ACM gadget 控制台

改动三处：

1. **内核配置**（已内置）：`USB_CONFIGFS=y`、`USB_CONFIGFS_ACM=y`、`USB_GADGET=y`、
   `USB_DWC3=y`、`USB_DWC3_QCOM=y`、`USB_DWC3_DUAL_ROLE=y`、`USB_F_ACM=y`
2. **DTB**：`usb@4ef8800` 的 `dr_mode` 由 `"host"` 改为 **`"peripheral"`**
   （主机模式取不到 VBUS；设备模式由 PC 供电，反而可靠）
3. **init**：执行 `/gadget.sh` 配置 configfs，然后在 `/dev/ttyGS0` 上 fork 一个 shell

结果：Windows 直接识别为 **`USB 串行设备 (COM3)`**，
`PNPDeviceID = USB\VID_1D6B&PID_0104&MI_00`（Linux Foundation Composite Gadget）。

## B. 从电脑直接操作平板

`tools/tty.ps1`（因执行策略限制，需用 `-ExecutionPolicy Bypass` 调用；
命令通过环境变量传，避免引号问题）：

```powershell
$env:TTYCMD = 'ls /sys/class/spi_master'
$env:TTYWAIT = '2000'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\TB331FCLinux\tools\tty.ps1
```

**从此不再需要拍照。** 这是整个项目效率提升最大的一步。

## C. 触控失败的最终定位

实测状态：

| 对象 | 状态 | 含义 |
|---|---|---|
| `spi0` / `spi0.0` | 存在，绑定 `himax_tp` | SPI 与驱动都正常 |
| `l9`（触控 VDDIO） | **enabled 1.8 V** | IO 供电正常 |
| `gpio86`（触控 reset） | **out high** | 复位已释放 |
| `gpio82`（面板 enable） | **out high** | 面板使能已拉高 |
| `gpio80`（触控 IRQ） | in low，无中断 | 芯片没在报点 |
| SPI 读回 | **恒为 0xFF** | 总线上没有芯片驱动 MISO |

并且稳压器表里**没有任何面板模拟电源**（`lab`/`ibb`/`vsp`/`vsn` 不存在）——
这些是 mdss 驱动面板时才会打开的。

**结论**：HX83102 是 TDDI，触控部分的模拟供电来自面板；
面板不初始化，触控芯片就不应答。**触控与显示是同一件事，必须一起做。**

（注：himax 驱动里那个 "panel 必须已注册" 的门槛已被主线移植移除，
所以不是驱动在拦，是芯片真的没电/没初始化。）

## D. TLMM GPIO 编号对照

`/sys/kernel/debug/gpio` 里 `gpiochip0` 的 GPIO 号 = **512 + TLMM 引脚号**。
例如 TLMM 82（面板 enable）对应 sysfs 的 gpio 594。

需要 `mount -t debugfs none /sys/kernel/debug` 才能看 `/sys/kernel/debug/gpio`。

## E. 下一步：p255_inx 面板驱动（触控/背光/显示的总开关）

已知：

- 本机面板：**INX p255_inx，1200 x 1920，90 Hz**
- 原厂初始化序列在 `tb331fc_stock.dts` 的
  `qcom,mdss_dsi_panel_p255_inx_fhd_video` 节点（on/off command、时序、电压）
- 主线驱动 `panel-himax-hx83102.c` 已有 7 个面板条目可参照，结构为
  `drm_display_mode + hx83102_panel_desc + init sequence`
- 需要同时在 DTB 里打开 `display-subsystem@5e00000`(mdss) 与
  `clock-controller@5f00000`(dispcc)，并把面板节点 compatible 指向新条目

风险：mdss 接管后 simpledrm 控制台会消失。但**现在有 USB 串口控制台兜底**，
屏幕黑掉也不影响调试，风险大幅降低。

---

# 附录：第六轮 —— p255_inx 面板驱动（面板点亮了！）

## A. 做法：忠实回放原厂初始化序列

原厂 `qcom,mdss-dsi-on-command` 是 Qualcomm DSI 命令缓冲，格式为：

```
[dtype][last][vc][ack][wait_ms][len_hi][len_lo][payload ...]
dtype 0x39 = generic long write
dtype 0x15 = dcs write + 1 参数
dtype 0x05 = dcs write 无参数
```

工具链：

| 工具 | 作用 |
|---|---|
| `tools/extract_panel.py` | 从 stock DTS 提取面板节点参数与命令数组 |
| `tools/gen_panel_c.py` | 转成 C 数组 `p255_inx_init.h`（**309 条命令，字节精确**） |
| `tools/add_p255_inx.py` | 往 `panel-himax-hx83102.c` 注入 replay + init + mode + desc + of_match |
| `tools/panel_dt.py` | DTB：打开 mdss/dispcc，面板 compatible → `lenovo,p255-inx` |

面板参数（原厂 p255_inx）：

```
1200 x 1920 @ 90Hz, 24bpp
hfp=96 hbp=96 hpw=4   vfp=56 vbp=248 vpw=2   -> 1396 x 2226
背光 = bl_ctrl_dcs（走 DCS 0x51，不需要 PWM）
朝向 = 180
```

驱动里新增的 mode：

```c
.clock = 279675, .hdisplay = 1200, .hsync_start = 1296, .hsync_end = 1300,
.htotal = 1396, .vdisplay = 1920, .vsync_start = 1976, .vsync_end = 1978,
.vtotal = 2226,
```

## B. 结果：面板驱动完全绑定

```
msm_dpu 5e01000.display-controller: bound 5e94000.dsi (ops dsi_ops)
msm_dpu 5e01000.display-controller: bound 5900000.gpu (ops a3xx_ops)
[drm] Initialized msm 1.12.0 for 5e01000.display-controller on minor 1
[drm] fb0: msmdrmfb frame buffer device

/sys/class/drm              -> card1  card1-DSI-1  renderD128
card1-DSI-1/status          -> connected
card1-DSI-1/modes           -> 1200x1920
card1-DSI-1/enabled         -> enabled
/sys/bus/mipi-dsi/devices   -> 5e94000.dsi.0 -> panel-himax-hx83102
/sys/class/backlight        -> 5e94000.dsi.0  brightness=3767/3767
/dev/fb0                    -> msmdrmfb  1200x1920
```

**309 条厂商初始化命令全部执行成功，无一条报错**，背光拉满，simpledrm 已退出。

## C. 现存问题 1：图像滚动/花屏（DPU 时钟）

```
msm_dpu: _opp_config_clk_single: failed to set clock rate: -22
[dpu error] failed to set core clock rate 300000000
```

原因：**mdss 节点没有 `operating-points-v2`**，`dev_pm_opp_set_rate()` 返回 -EINVAL，
DPU 只能跑 ABL 留下的默认频率 → 带宽不足 → 欠载 → 滚动/花屏。

修法：给 `display-subsystem@5e00000` 加一张 OPP 表，引用 dispcc 的
`DISP_CC_MDSS_MDP_CLK`（0x70 的某个 index），列出 200/300/345/430 MHz 等档位。

## D. 现存问题 2：触控仍不应答

即使 DSI 已 enabled、面板已初始化，重新 bind 触控驱动后仍是：

```
[HXTP] hx83102_sense_off: Check enter_save_mode data[0]=FF
[HXTP][ERROR] hx83102_chip_detect:hx83102_sense_off Fail:
```

推测：显示时序错误导致面板 IC 未真正进入正常工作状态，触控侧仍不响应。
**先修好 DPU 时钟/图像稳定，再回来看触控** —— 两者很可能是同一个根因。

## E. 另一个缺失：GPU 固件

```
msm_dpu: Direct firmware load for qcom/a630_sqe.fw failed with error -2
```

需要从原厂 `NON-HLOS.bin` / vendor 分区提取
`a630_sqe.fw`、`a610_zap.mdt` 及其段文件，放进 initramfs 的 `/lib/firmware/qcom/`。
（不装也能出 2D 画面，但 Niri 需要 GLES，所以最终必须补上。）

## F. 可回退状态

| 状态 | boot_b | vendor_boot_b | 屏幕表现 |
|---|---|---|---|
| 面板版（当前） | `boot_panel.img` | `vb_panel.img` | 1200x1920 出图但滚动 |
| 稳定控制台版 | `boot_newkernel.img` | `vb_v11.img` | simpledrm 文字控制台稳定 |
| 原厂内核版 | `v4_boot_b.img` | `vb_v11.img` | 同上（原厂内核） |

**USB 串口控制台在所有状态下都可用**（前提是 DTB 里 `dr_mode=peripheral`），
所以屏幕状态不影响调试。

---

# 附录：第七轮 —— DSC 与显示链路的最后一段

## A. 发现：面板是 DSC 压缩面板

原厂 p255_inx 节点带完整 DSC 参数（之前忽略了）：

```
qcom,compression-mode      "dsc"
qcom,mdss-dsc-version      1.1 (0x11)
qcom,mdss-dsc-bit-per-pixel     8
qcom,mdss-dsc-bit-per-component 8
qcom,mdss-dsc-slice-width       600
qcom,mdss-dsc-slice-height      20
qcom,mdss-dsc-slice-per-pkt     2
qcom,mdss-dsi-lane-map          0123（4 lane）
物理尺寸                        147 x 235 mm
```

**不做 DSC 压缩，面板就会把未压缩流当压缩流解码 → 花屏+滚动。**
这就是"滚动"的真正原因。

## B. 驱动里补上 DSC

`tools/add_dsc.py` 给 `panel-himax-hx83102.c` 增加了：

- `struct drm_dsc_config dsc` 成员
- `has_dsc` 描述符标志
- probe 里填充 DSC 参数并 `dsi->dsc = &ctx->dsc`
- 启动日志确认：`panel-himax-hx83102 5e94000.dsi.0: DSC enabled: 600x20 slices, 8 bpp`

**效果：滚动消失**，但图像仍有"文本与花屏混杂"，`block_pred_enable` true/false 都无改善。

## C. 关键新证据：DPU 扫描的不是 /dev/fb0

```
/dev/fb0            name=msmdrmfb
virtual_size        1200,1920
stride              4864        ← 1216*4，有 64 字节对齐填充
bits_per_pixel      32
```

**往 /dev/fb0 写 9 MB 全零，屏幕毫无变化**（仍显示启动日志+花屏）。
`devmem 0x5C000000` 读回 `0xFF000000`（全黑），也不是屏幕内容。

结论：DPU 实际扫描输出的内存 / 或者显示根本不刷新，与 fb0 不一致。
可能的根因：

1. **DPU 时钟设不上去**：`_opp_config_clk_single: failed to set clock rate: -22`
   → `dev_pm_opp_set_rate` 失败 → 带宽不足 → 帧不完整/不刷新（**最可疑**）
2. 显示用 IOMMU（`iommus = <0x30 0x420 0x02 ...>`）映射异常，扫描地址错位
3. fbdev 的 dumb buffer 未真正提交给 CRTC

## D. 下一步实验（按性价比排序）

1. **给 DPU 补 OPP 表**：在 `display-controller@5e01000`（`kms->pdev`）上提供
   `operating-points-v2`，包含 200/300/345/430 MHz 档位，让 DPU 能真正跑到 300 MHz。
2. **验证 fb0 是否被扫描**：安装 `libdrm` + `modetest`，直接提交一帧测试图案；
   若图案正确显示，则问题只在 fbcon/内容刷新，不在链路。
3. **检查 IOMMU**：确认 mdss 的 `iommus` 与 SMMU 域映射正确。
4. 对照实验：把面板 compatible 临时改回 `boe,hx83102p-2k`（TB128FU 已知可用配置），
   若同样花屏则问题在 DPU 层，若变正常则问题在我们的 panel/时序/DSC 配置。

## E. 设备当前可用性

- **USB 串口控制台稳定可用**（COM3，`tools/tty.ps1`）
- 屏幕：面板点亮、背光满、1200x1920 模式，图像花屏混杂且不刷新
- 触控：SPI 与驱动绑定正常，但芯片读回恒 0xFF
- 可随时回退到 `boot_newkernel.img` + `vb_v11.img`（simpledrm 文字控制台，稳定）

---

# 附录：第八轮 —— 显示打通！（slice_per_pkt 是最终钥匙）

## A. 决定性修复：slice_per_pkt = 2

主线 msm DSI 驱动写死了 **每个 DSI 包只装 1 个 DSC slice**，源码里明确写着：

```c
/* drivers/gpu/drm/msm/dsi/dsi_host.c */
bytes_per_pkt = dsc->slice_chunk_size;   /* * slice_per_pkt; */
...
/*
 * Since the current driver only supports slice_per_pkt = 1,
 * pkt_per_line will be equal to slice per intf for now.
 */
pkt_per_line = slice_per_intf;
...
/* TODO: Expand mipi_dsi_device struct to hold slice_per_pkt info */
wc = msm_host->dsc->slice_chunk_size + 1;
```

而 p255_inx 厂商配置是 **`qcom,mdss-dsc-slice-per-pkt = <2>`**。
打包节奏不一致 → 面板解码器按错误的边界重组 slice → **每帧只有一部分被正确更新，
其余停留在旧内容**（表现为"白色块 + 旧日志文字交错"）。

修复（`tools/add_slice_per_pkt.py`）：

```c
bytes_per_pkt = dsc->slice_chunk_size * 2;          /* 原：* 1 */
pkt_per_line  = slice_per_intf * 2;                 /* 原：= slice_per_intf */
wc            = dsc->slice_chunk_size * 2 + 1;      /* 命令模式路径 */
```

**验证方法（很干净）**：把 `/dev/fb0` 整个填 0（`dd if=/dev/zero of=/dev/fb0 bs=65536`，
142 块 ≈ 9.3 MB），屏幕立刻变成**纯黑** → 整帧传输正常。

> 注：修复前的对照实验里，往 fb0 填白只会让屏幕顶部一小块变白，
> 其余仍是旧日志 —— 这正是"帧不完整"的特征，是定位此 bug 的关键证据。

## B. 完整的面板参数（p255_inx）

```
1200 x 1920, 24bpp
时序（当前用 60Hz）: hfp=96 hbp=96 hpw=4 / vfp=56 vbp=248 vpw=2 -> 1396 x 2226
  90Hz: .clock = 279675   60Hz: .clock = 186473
DSC : version 1.1, bpp=8, bpc=8, slice 600x20, slice_count=2, slice_per_pkt=2
背光: bl_ctrl_dcs（DCS 0x51），brightness 0..3767
朝向: 180
物理: 147 x 235 mm
```

驱动里 `dsi_populate_dsc_params()` 会覆盖 `convert_rgb=1`、`line_buf_depth=bpc+1=9`
并计算 RC 参数，**但不改 slice 尺寸**，所以 slice 参数必须由面板驱动给对。

## C. 显示链路的最终状态

```
/sys/class/drm/card1-DSI-1/status  = connected
/sys/class/drm/card1-DSI-1/modes   = 1200x1920
/sys/class/drm/card1-DSI-1/enabled = enabled
/sys/bus/mipi-dsi/devices/5e94000.dsi.0 -> panel-himax-hx83102
/sys/class/backlight/5e94000.dsi.0  brightness=3767/3767
/dev/fb0  msmdrmfb 1200x1920 stride=4864 32bpp
```

写入 framebuffer → 屏幕立即正确显示。**原生 DSI 面板驱动已打通。**

## D. 仍然遗留

1. **DPU 核心时钟**：`_opp_config_clk_single: failed to set clock rate: -22`
   （`clk_set_rate(DISP_CC_MDSS_MDP_CLK, 300MHz)` 返回 EINVAL，
   虽然频率表里有 300MHz、分支也带 CLK_SET_RATE_PARENT）。目前不影响出图，但影响性能。
2. **触控**：SPI/驱动/引脚/供电全对，芯片读回恒 0xFF —— TDDI 的触控侧仍未应答。
3. **GPU 固件** `a630_sqe.fw` / `a610_zap.*` 缺失（Niri 需要 GLES）。

---

# 附录：第九轮 —— 显示彻底打通（标准 DSC PPS 是最后一环）

## A. 最终修复：把标准 DSC PPS 发给面板

之前所有尝试都缺了这一步。参考驱动（`panel-raydium-rm692e5.c`）在 prepare 里会做：

```c
drm_dsc_pps_payload_pack(&pps, &ctx->dsc);
mipi_dsi_picture_parameter_set_multi(&dsi_ctx, &pps);
mipi_dsi_compression_mode_ext_multi(&dsi_ctx, true,
                                    MIPI_DSI_COMPRESSION_DSC, 0);
```

**我们没有做**，只依赖面板自己那几条寄存器 → 面板解码器拿不到完整的压缩参数
→ 无论怎么调 slice/时序都只解出花屏或半帧。

最终实现（`tools/add_pps.py`）：

1. 把厂商 309 条初始化序列**在 `0x11`(sleep out) 之前截断**执行
2. 发送标准 PPS + 打开 DSI 压缩模式
3. 再执行剩下的 `0x11` / `0x29`

```c
static int lenovo_p255_inx_init(struct hx83102 *ctx)
{
	size_t pos = 0;
	if (ctx->desc->has_dsc) {
		p255_inx_replay_range(ctx, p255_inx_on_seq, sizeof(p255_inx_on_seq),
				      &pos, true /* stop before 0x11 */);
		drm_dsc_pps_payload_pack(&pps, &ctx->dsc);
		mipi_dsi_picture_parameter_set_multi(&dsi_ctx, &pps);
		mipi_dsi_compression_mode_ext_multi(&dsi_ctx, true,
						    MIPI_DSI_COMPRESSION_DSC, 0);
	}
	return p255_inx_replay_range(ctx, p255_inx_on_seq,
				     sizeof(p255_inx_on_seq), &pos, false);
}
```

**结果：显示完全正常。**

## B. 排查过程中排除掉的因素（都验证过无效或不必要）

| 试过 | 结果 | 结论 |
|---|---|---|
| 关闭 DSC + 厂商序列 | 半帧 | 面板需要 DSC |
| DSC + slice_per_pkt=1 | 半帧 | 打包节奏不对 |
| DSC + slice_per_pkt=2（`pkt_per_line=4`） | 全黑 | 参数算错 |
| DSC + slice_per_pkt=2（`pkt_per_line=1`） | 半帧 | 仍缺 PPS |
| slice_height 40 | 全花 | 厂商值 20 才对 |
| 90 / 60 / 30 Hz | 完全无差别 | 不是带宽问题 |
| BOE / CSOT / IVO / KingDisplay / Starry 五个现成面板 | 都不匹配 | 色彩/伽马不对 |
| 跳过 0x90/0x91/0x92（DSC 寄存器） | 灰屏 + 花字 | 面板确实要 DSC |
| **发送标准 PPS** | **完全正常** | ★ 正解 |

**教训**：DSC 面板必须由 host 显式下发 PPS，不能依赖面板初始化序列里的寄存器写。
"BLOCK 级花屏 / 半帧" 是 PPS 缺失的典型症状。

## C. 最终可用的显示配置

```
面板        ：lenovo,p255-inx（INX，1200x1920，还原厂商 309 条初始化序列）
模式        ：1200x1920 @ 60Hz（.clock = 186473，htotal 1396 / vtotal 2226）
DSC         ：开启，1.1，8bpp/8bpc，slice 600x20，slice_count 2，slice_per_pkt 1
背光        ：DCS 控制（0x51），brightness 0..3767
驱动        ：panel-himax-hx83102 + msm DPU/DSI，无 simpledrm
framebuffer ：/dev/fb0  msmdrmfb  1200x1920  stride 4864  32bpp
```

DTB 需同时满足：`mdss` 与 `dispcc` 打开、面板 compatible = `lenovo,p255-inx`、
cmdline **不带 `nomodeset`**。

## D. 当前镜像（B 槽，全部可用）

| 分区 | 文件 | 说明 |
|---|---|---|
| `boot_b` | `build\boot_pps.img` | 自编译内核 + 完整 p255_inx 面板驱动 |
| `vendor_boot_b` | `build\vb_panel3.img` | initramfs_v12 + `ref_panel_final.dtb` |
| `init_boot_b` | `build\init_boot_empty.img` | 空占位 |
| `dtbo_b` | `build\dtbo_02.img` | 仅条目 0,2 |
| `vbmeta_b` | 原厂 `fw\vbmeta.img` | — |

## E. 仍然遗留

1. **触控**：SPI/引脚/供电/驱动全对，芯片读回恒 0xFF。面板已完全初始化仍不应答，
   需要单独排查（可能 TB331FC 的触控 SPI 引脚与 TB128FU 不同，或需要触控固件
   `Himax_firmware.bin`）。
2. **GPU 固件**：`qcom/a630_sqe.fw`、`a610_zap.*` 缺失（Niri 需要 GLES）。
3. **DPU 核心时钟 OPP**：`clk_set_rate(...,300MHz)` 返回 -22，不影响出图但影响性能。

---

# 附录：第十轮 —— 显示验证通过

## A. 几何测试图案验证结果

用「148 个 `#` 满宽横线 + `R001`~`R078` 带行号 + 完整字母表」的图案验证：

- ✅ `TOP-LEFT` 在起始位置，`BOTTOM-RIGHT END` 在末尾
- ✅ `#` 横线正好铺满，左右无空缺、无溢出
- ✅ 行号与字母表完整、文字锐利
- ✅ 无重影、无色彩偏移、无横竖条纹、无块状伪影

**显示功能完全正常。**

## B. 画面旋转 90° 是正常的

面板原生扫描方向是 **1200x1920（竖屏）**，而平板按 1920x1200 横屏使用，
所以画面天然旋转 90°。处理方式：

| 场景 | 做法 |
|---|---|
| 桌面环境（Niri 等） | 合成器读 DRM 的 panel orientation 属性自动旋转，无需干预 |
| 文字控制台（fbcon） | 需要 `CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y` + cmdline `fbcon=rotate:1` |

当前内核 **`CONFIG_FRAMEBUFFER_CONSOLE_ROTATION` 未启用**，所以运行时
`echo 1 > /sys/class/graphics/fbcon/rotate` 无效（已实测）。
下次编译内核时把它打开即可，属于一行改动。

## C. 当前最终状态

| 项目 | 状态 |
|---|---|
| 显示（原生 DSI 1200x1920 + DSC + 背光） | ✅ **验证通过** |
| 内核 / 用户态 / UFS / SD 卡 | ✅ |
| USB 串口终端（COM3） | ✅ |
| 免刷机脚本通道 | ✅ |
| 触控 | ❌ 芯片 SPI 读回 0xFF |
| GPU（GLES） | ❌ 缺 a630_sqe.fw / a610_zap |
| DPU 核心时钟 OPP | ⚠️ clk_set_rate 返回 -22 |

## D. 下一次开工的建议顺序

1. **触控**：面板已完全初始化仍不应答，重点排查方向：
   - TB331FC 的触控 SPI 引脚是否与 TB128FU 不同（对比厂商 overlay 的 pinctrl）
   - 是否需要 `Himax_firmware.bin`（从原厂 vendor 固件提取）
   - 用 `devmem` 直接读 SPI 控制器寄存器，确认 MISO 是否有数据翻转
2. **GPU 固件**：从 `NON-HLOS.bin` / vendor 分区提取 `a630_sqe.fw`、`a610_zap.*`，
   放进 initramfs 的 `/lib/firmware/qcom/`
3. **内核重编**（顺手）：打开 `CONFIG_FRAMEBUFFER_CONSOLE_ROTATION`，
   加 cmdline `fbcon=rotate:1`
4. 触控 + GPU 就绪后 → Alpine/pmOS + Niri

---

# 附录：第十一轮 —— 触控真相（Novatek，不是 Himax）

## A. 根本性发现：触控芯片认错了

从运行中的 Android（A 槽）查到的权威信息：

```
/proc/bus/input/devices:
  N: Name="NVTCapacitiveTouchScreen"    ← 触控是 Novatek
  N: Name="himax-stylus"                ← Himax 只负责手写笔

dmesg:
  [NVT-ts] it is inx panel, firmware path: novatek_ts_fw.bin
  [NVT-ts] SPI driver NVT-ts has no spi_device_id for novatek,NVT-ts-spi
  [NVT-ts] nvt_ts_probe: mode=0, max_speed_hz=10000000
  [NVT-ts] novatek,irq-gpio=478, novatek,pen-support=1
  [NVT-ts] not support novatek,spi-rd-fast-addr
```

**结论：真正的触控是 Novatek NT36523，挂在 SPI CS1（spi0.1），mode 0，10 MHz。**
`spi0.0` 上的 Himax 是手写笔控制器。

之前所有触控失败（`himax_hx83102 sense_off data[0]=FF`）都是因为**驱动在跟一颗
Novatek 芯片用 Himax 的协议通信**，永远读不到应答。

## B. 修复路径（三处改动）

1. **内核配置**：`CONFIG_TOUCHSCREEN_NT36523_SPI=y`
   （原本是 `=m`，模块没编进 initramfs）
2. **DTB**：启用已存在的 `touchscreen@1`（`compatible = "novatek,nt36523-spi"`），
   禁用 `touchscreen@0`（Himax）
3. **固件**：`novatek_ts_fw.bin` 放进 initramfs 的 `/lib/firmware/`，
   DT 的 `firmware-name` 指向它

工具：`tools/enable_novatek.py`

## C. 当前结果：驱动已绑定，芯片已识别，但固件下载失败

```
spi0.1                                    ← 设备存在
[NVT-ts-spi] nvt_read_pid: PID=84D3       ← 芯片有应答！
[NVT-ts-spi] abs_x_max=1200, abs_y_max=2000
N: Name="NVTCapacitiveTouchScreen"        ← 输入设备已注册
N: Name="NVTCapacitivePen"
```

但：

```
nvt_read_bld_hw_crc: ilm: bin crc = 0xF4FD5D35, result = 0xF4FD5D35   ✓
nvt_read_bld_hw_crc: dlm: bin crc = 0x49618174, result = 0x2AD78BD2   ✗
nvt_update_firmware: Download Firmware failed. (-1)
中断 115 (NVT-ts-spi): 0 次                       ← 芯片不报点
```

**ILM（代码段）写入正确，DLM（数据段）写入后 CRC 不一致，且每次结果不同**
（`0x2AD78BD2` / `0xE2E96CC4` / `0x932BC7BD`）→ 大块写入不稳定。

## D. 已排除的猜测

| 尝试 | 结果 |
|---|---|
| 恢复 SPI `dmas`（担心无 DMA 影响大块传输） | DLM 仍失败，结果依旧随机 |
| 删除 `novatek,spi-rd-fast-addr`（厂商日志明确不支持） | DLM 仍失败 |
| 触控 SPI 降到 5 MHz | **更糟**：`PID=0000`，中断风暴 478 次 → 9.6~10 MHz 才对 |

## E. 下一步方向（触控）

1. **换固件文件**：原厂还有 `novatek_ts_mp.bin`、`novatek_ts_fw_csot.bin`、
   `novatek_ts_mp_csot.bin`（都在 `D:\TB331FCLinux\firmware\vendor-firmware\`）
2. **比对 DLM 地址**：`drivers/input/touchscreen/nt36523_mem_map.h` 里该 IC 的
   DLM 写入地址是否与 PID 84D3 匹配
3. **对比 Android 驱动流程**：厂商驱动先 `bootloader_reset` 再按两套 chip map
   尝试（`chip_ver_trim_addr=0x1fb104` 与 `0x03f004`），主线只用了后者
4. 复位时序：`reset-gpio` 的拉低/释放延时可能与厂商不同

## F. 当前最佳状态（已固化）

| 分区 | 文件 |
|---|---|
| `boot_b` | `build\WORKING_boot_b.img`（= boot_nvt.img） |
| `vendor_boot_b` | `build\WORKING_vendor_boot_b.img`（= vb_nvt4.img） |

- 显示：**原生 DSI 1200x1920 + DSC + 背光** ✅
- USB 串口控制台（COM3）✅
- 触控驱动已绑定、芯片已识别，固件下载待解决
- 固件素材：`D:\TB331FCLinux\firmware\vendor-firmware\`（25 MB，57 个文件，
  Himax_firmware.bin / a630_sqe.fw / a610_zap.* / novatek_ts_* 等）

---

# 附录：第十二轮 —— GPU 固件与现状

## A. 已解决：GPU 固件加载

从 Android 的 `/vendor/firmware/` 提取并放到位（`tools/mk_gpu_initramfs.sh`）：

```
lib/firmware/qcom/a630_sqe.fw                              32,504
lib/firmware/qcom/sm6225/LENOVO/TB128FU/a610_zap.mdt        6,860
                                          a610_zap.b00/.b01/.b02
lib/firmware/novatek_ts_fw.bin                            196,608
lib/firmware/Himax_firmware.bin                           261,120
```

结果（之前是 `failed with error -2`）：

```
[drm:adreno_request_fw] loaded qcom/a630_sqe.fw from new location
msm_dpu 5e01000.display-controller: bound 5900000.gpu (ops a3xx_ops)
/dev/dri/card1, /dev/dri/renderD128
/sys/class/devfreq/5900000.gpu
```

## B. GPU 硬件初始化尚未发生

`dmesg` 里没有任何 `a6xx` / GPU 型号输出。原因分析：

- 主线 6.14 **不需要** `CONFIG_QCOM_ZAP_SHADER`（该配置项在这个树里不存在，
  ZAP 由 `adreno_gpu.c: zap_shader_load_mdt()` 直接处理）
- `zap-shader` 节点在 DTB 里存在且属性齐全
  （`memory-region = <&zap_shader_region>`、`firmware-name = ".../a610_zap.mdt"`）
- `adreno_load_gpu()` 由 `msm_gpu_init()` 触发，而 `msm_gpu_init()` 需要
  **真正的 DRM 客户端**（打开 card 节点并执行 ioctl），我们只有 busybox，
  手动 `exec 3<>/dev/dri/card1` 不足以触发

**结论：GPU 初始化要等有真正的 userspace 图形栈（Mesa/freedreno）时才会发生。**
这跟"下一个大目标：装发行版"天然合在一起 —— 装好 Alpine + Mesa 后打开任意
DRM 程序，GPU 就会初始化，届时再看 `dmesg` 的 a6xx 输出。

## C. 关于 Adreno 610 的支持度（回答"骁龙有开源驱动"）

判断正确，支撑是成熟的：

| 层 | 组件 | 状态 |
|---|---|---|
| 内核 | `msm` + `adreno`（A610 属于 a6xx，freedreno 覆盖） | ✅ 已内置并绑定 |
| 固件 | `a630_sqe.fw`（a6xx 共用）+ `a610_zap.*` | ✅ 已就位 |
| 用户态 | Mesa `freedreno`（`msm_dri.so`） | ⬜ 随发行版安装 |

所以 GPU 不需要我们写驱动，只需要发行版里的 Mesa。

## D. 触控（遗留）

固件下载仍是卡点：

```
ilm: bin crc = 0xF4FD5D35, result = 0xF4FD5D35   ✓
dlm: bin crc = 0x49618174, result = 每次不同      ✗
```

下一次建议：
1. 换 `novatek_ts_mp.bin` / `novatek_ts_mp_csot.bin` / `novatek_ts_fw_csot.bin`
2. 核对 `nt36523_mem_map.h` 里 PID 84D3 的 DLM 写入地址
3. 对照厂商驱动：它先 `bootloader_reset`，再按两套 chip map 尝试
   （`chip_ver_trim_addr=0x1fb104` 与 `0x03f004`），主线只用后者

## E. 当前最佳状态

| 分区 | 文件 |
|---|---|
| `boot_b` | `build\boot_nvt.img`（Novatek 触控驱动内置） |
| `vendor_boot_b` | `build\vb_gpu.img`（DTB + 触控/GPU 固件） |

**可用能力**：原生 DSI 1200x1920 + DSC + 背光、USB 串口控制台、UFS、SD 卡、
自编译内核、免刷机脚本通道。

**下一步主攻**：发行版（Alpine/pmOS）+ Mesa → 然后 Niri。

---

# 附录：第十三轮 —— 发行版（Alpine）开工记录

## A. 已完成

| 项 | 结果 |
|---|---|
| Alpine aarch64 minirootfs 3.24.3 | 已下载（`rootfs/alpine/alpine-minirootfs-3.24.3-aarch64.tar.gz`，4 MB） |
| `apk.static` 3.0.8（x86_64） | 已下载并解出（`rootfs/alpine/apk.static`）—— **可交叉安装 aarch64 包，不需要 qemu/chroot** |
| minirootfs 解压 | `rootfs/alpine/stage`（83 个文件，8.4 MB） |
| niri 可用性确认 | **有**：Alpine v3.24 **community** 仓库提供 `niri-26.04-r0` |

## B. 下次继续的第一步

`apk.static` 在非 root 下必须加 **`--usermode`**（否则报
"Use --usermode to allow creating database as non-root"）。命令模板：

```bash
cd /mnt/d/TB331FCLinux/rootfs/alpine
./apk.static --root stage --arch aarch64 --usermode --no-progress \
  --keys-dir stage/etc/apk/keys \
  --repository <MIRROR>/v3.24/main \
  --repository <MIRROR>/v3.24/community \
  --allow-untrusted \
  add alpine-base mesa mesa-dri-gallium mesa-egl mesa-gbm libdrm eudev niri
```

**国内镜像（优先用这些，海外源太慢）：**

| 镜像 | Alpine 地址 |
|---|---|
| 清华 TUNA | `https://mirrors.tuna.tsinghua.edu.cn/alpine` |
| 中科大 USTC | `https://mirrors.ustc.edu.cn/alpine` |
| 阿里云 | `https://mirrors.aliyun.com/alpine` |
| 南京大学 | `https://mirror.nju.edu.cn/alpine` |

## C. 根文件系统方案（已定，无需格式化 SD 卡）

SD 卡是 FAT32（Windows 可写），Linux rootfs 需要 ext4。方案：

1. 在 WSL 里用 `mke2fs -t ext4 -d <dir> rootfs.img <size>` **非 root 直接生成已填充的
   ext4 镜像**（e2fsprogs ≥1.47 支持 `-d`）
2. 把 `rootfs.img` 作为**普通文件**拷到 SD 卡根目录（Windows 直接拖）
3. 改 init：挂载 vfat → 找到 `/mnt/rootfs.img` → `losetup` → 挂 ext4 → `switch_root`

这样卡不用重分区、不用格式化，随时可以换镜像。

**注意**：早期 `mount -t vfat` 曾返回 EFAULT，但当时内核里 VFAT 还是模块；
现在 `VFAT_FS`/`MSDOS_FS`/`EXFAT_FS` 都已内置（`=y`），需重新验证一次挂载。

## D. 今日最终状态

| 项目 | 状态 |
|---|---|
| 显示（原生 DSI 1200x1920 + DSC + 背光） | ✅ |
| 内核 / 用户态 / UFS / SD 卡 | ✅ |
| USB 串口控制台（COM3，`tools/tty.ps1`） | ✅ |
| 免刷机脚本通道（SD 卡 `run.sh`） | ✅ |
| 自编译内核（SPI/触控/PWM/vfat 内置） | ✅ |
| GPU 固件（a630_sqe.fw + a610_zap） | ✅ 已加载 |
| 触控 | 🟡 驱动绑定+芯片识别（Novatek PID 84D3），固件 DLM 下载待解决 |
| GPU 硬件初始化 | ⬜ 待 Mesa（需发行版） |
| 发行版 | 🟡 Alpine 已下载并解压，包安装待完成 |

**镜像固化**：`build\WORKING_boot_b.img` + `build\WORKING_vendor_boot_b.img`

**固件素材**：`D:\TB331FCLinux\firmware\vendor-firmware\`（25 MB / 57 个文件）

---

# 附录：第十四轮 —— Alpine Linux 起来了（重大里程碑）

## A. 成果：平板跑起完整 Alpine Linux

```
Welcome to Alpine Linux 3.24
Kernel 6.14.0-rc5-next-20250306 on aarch64 (/dev/ttyGS0)

tb331fc login: root （空密码）
tb331fc:~#
```

系统信息：
```
Linux tb331fc 6.14.0-rc5-next-20250306 aarch64
Mem: 5589 MB 总 / 5469 MB 可用
Disk: /dev/loop0 1.9G，已用 522M
/dev/dri: card1, renderD128
niri: /usr/bin/niri (25.11)  ← 已安装
```

**从电脑通过 USB 串口直接 root 登录，像操作一台服务器一样操作这台平板。**

## B. 启动架构（最终形态）

```
ABL → boot_b(自编译内核) → vendor_boot_b(initramfs_v18)
  → init: 挂 proc/sys/dev/tmp → 备好 busybox → 早期建立 USB gadget
  → 挂 FAT32 SD 分区(/dev/mmcblk0p1) → 找到 /mnt/alpine-rootfs.img
  → losetup /dev/loop0 → mount ext4 → 迁移 /proc /sys /dev + configfs
  → busybox switch_root /newroot /sbin/init
  → Alpine OpenRC 启动 → getty on ttyGS0
```

**关键设计：根文件系统是 FAT32 卡上的一个 ext4 镜像文件** —— 不用重分区、
Windows 直接拖文件替换，随时可以换镜像。

## C. 踩过的坑（都已解决）

| 问题 | 根因 | 修法 |
|---|---|---|
| `switch_root: not found` → kernel panic | initramfs 里只有 `/bin/busybox`，没有 applet 符号链接 | 显式写 `/bin/busybox switch_root` |
| switchroot 后 `/dev/ttyGS0` 消失 | `switch_root` 只移动 `/sys`，**configfs 子挂载被孤立** → gadget 被拆 | ① gadget 提前到 switchroot 之前建立<br>② switchroot 时把 `/sys/kernel/config` 一起迁移 |
| Alpine `usbgadget` 服务失败 | UDC 被孤立实例占用 | 由 initramfs 负责建 gadget，Alpine 侧不再重复 |
| init 里 `mount(2)` 返回 EFAULT | 内核行为怪异 | 改为 fork+exec `busybox mount` |
| `inittab` 里 getty 打不开 ttyGS0 | gadget 不存在 | 同上 |
| niri 报 `NoWaylandLib` | 缺 `wayland-libs-server` | 待装（见 D） |

## D. 断点：待完成（下次从这里继续）

### 1. 装 niri 缺失的依赖（不用刷机、不用重拷镜像）

包已下载在 `D:\TB331FCLinux\rootfs\alpine\apks\`（6 个，224 KB）：
```
wayland-libs-server-1.25.0-r0.apk   32K   ← niri 必需
libseat-0.9.3-r0.apk                16K
seatd-0.9.3-r0.apk                  19K
seatd-openrc-0.9.3-r0.apk          2.1K
mesa-utils-9.0.0-r6.apk            135K   ← 测试 GL 用
evtest-1.36-r0.apk                  14K   ← 调试触控用
```

**两种安装方式（二选一）：**

**(a) 串口传输**（`tools/transfer_apks2.ps1`，用 heredoc 流式写入）
> 之前失败原因：v1 每 400 字节等一次 shell 回显，开销压倒传输。
> v2 改成单个 heredoc 一次灌入，理论 10~20 秒。**还没跑成功过，下次验证。**

**(b) 最可靠：把 SD 卡插电脑，把 `apks\*.apk` 拷到卡上 `apks\` 目录**
```sh
mkdir -p /mnt && mount -t vfat /dev/mmcblk0p1 /mnt
cp /mnt/apks/*.apk /tmp/apks/
apk add --allow-untrusted --no-network /tmp/apks/*.apk
```

### 2. 之后的目标

```sh
# 装完依赖后测 niri
rc-service seatd start
niri                  # 看能否出画面（GPU 初始化会在此触发）
dmesg | grep a6xx     # 确认 Adreno 610 初始化
```

3. **触控**仍是固件 DLM 写入 CRC 不一致（芯片 Novatek NT36523 PID 84D3/8793）
4. **GPU**：固件已就位，等 niri/mesa 触发初始化
5. USB 网络（RNDIS）：已写进 `initramfs/gadget.sh`，但还没刷入生效
   （`build\vb_alpine7.img` 已生成，等下次刷）

## E. 工具速查

| 工具 | 用途 |
|---|---|
| `tools\alpine.ps1` | 在 Alpine 里执行命令（自动登录）：`$env:ALPINE_CMD='...'` 然后调用 |
| `tools\transfer_apks2.ps1` | 串口传输 apk |
| `tools\fetch_apks.sh` | 在 PC 上下载 aarch64 apk（用清华镜像） |
| `tools\mk_initramfs_v16.sh` | 打包 initramfs（当前用 init_v18） |
| `tools\mkv4.py` | 生成 boot/vendor_boot 镜像 |

## F. 当前镜像状态

| 分区 | 文件 | 说明 |
|---|---|---|
| `boot_b` | `build\boot_nvt.img` | 自编译内核（Novatek 触控 + 面板 + loop/ext4/vfat 全内置） |
| `vendor_boot_b` | `build\vb_alpine6.img` | **当前已刷**（早期 gadget + configfs 迁移，串口稳定） |
| 待刷 | `build\vb_alpine7.img` | 额外加了 RNDIS USB 网络 |
| SD 卡 | `alpine-rootfs.img` (2.0 GB) | Alpine 3.24 + niri + mesa + 全部固件 |

---

# 附录：第十五轮 —— GPU + Niri 成功运行（目标达成）

## A. GPU：freedreno FD610 工作正常

装好 Mesa 后，只要**有程序真正打开 DRM 设备**，Adreno 就会初始化：

```sh
eglinfo -B
```
```
EGL API version: 1.5
OpenGL core profile vendor:   freedreno
OpenGL core profile renderer: FD610                    ← Adreno 610
OpenGL core profile version:  4.6 (Core Profile) Mesa 26.1.6
OpenGL ES profile version:    OpenGL ES 3.2 Mesa 26.1.6
```

**之前 `dmesg` 里一直没有 `a6xx` 初始化日志，不是驱动或固件的问题 —— 只是没人打开 GPU。**
`CONFIG_QCOM_ZAP_SHADER` 这个配置项在 6.14 里根本不存在（ZAP 由
`adreno_gpu.c: zap_shader_load_mdt()` 内联处理），不要再去找它。

## B. Niri 25.11 在平板上运行成功

```sh
mkdir -p /run/user/0 && chmod 700 /run/user/0
export XDG_RUNTIME_DIR=/run/user/0
rc-service seatd start
niri
```

```
niri: starting version 25.11
niri::backend::tty: using as the render node: "/dev/dri/renderD128"
niri::backend::tty: adding device: "/dev/dri/card1"
niri::backend::tty: this is the primary node
niri::backend::tty: initializing the primary renderer
niri::backend::tty: new connector: DSI-1
niri::backend::tty: picking mode: Mode { name: "1200x1920", clock: 186473,
    size: (1200, 1920), hsync: (1296, 1300, 1396), vsync: (1976, 1978, 2226),
    vrefresh: 60, ... PREFERRED|DRIVER }
niri: listening on Wayland socket: wayland-1
niri: IPC listening on: /run/user/0/niri.wayland-1.5258.sock
```

**Niri 直接接管 DSI 面板，用我们驱动的模式 1200x1920@60Hz。**

无害 warning（可忽略/后续再补）：
- `EGL_WL_bind_wayland_display` 不支持 —— 正常，不影响
- `error initializing DRM leasing` —— 不影响
- `error getting EDID info for DSI-1` —— **DSI 面板没有 EDID 是正常的**
- 缺 HDR/GAMMA 属性 —— 面板驱动未提供，不影响
- `xwayland-satellite` 缺失 —— 只影响跑 X11 程序
- dbus/login1/locale1 未运行 —— 缺 elogind/dbus，影响会话管理
- `x cursor default@48` 无图标、`waybar` 未安装 —— 纯外观

## C. 关键教训（GPU 部分）

**不要一开始就怀疑固件/驱动。** 先后花了很久排查：
- `CONFIG_QCOM_ZAP_SHADER` —— 6.14 无此配置
- `a630_sqe.fw` 加载 —— 确实需要（已放好）
- 手动 `exec 3<>/dev/dri/renderD128` —— 不足以触发
- 真正原因：**需要有实际使用 GPU 的用户态程序（Mesa/eglinfo/niri）**

固件路径（必须放对，否则 `-2`）：
```
/lib/firmware/qcom/a630_sqe.fw
/lib/firmware/qcom/sm6225/LENOVO/TB128FU/a610_zap.{mdt,b00,b01,b02}
```
（路径来自 DTB 的 `zap-shader { firmware-name = ... }`）

## D. 离线装包方法（无网络时）

SD 卡在 Alpine 里挂载：
```sh
mkdir -p /mnt && mount -t vfat /dev/mmcblk0p1 /mnt
cp /mnt/apks/*.apk /tmp/apks/
apk add --allow-untrusted --no-network /tmp/apks/*.apk
```

PC 侧下载 aarch64 包（用清华镜像，`tools/fetch_apks.sh`）：
```bash
./apk.static --root stage --arch aarch64 --usermode \
  --repository https://mirrors.tuna.tsinghua.edu.cn/alpine/v3.24/main \
  --repository https://mirrors.tuna.tsinghua.edu.cn/alpine/v3.24/community \
  --allow-untrusted add <packages>
# apk 3.x 不保留缓存，改用 apk fetch 或从 installed db 解析版本号 + curl
```

**注意**：apk 3.x 的 `fetch` 子命令不支持 `--usermode`；
`--root` 与 `--usermode` 不能同时用于 fetch。

## E. 当前待办（按优先级）

1. **触控**（最关键，没有它无法真正使用桌面）
   - Novatek NT36523，`spi0.1`，PID 84D3/8793
   - 卡点：固件 DLM 段写入后 CRC 不一致（ILM 正常）
   - 已排除：SPI 频率（5MHz 更差）、`spi-rd-fast-addr`、DMA
   - 下一步：换 `novatek_ts_mp.bin` 等其它固件 / 核对 mem_map 地址

2. **Niri 开机自启**（现在要手动从串口敲命令）
   - 需要：dbus + elogind（或 seatd + 直接 root 会话）
   - 写一个 openrc 服务在 tty1 上启动 niri

3. **USB 网络**：`usb0` 已在设备侧就绪（RNDIS），但 **Windows 11 已移除内置
   RNDIS 驱动**，主机侧不识别 → 改用 **NCM** 或 USB 网卡，或继续用 SD 卡离线装包

4. 音频、WiFi、GPU 性能调优（DPU 核心时钟 -22）

## F. 里程碑总结

| 能力 | 状态 |
|---|---|
| 主线内核 + ABL 放行 | ✅ |
| 原生 DSI 显示 1200x1920@60 + DSC + 背光 | ✅ |
| UFS / SD 卡 | ✅ |
| USB 串口 root 登录 | ✅ |
| **Alpine Linux 3.24 根文件系统** | ✅ |
| **GPU：freedreno FD610，OpenGL 4.6 / GLES 3.2** | ✅ |
| **Niri 25.11 Wayland 合成器** | ✅ |
| 触控 | 🟡 芯片/驱动就绪，固件 DLM 待解决 |
| USB 网络 | 🟡 设备侧就绪，Windows 侧驱动缺失 |

---

# 附录：第十六轮 —— Niri 正常显示（DPU 核心时钟是元凶）

## A. 症状与破案过程

niri 启动后画面是**满屏蓝绿竖条网格**（周期 8x16 像素 = 控制台字符格）。
关键线索来自用户观察：

> "第一次启动 niri 时快捷键显示正常，后来不知怎么就花了"

顺着这条线查到时钟：

```
刚开机:  disp_cc_mdss_mdp_clk = 383 MHz   ← dpu_kms_init 取最高 OPP，画面正常
niri 跑起来后: disp_cc_mdss_mdp_clk = 19.2 MHz ← 画面花掉
```

## B. 根因

1. DT 里 `display-controller@5e01000` 的 OPP 表（phandle 0x72）写的是
   **200 / 300 / 383 / 470 / 560 MHz**
2. dispcc 的 `ftbl_disp_cc_mdss_mdp_clk_src` 实际只支持
   **19.2 / 192 / 256 / 307.2 / 384 MHz**
3. `dpu_core_perf_crtc_update()` 算出需要的带宽后调用 `dev_pm_opp_set_rate()`
   → 频率不在表里 → `clk_set_rate` 返回 **-EINVAL(-22)**
   → 时钟落到最低档 **19.2 MHz**
4. 19.2 MHz 无法支撑 1200x1920@60 的全屏逐帧刷新
   → 欠载 → 输出错乱成网格

**为什么控制台一直看着正常**：fbcon 只在有文字变化时做小范围刷新，19.2 MHz 勉强够；
合成器每帧全屏重绘就崩了。

## C. 修法：把 OPP 表钉死到 384 MHz

`tools/fix_dpu_opp.py` + `tools/pin_dpu_clk.py`，最终 DT 里只剩一档：

```dts
opp-table {
    compatible = "operating-points-v2";
    phandle = <0x72>;
    opp-384000000 {
        opp-hz = <0x00 0x16e36000>;   /* 384000000 */
        required-opps = <0x1a>;
    };
};
```

这样 `dev_pm_opp_find_freq_ceil/floor()` 只能返回 384 MHz，
`dev_pm_opp_set_rate()` 永远成功，频率不再被降下来。

**注意**：写十六进制时要精确 —— `192000000 = 0xB71B000`（不是 0xB700000），
`307200000 = 0x124F8000`（不是 0x12500000）。写错会导致精确匹配查表失败。

## D. 结果

```sh
grep disp_cc_mdss_mdp_clk /sys/kernel/debug/clk/clk_summary
#   disp_cc_mdss_mdp_clk   2  2  0  382999951  ...
```

niri 启动、显示快捷键提示、**画面稳定正常**。

## E. 顺带解决的问题：UBWC

niri 最初用 `DRM_FORMAT_MOD_QCOM_COMPRESSED`（UBWC）分配 framebuffer，
而 sm6225 从 sm6115 继承的 UBWC 参数（enc 1.0 / dec 2.0 / swizzle 7）并不正确。
`tools/disable_sm6225_ubwc.py` 给 sm6225 单独一份 mdss data（不宣告 UBWC），
让所有合成器退回线性缓冲。这不是本次花屏的最终原因，但是必要的一步：

```
niri 的 framebuffer: modifier=0x0   （原来是 0x500000000000001）
```

## F. 当前可用的完整栈

| 层 | 状态 |
|---|---|
| Bootloader（ABL + stub `__symbols__`） | ✅ |
| 内核 6.14-rc5（自编译，全内置） | ✅ |
| 原生 DSI 面板 1200x1920@60 + DSC + 背光 | ✅ |
| 存储（UFS + SD 上 loop 挂 ext4） | ✅ |
| USB 串口控制台（ttyGS0，COM3） | ✅ |
| Alpine 3.24 rootfs | ✅ |
| GPU（freedreno FD610，GL 4.6 / GLES 3.2） | ✅ |
| **Niri 25.11 合成器，画面正常** | ✅ |
| DPU 核心时钟 384 MHz 稳定 | ✅ |

## G. 待办

1. **切 90Hz**（面板原生支持，厂商用 90Hz：clock 279675 kHz）
2. **触控**（Novatek NT36523，固件 DLM 写入 CRC 不一致）
3. 装终端（foot）等应用，做成可日常使用的桌面
4. GPU 性能调优（现在 DPU 钉在最高频，耗电会高一些）

---

# 附录：第十七轮 —— 触控攻坚（厂商源码线索 + 未解决）

## A. 触控当前状态

```
spi0.1 绑定 NVT-ts-spi     ✅
PID=每次不同（84D3/A493/10D3/8793/9693/9413）  ❌ 应为固定值
ilm crc: bin == golden == result                ✅ 写入+回读正确
dlm crc: bin == golden，result 每次不同          ❌
中断 115 (NVT-ts-spi): 0 次                     ❌ 芯片不报点
```

**PID 每次都不一样是最关键的异常** —— 真实芯片的 PID 是固定的，
说明 SPI 通信返回的数据不可靠，或芯片处于不断重启/异常状态。

## B. 已排除的假设

| 假设 | 实验 | 结果 |
|---|---|---|
| 驱动认错芯片（Himax vs Novatek） | 换 Novatek 驱动 | ✅ 修好了识别，但不报点 |
| UBWC / 缓冲格式 | 关闭 UBWC | 与触控无关（显示问题） |
| 大块传输失败（63KB） | 改 4KB | DLM 仍失败 |
| SPI 无 DMA | 恢复 `dmas` | DLM 仍失败 |
| `spi-rd-fast-addr` 不支持 | 删除该属性 | DLM 仍失败 |
| SPI 频率 | 5 MHz | **更糟**（PID=0000）→ 9.6~10 MHz 才对 |
| 芯片卡在 CRC 失败重启循环 | 移植 `nvt_stop_crc_reboot()` | 检测结果显示"不在循环中"（读地址可能不对） |

## C. 厂商源码线索（重要，下次从这里接）

**找到的开源仓库：**

| 仓库 | 内容 | 适用性 |
|---|---|---|
| [Roynas-Android-Playground/kernel_lenovo_tb128fu](https://github.com/Roynas-Android-Playground/kernel_lenovo_tb128fu) | TB128FU 厂商内核，含 `nova_36525_mmi/nt36xxx*.c` | ⚠️ **I2C 版**（`CTP_I2C_WRITE`），我们是 SPI 版，只能参考协议 |
| [yxyyds666/TB331FC-Kernel](https://github.com/yxyyds666/TB331FC-Kernel) | TB331FC 定制内核（GKI 5.15 + KernelSU） | 只有 CI 脚本，无驱动源码 |
| TB331FC 原厂 | Lenovo 开源代码站（按机型找） | **未确认**，值得去找 |

**从厂商 nt36xxx.c 学到的**（已参考实现）：
```c
void nvt_stop_crc_reboot(void)
{
    // 读 4 字节；若 buf[1..3] 全为 0xFC 或 0xFF → IC 在 CRC 失败重启循环
    // 处理：写 0xA5 到 HW 地址两次 → 清 CRC_ERR_FLAG(=0x03F135) ← 0xA5
}
```

**本机的关键地址（来自 Android 厂商日志）：**
```
chip_ver_trim  = 0x03F004
swrst_sif      = 0x03F0FE
crc_err_flag   = 0x03F135
```

## D. 下一步建议（触控）

1. **用逻辑分析仪或示波器**看 SPI 实际波形（MISO 上是否有数据翻转、CS 时序），
   这是判断"读不可靠"最快的办法
2. **找 Lenovo 官方开源代码包**（按 TB331FC 型号），里面应有 SPI 版 nt36523 驱动
3. 对比 Novatek 官方 SPI 参考驱动与主线 `nt36523_ts.c` 的
   `spi_read_write()`（dummy bytes、bits_per_word、CS 控制）
4. 在 Android 侧用 `devmem`/netlink 抓触摸正常时的 SPI 事务，与 Linux 对比
5. 确认是否需要 `novatek,spi-rd-fast-addr`（本机厂商日志说"不支持"）

## E. 当前系统状态（好状态，可日用）

| 项目 | 状态 |
|---|---|
| 显示（1200x1920@60 + DSC + 背光） | ✅ |
| DPU 核心时钟 384 MHz（钉死） | ✅ |
| GPU（freedreno FD610, GL 4.6） | ✅ |
| **Niri 合成器**（tty1 自启 + seatd） | ✅ |
| USB 串口 root 登录 | ✅ |
| 触控 | ❌ 未解决（SPI 读不可靠 / 固件写入失败） |
| 90Hz | ⬜ 未切换（面板支持，现在跑 60Hz） |

**当前镜像：**
- `boot_b` = `build\boot_crcfix2.img`（含 CRC 检测，无害）
- `vendor_boot_b` = `build\vb_pinned.img`（DPU 时钟钉 384MHz）
- 稳定回退版：`WORKING_boot_b.img` + `WORKING_vendor_boot_b.img`

## F. 桌面环境决策（已定）

**最终目标：Debian + HyperOS 双系统，桌面用 Hyprland。**

- Hyprland 在 Debian 官方仓库有 arm64 包（`trixie-backports` / `forky` / `sid`），
  直接 `apt install` 即可
- niri **没有** Debian 官方包（需源码编译）
- Denial 无 ARM64 官方包（需自建 Flutter 引擎，不现实）
- 触屏体验最好的是 GNOME，但 Hyprland 有触摸屏 swipe 支持且可关效果，选了它

---

# 附录：第十八轮 —— SPI 自检排除通信问题（关键）

## A. 自检结果：SPI 传输完全可靠

在驱动里加了 `nvt_spi_selftest()`（连续读同一个寄存器 20 次并打印）：

```
[NVT-ts-spi] nvt_spi_selftest: selftest: 20 reads, 1 distinct values
[NVT-ts-spi] selftest[00..09]: 84D3 84D3 84D3 84D3 84D3 84D3 84D3 84D3 84D3 84D3
[NVT-ts-spi] selftest[10..19]: 84D3 84D3 84D3 84D3 84D3 84D3 84D3 84D3 84D3 84D3
[NVT-ts-spi] nvt_read_pid: PID=84D3
```

**结论：SPI 通信没有问题，芯片 PID 稳定为 `0x84D3`。**

这一下排除了一整类假设（时钟/模式/CS/走线/哑字节）。
之前"PID 每次不同"是因为那些读取发生在**固件下载失败之后**的混乱状态。

## B. 排除清单更新

| 假设 | 状态 |
|---|---|
| SPI 传输不可靠（时序/模式/走线） | ❌ **已排除**（20 次读一致） |
| 芯片未应答 / 错误的驱动 | ❌ 已排除（PID 正常） |
| 大块传输 63KB 失败 | ❌ 已排除（4KB 仍失败） |
| 无 DMA | ❌ 已排除 |
| SPI 频率 | ❌ 已排除（9.6 MHz 正确） |
| 芯片卡在 CRC 失败重启循环 | 🟡 检测显示"不在循环"（读地址可能不对，无法确认） |
| **固件 DLM 段写入失败** | ⬜ **剩余的真问题** |

## C. 另一个发现：主线驱动的 ID 校验被砍掉了

```c
static int8_t nvt_ts_check_chip_ver_trim(uint32_t chip_ver_trim_addr)
{
	ts->mmap = &NT36523_memory_map;      /* 硬编码，不读 ID 不匹配 */
	ts->carrier_system = NT36523_hw_info.carrier_system;
	ts->hw_crc = NT36523_hw_info.hw_crc;
	return 0;
}
```

`nt36523_mem_map.h` 里的 `trim_id_table[]` 有 10+ 个芯片条目（NT36523/NT36675/NT36526/
NT36672A…），但**这个函数根本没用到**。所以映射表是按 NT36523 硬套的。

对我们的芯片大概率正确（Android 也是 NT36523），但**未经校验** ——
如果固件下载的 DLM 地址来自这张表而表实际不匹配，就会写错位置。

## D. 下一步（按性价比排序，都不需要逻辑分析仪）

1. **换固件文件试**（最便宜）：
   `D:\TB331FCLinux\firmware\vendor-firmware\` 里还有：
   ```
   novatek_ts_fw_csot.bin
   novatek_ts_mp.bin
   novatek_ts_mp_csot.bin
   ```
   逐个替换 `/lib/firmware/novatek_ts_fw.bin` 后重启，看 DLM CRC 是否通过。
   （约 192 KB，可通过串口 heredoc 传输，约 25 秒/个）

2. **让 trim ID 校验真正生效**：把 `trim_id_table[]` 的匹配逻辑加回
   `nvt_ts_check_chip_ver_trim()`，打印实际读到的 6 字节 ID，
   确认芯片是否真的匹配 NT36523 映射。

3. **GENI 寄存器对比**：Android 侧触摸正常时用 `devmem` 读 SPI 控制器寄存器，
   与 Linux 侧逐位对比（Android 是已知可用的基准）。

4. **补上驱动 remove 路径的 bug**：`unbind` 会内核 oops（导致没法热重载驱动测试，
   每次都要重启）。修好后测试效率会高很多。

5. 硬件（可选）：USB 逻辑分析仪 ~¥40-100，8 通道 24 MHz 够看 10 MHz SPI 时序误差。

## E. 当前镜像

- `boot_b` = `build\boot_selftest2.img`（含 SPI 自检，每启动打印 20 次读数）
- `vendor_boot_b` = `build\vb_pinned.img`
- 系统状态正常：显示 ✅ / GPU ✅ / Niri ✅ / 串口 ✅ / 触控 ❌

---

# 附录：第十九轮 —— 触控排查收敛 + 传输通道

## A. 本轮确证的事实（都是实测）

| 结论 | 证据 |
|---|---|
| **SPI 传输完全可靠** | 连续读同一寄存器 20 次，20 次全为 `84D3` |
| **芯片是 NT36523 家族** | trim ID = `17 20 00 23 65 03`，后三字节 `23 65 03` 命中 `trim_id_table[]` 的 NT36523 条目 |
| **内存映射正确** | 同上，映射表选对了 |
| **4 个原厂固件全试过** | INX 版（`b1855...`）、mp 版（`1e3a...`）都失败；另两个 `_csot` 版是给 CSOT 面板的，不适用 |
| **故障点固定在 DLM 段** | `ilm: bin == golden == result`；`dlm: bin == golden ≠ result` |

所以问题精确定位为：**NT36523「无 flash」驱动把固件写入 SRAM 后，DLM 段回读 CRC 不符**，
而 ILM 段完全正确。芯片因此从未进入正常固件状态（`nvt_check_fw_reset_state failed`），
中断永不触发。

## B. 本轮尝试过但无效的

| 尝试 | 结果 |
|---|---|
| 换固件文件（mp 版） | DLM 仍失败（`result=0x9505C6EB`） |
| 传输块 63KB → 4KB | DLM 仍失败 |
| 移植 `nvt_stop_crc_reboot()`（厂商 I2C 版的 CRC 重启恢复） | 检测结果为"不在重启循环"（SPI 下读地址不对，无法确认） |
| 驱动 ID 校验桩函数 | 已补上真实读取（成功拿到 trim ID） |

## C. 新发现的两个驱动 bug（已修一个）

1. **`nvt_ts_remove()` 不销毁 `ts->event_wq`** → unbind 时 use-after-free → 内核 oops。
   **已修**（`tools/fix_nvt_remove.py`），unbind/bind 单次可成功。
2. **remove→probe 连续循环仍会崩** 在 `nvt_ts_probe+0x664`（第二次 bind 时）。
   说明 probe/remove 的状态清理还不完整。**未修**。
   → 因此固件测试改为「改固件 + 重启」，不依赖热重载。

## D. USB U 盘功能：需要先修 initramfs

想做「USB 复合设备：串口 + U 盘」，但发现：

```
/sys/kernel/config/            ← 空的（新挂载的 configfs 实例）
/sys/class/udc/4e00000.usb/state = configured
function = tb331fc             ← 我们的 gadget 活着，但在孤立的 configfs 里
```

**原因**：initramfs 建立 gadget 后，`switch_root` 迁移了 configfs，
但 Alpine 启动时又挂了一个新的 configfs 盖在上面，导致原实例不可访问。
`umount` 也卸不掉（EINVAL）。

**修法（下次刷机时一起做）**：
- 方案 A：initramfs 只在**不切换到 Alpine** 时才建 gadget，让 Alpine 自己建
  （`/etc/init.d/usbgadget` 已有，需加上 mass_storage 功能）
- 方案 B：让 Alpine 不要重复挂 configfs

内核已具备 `CONFIG_USB_CONFIGFS_MASS_STORAGE=y`，不需要重编译。

## E. 文件传输通道现状

| 方式 | 状态 |
|---|---|
| **SD 卡插电脑拷文件** | ✅ 可用（最可靠，`/mnt/fwtest/` 目录） |
| `tools/push_file.ps1` 串口 base64 | ⚠️ 192KB 文件在 ~40KB 处会卡住（串口流控不稳），适合小文件 |
| USB U 盘 | ⬜ 需先修 initramfs（见 D） |
| USB 网络（RNDIS） | ⬜ Windows 11 已移除内置驱动 |

## F. 触控下一步（最有效的一条）

**拿到 Novatek nt36523 的 SPI 厂商驱动源码，与主线逐行对比下载流程。**

候选来源：
- `LineageOS/android_kernel_motorola_sm6225`（同为 SM6225 + Novatek）
- 其他 SM6225 设备的 Android 内核里找 `nt36523` / `nova_*` 的 **SPI** 版本
- Lenovo 官方开源代码站（按 TB331FC 型号）

重点对比：
1. `nvt_write_sram()` 的分块大小与 `nvt_set_page()` 的调用时机
2. DLM 写入前后是否有额外的命令（如 `nvt_boot_ready()` 的顺序、`DMA_CRC_EN` 处理）
3. `hw_crc` 模式下的 CRC 校验地址
4. 是否有"写 DLM 前必须先进某个模式"的步骤

## G. 系统当前状态（恢复为可用）

- 固件已恢复为原始 INX 版（md5 `b18554017ad2f30224d0b7a47aa82d4d`）
- `boot_b` = `boot_trimid.img`（含 trim ID 读取 + SPI 自检 + remove 修复）
- 显示 ✅ / GPU ✅ / Niri ✅ / 串口 ✅ / 触控 ❌

---

# 附录：第二十轮 —— WiFi / 蓝牙开工（固件全部搞定）

## A. 背光：已经是好的（不用修）

```
/sys/class/backlight/5e94000.dsi.0/
  max_brightness 3767 / brightness 3767
  写入 1000 → actual_brightness 1000  ✅
```

DCS 背光控制正常，无需任何工作。

## B. 固件来源全部破解（重要成果）

厂商固件不只在 `/vendor/firmware`，还藏在两个**FAT 镜像**里：

| 用途 | 来源文件 | 提取出的内容 |
|---|---|---|
| **WiFi** | `fw\NON-HLOS.bin`（40MB，FAT） | `wlanmdsp.mbn` (3.7MB) + 34 个 `bdwlan.*`（含 `bdwlan.bin`） |
| **蓝牙** | `fw\BTFM.bin`（1MB，**FAT16**） | `crbtfw21.tlv` (227KB) + `crnv21.bin` (4.8KB) |

提取方法（WSL 里 loop 挂载）：
```bash
sudo mount -o loop,ro NON-HLOS.bin /mnt/nh    # → /mnt/nh/image/*
sudo mount -o loop,ro BTFM.bin    /mnt/btfm   # → /mnt/btfm/image/*
```
提取脚本：`tools/extract_wifi_fw.sh`、`tools/extract_btfm.sh`

**蓝牙固件路径**（`btqca.c` 里写死的）：
```
/lib/firmware/qca/crbtfw21.tlv
/lib/firmware/qca/crnv21.bin
```

## C. 内核配置：蓝牙 built-in 成功，WiFi 只能模块

```sh
# 蓝牙（全部内置，不需要模块）
CONFIG_BT=y
CONFIG_BT_HCIUART=y
CONFIG_BT_HCIUART_QCA=y
CONFIG_BT_QCA=y

# WiFi
CONFIG_ATH10K=y
CONFIG_ATH10K_SNOC=m          # 无法设为 y，见下
CONFIG_QCOM_QMI_HELPERS=m
```

**为什么 `ATH10K_SNOC` 只能是模块**：它依赖
`QCOM_RPROC_COMMON || QCOM_RPROC_COMMON=n`，而 `QCOM_RPROC_COMMON` 是**隐藏符号**
（由 Q6V5 系列 select），那些驱动本身又是 `=m`，无法强制为 `y`。

**踩坑记录**：
- 内置 `BT_QCA=y` 后必须**禁用 `BT_HCIBTUSB` / `BT_HCIBTQCOMSMD` 等 USB 蓝牙传输**，
  否则 modpost 报 `btbcm_setup_apple undefined`。
- 改过配置后必须**先 `make Image` 再 `make modules`**，否则 Module.symvers 里没有
  内置符号，modpost 会报一堆 `pwrseq_*` undefined。

模块已编译并安装到设备：`/lib/modules/6.14.0-rc5-next-20250306/`（676 个 .ko），
`depmod -a` 通过，`modprobe ath10k_snoc` 返回 0。

## D. 当前进展与卡点

### WiFi
```
ath10k_snoc c800000.wifi: Adding to iommu group 7
ath10k_snoc c800000.wifi: supply vdd-3.3-ch1 not found, using dummy regulator
（之后没有更多日志，没有 wlan 接口）
```
DTB 已补 `vdd-3.3-ch1-supply`，但**尚未验证是否生效**（那次刷的 DTB 基线选错，
见 E 节）。仍需排查：固件路径（DT 的 `firmware-name = "lenovo-tb128fu"` 会变成
`ar->board_name`）、QMI 流程、以及 `qcom,msa-fixed-perm` 权限。

### 蓝牙
```
qcom_geni_serial 4a8c000.serial: Invalid line -19
```
源码位置 `drivers/tty/serial/qcom_geni_serial.c:1654`：
```c
line = of_alias_get_id(node, "serial");
if (line == -ENODEV)
    line = of_alias_get_id(node, "hsuart");
port = get_port_from_line(line, data->console);   // line=-19 → 报错
```
即 `of_alias_get_id()` 返回 -ENODEV（-19）。**已给 DT 加了 `serial1` 别名**
（DTB 里确认存在），但驱动仍报 -19 —— 说明 `of_alias_get_id` 没找到。
**下次要查**：别名路径是否与实际节点路径完全一致、`qcom,geni-uart` 是否匹配到了
正确的 `of_match` 分支（console/UART 两套 driver）、以及是否需要 `hsuart` 别名。

## E. 【重要教训】DTB 基线必须唯一

本轮踩了个大坑：修 WiFi/BT 时从 `ref_nvt3.dts` 派生新 DTS，**丢掉了之前锁定的
DPU OPP（384 MHz）** → 时钟掉回 19.2 MHz → 屏幕立刻变蓝绿网格花屏。

**已建立唯一权威基线**：
```
build\CANONICAL.dts      ← 目前 = ref_pinned_bt.dts
```
含：ABL stub `__symbols__`、面板 `lenovo,p255-inx`、触控 `novatek,nt36523-spi`、
**DPU OPP 只留 384 MHz**、蓝牙 `serial1` 别名、WiFi `vdd-3.3-ch1`。

**以后所有 DTB 改动都必须从这个文件出发**（`tools/*.py` 里的路径也应改成它）。

## F. 当前可用状态

| 项目 | 状态 |
|---|---|
| 显示 1200x1920 + DSC + 背光（含亮度调节） | ✅ |
| DPU 核心时钟 384 MHz 锁定 | ✅ |
| GPU（freedreno FD610） | ✅ |
| Niri 合成器 | ✅ |
| USB 串口 root 登录 | ✅ |
| 内核模块（676 个）已安装 | ✅ |
| WiFi 固件 + 蓝牙固件已就位 | ✅ |
| WiFi 联网 | 🟡 驱动加载但无接口 |
| 蓝牙 | 🟡 serdev 未绑定（`Invalid line -19`） |
| 触控 | ❌ DLM 段写入 CRC 不符（待对比厂商 SPI 驱动） |
| 90Hz | ⬜ 未切换 |

镜像：
- `boot_b` = `boot_wifi2.img`（WiFi/BT 内核）
- `vendor_boot_b` = `vb_pinned_bt.img`（OPP 锁定 + WiFi/BT DT）
- 备份：`WORKING_boot_b.img` / `WORKING_vendor_boot_b.img`

## G. 下次开工建议顺序

1. **修蓝牙的 `Invalid line -19`**（改动小、最接近成功）
2. **WiFi 固件路径**：按 ath10k 的实际请求路径（`dmesg` 里的
   `Direct firmware load for X failed`）摆放，DT 的 `firmware-name` 决定 board_name
3. 触控 DLM（需要厂商 SPI 驱动对照）
4. 90Hz（面板原生支持）

---

# 附录：第二十一轮 —— 蓝牙链路全通，芯片不应答

## A. 已解决的一连串问题（都是真实缺陷）

| 问题 | 根因 | 修法 |
|---|---|---|
| `qcom_geni_serial 4a8c000.serial: Invalid line -19` | DT aliases 路径写成 `/soc@0/...`，真实路径是 `/soc/...` → `of_alias_get_id()` 返回 -ENODEV | `tools/fix_aliases_path.py`：3 处别名改为 `/soc/` |
| 蓝牙 UART 无 pinctrl | `serial@4a8c000` 节点完全没有 `pinctrl-0` | 挂上 DTB 里已有的 `qup-spi3-default-state`(0x57) |
| 缺 2 路稳压器 | hci_qca 的 `qca_soc_data_wcn3990` 要 `vddio/vddxo/vddrf/vddch0` 四路，DT 只有两路 | `tools/fix_bt_supplies.py`：vddrf→`vdd-1.3-rfa`，vddch0→`vdd-3.3-ch0` |

**现在状态（全部验证通过）：**
```
4a8c000.serial: ttyHS1 at MMIO 0x4a8c000 (irq = 110) is a MSM   ← UART OK
/sys/bus/serial/devices/: serial0, serial0-0                     ← serdev 绑定 OK
/sys/class/bluetooth/: hci0                                      ← HCI 设备 OK
pin 8/9/10/11: 4a8c000.serial  function qup3                      ← 四线全 mux OK
serial0-0-vddio/vddxo/vddrf/vddch0 均已申请 (15/80/300/450mA)     ← 供电 OK
```

## B. 剩余问题：芯片不应答

```
Bluetooth: hci0: command 0xfc00 tx timeout
Bluetooth: hci0: Reading QCA version information failed (-110)
Retry BT power ON:0..3
```

即 `0xFC00`（QCA 版本查询）发出去了但收不到回应。已排除：
- UART 控制器 ✅、serdev ✅、引脚 mux（TX/RX/CTS/RTS）✅、四路稳压器请求 ✅

**下一步怀疑方向：**
1. **芯片没真正上电/使能**：`regulator_summary` 显示各路电压都是 `0mV`，
   可能是固定/dummy 稳压器（没有真正的 PMIC 驱动接管），或需要一个 BT enable GPIO
2. **UART 实例可能不对**：DT 里的 `serial@4a8c000` 来自 TB128FU 的 DTB，
   TB331FC 的蓝牙可能挂在别的 SE（如 4a88000/4a90000）
3. **需要核对 Android 侧**：A 槽 Android 里 `dmesg | grep -i qca` 能看到真实的
   UART/GPIO/regulator 配置，这是最权威的参照

## C. CANONICAL.dts 当前累计修复（唯一权威基线）

```
build\CANONICAL.dts
├── ABL stub __symbols__（120 个符号）
├── aliases 路径修正 /soc@0/ → /soc/
├── 面板 compatible = lenovo,p255-inx
├── 触控 touchscreen@1 = novatek,nt36523-spi（touchscreen@0 禁用）
├── DPU OPP 只保留 384 MHz（显示不花屏的关键）
├── wifi: vdd-3.3-ch1-supply
├── bluetooth: vddrf-supply + vddch0-supply
└── serial@4a8c000: pinctrl-0 = <0x57>（qup3 四线）
```

## D. 下一步

1. 启动 A 槽 Android，抓 `dmesg | grep -iE "qca|bt|hci|4a8c000"`，
   确认蓝牙真实所用的 UART 实例、GPIO、稳压器
2. 对照后修正 DTB
3. WiFi 同理（ath10k_snoc 加载了但无接口，需按 dmesg 的实际固件请求路径摆放）

## E. 系统状态

| 项目 | 状态 |
|---|---|
| 显示 1200x1920 + DSC + 亮度可调 | ✅ |
| DPU 时钟 384 MHz 锁定 | ✅ |
| GPU（freedreno FD610） | ✅ |
| Niri / 串口 / 676 个内核模块 | ✅ |
| 蓝牙 | 🟡 UART+serdev+hci0 全部就绪，芯片不应答 |
| WiFi | 🟡 驱动加载，无接口 |
| 触控 | ❌ DLM 写入 CRC 不符 |
| 90Hz | ⬜ 未切换 |

镜像：`boot_b` = `boot_wifi2.img`，`vendor_boot_b` = `vb_bt4p.img`

---

# 附录：第二十二轮 —— 从 A 槽抓到真相（WiFi/蓝牙共同根因）

## A. 方法：直接抓厂商运行时设备树

```sh
adb pull /sys/firmware/fdt  vendor.fdt     # 421,641 字节
dtc -f -I dtb -O dts -o vendor.dts vendor.fdt   # 605 KB
```
这是**最权威的参照** —— 比反编译原厂 boot.img 里的 DTB 更准确（含 ABL 补丁后的结果）。

## B. 根因：我们的 DTB 完全缺少 PMIC 稳压器定义

```
我们的 CANONICAL.dts :  rpm-smd-regulator 节点 = 0
厂商 vendor.dts      :  rpm-smd-regulator 节点 = 68
```

厂商有一个 `qcom,rpm-smd { rpm-requests { ... } }` 节点（vendor.dts L3159 起），
里面定义了全部 LDO/BOB/SMP。**我们完全没有**。

后果：Linux 内核里所有 `*-supply` 请求都回落到 **dummy 稳压器**，
**外设根本没有真正上电**：

```
ath10k_snoc: supply vdd-3.3-ch1 not found, using dummy regulator
Bluetooth:   hci0: command 0xfc00 tx timeout   ← 芯片没电，自然不应答
```

这解释了 WiFi 和蓝牙**同时**不工作的原因，而且是一个根因。

## C. 厂商的真实供电映射（关键数据）

从 vendor.dts 的 `bt_wcn3990` 节点提取：

| 功能 | 厂商属性 | 稳压器 | 电压 |
|---|---|---|---|
| BT IO | `qca,bt-vdd-io-supply` | **pm6125_l9** | 1.7–1.9V |
| BT core | `qca,bt-vdd-core-supply` | **pm6125_l17** | 1.2V |
| BT PA | `qca,bt-vdd-pa-supply` | **pm6125_l23** | 3.0–3.3V |
| BT xtal | `qca,bt-vdd-xtal-supply` | **pm6125_l16** | 1.7–1.9V |
| BT 使能 | `qca,bt-sw-ctrl-gpio` | **tlmm GPIO 87** | — |

WiFi（厂商走 `qcom,icnss`，非 ath10k）：
```
vdd-3.3-ch0-supply = pm6125_l23
vdd-1.3-rfa-supply = pm6125_l17
vdd-1.8-xo-supply  = pm6125_l16
vdd-cx-mx-supply   = 另一个（0x1b0）
```

**注意**：我们 CANONICAL.dts 里 BT 节点当前的 `vddio=<0x4c>`、`vddxo=<0x59>`
指向的完全是别的节点 —— 也要一并改成 l9/l16/l17/l23。

## D. 其他确认的差异

| 项目 | 厂商 | 我们 | 结论 |
|---|---|---|---|
| 蓝牙节点 | 独立 `/soc/bt_wcn3990`，`compatible="qcom,wcn3990"`（WCNSS 风格） | `serial@4a8c000/bluetooth`，`qcom,wcn3990-bt`（serdev 风格） | 主线用 serdev 是对的，但**供电必须按厂商那套配** |
| WiFi | `qcom,icnss@C800000`（CNSS 专有栈） | `qcom,wcn3990-wifi`（ath10k） | 主线用 ath10k 是对的 |
| 触控 | `novatek@62`（I2C）**和** SPI 节点并存 | `touchscreen@1`（SPI） | 主线走 SPI 能读到 PID(84D3)，方向正确 |

## E. 下一步（明确的移植任务）

**把厂商的 `qcom,rpm-smd` 稳压器整块移植进 CANONICAL.dts**：

1. 从 `ref/android/vendor.dts` 提取 `qcom,rpm-smd { rpm-requests { ... } }`（L3159 起，含 68 个 regulator）
2. 处理 phandle 冲突：vendor 的 phandle 数值会和我们现有的冲突 →
   方案：给需要的 regulator 节点加**label**（如 `pm6125_l9: "pm6125_l9" { ... }`），
   并把内部引用改成 `&pm6125_l9` 形式
3. 把 BT 节点改成：
   ```dts
   vddio-supply  = <&pm6125_l9>;
   vddrf-supply  = <&pm6125_l17>;
   vddch0-supply = <&pm6125_l23>;
   vddxo-supply  = <&pm6125_l16>;
   ```
   WiFi 节点同理改成 l16/l17/l23
4. 重建 DTB → 刷 vendor_boot → 验证：
   - `regulator_summary` 里这些 LDO 应显示真实电压（不再是 0mV）
   - 蓝牙应能回 `0xFC00`
   - WiFi 应能请求到 wlanmdsp.mbn

**这是 WiFi + 蓝牙的共同前置条件，值得优先做。**

## F. 本轮已解决/确认的清单

已解决：
- 别名路径 `/soc@0/` → `/soc/`（修好 `Invalid line -19`）
- BT UART 的 `pinctrl-0`（qup3 四线 gpio8-11）
- BT 节点补齐 `vddrf`/`vddch0`（名字对，但指向的稳压器还需按 C 节修正）

已确认瓶颈：
- **PMIC 稳压器子系统整体缺失** —— 这是 WiFi/蓝牙不工作的根因

## G. 文件与镜像

- 厂商运行时 DT：`ref\android\vendor.fdt` / `vendor.dts`（605 KB，最权威参照）
- 权威基线：`build\CANONICAL.dts`
- 镜像：`boot_b` = `boot_wifi2.img`，`vendor_boot_b` = `vb_bt4p.img`

---

# 附录：第二十二轮【更正】—— PMIC 稳压器并不缺失

## ⚠️ 前一节的结论是错的，以此节为准

上节写"我们的 DTB 完全缺少 PMIC 稳压器定义（0 个 rpm-smd-regulator）"，
**这是检查脚本的缩进匹配错误导致的误判**。真实情况：

我们的 `CANONICAL.dts` 在 `remoteproc/glink-edge/rpm-requests/regulators-0`
（L489 起）里，用**老式单节点绑定** `compatible = "qcom,rpm-pm6125-regulators"`
定义了 13 个稳压器：

```
l4  → 0x2d    l5  → 0x3f    l8  → 0xa7    l9  → 0x4c
l11 → 0x42    l12 → 0x2e    l15 → 0x2f    l16 → 0x59
l17 → 0xa8    l18 → 0x43    l22 → 0x3e    l23 → 0xa9
l24 → 0x41
```

而厂商用的是**新式绑定**（`qcom,rpm-smd-regulator-resource` + `qcom,rpm-smd-regulator`，
68 个节点）。两种绑定内核都支持（`CONFIG_REGULATOR_QCOM_SMD_RPM=y`），
所以数量差异只是**写法不同**，不是缺失。

## 映射核对（全部正确）

| 用途 | 我们 DT 里的属性 | phandle | 对应稳压器 | Android 实测 |
|---|---|---|---|---|
| BT vddio | `vddio-supply = <0x4c>` | 0x4c | **l9** | 1800000 uV enabled ✅ |
| BT vddxo | `vddxo-supply = <0x59>` | 0x59 | **l16** | 1800000 uV enabled ✅ |
| BT vddrf | `vddrf-supply = <0xa8>` | 0xa8 | **l17** | 1304000 uV enabled ✅ |
| BT vddch0 | `vddch0-supply = <0xa9>` | 0xa9 | **l23** | 3200000 uV enabled ✅ |

**结论：蓝牙的供电配置从一开始就是对的，不需要移植稳压器。**
（WiFi 的 `vdd-3.3-ch1` 确实不存在 —— 但厂商 ICNS S 节点也只有 `ch0`，
主线 ath10k 请求 ch1 会回落 dummy，这属于次要问题。）

## 蓝牙仍需排查的方向（更新后）

1. **稳压器是否真的被使能**：Linux 侧要查
   `/sys/class/regulator/*/state`（不只是 `regulator_summary` 的电压列，
   该列对 RPM 稳压器常显示 0mV，不代表没开）
2. **GPIO 87（sw_ctrl / BT 使能）**：厂商 `qca,bt-sw-ctrl-gpio = <&tlmm 0x57>`，
   主线 `hci_qca` 只**读** `swctrl-gpios` 不驱动它 —— 如果硬件需要它拉高才能开机，
   就得在 DT 里加 `swctrl-gpios` 并确认其默认电平
3. **UART 流控/RTS**：厂商日志有 `BT_CMD_CHECK_SW_CTRL`，说明它在检查这个脚
4. 对照 Android 侧的运行时 UART 参数（Android 显示 `ttyHS0 ... irq = 174`）

## 方法教训

检查 DTS 节点是否存在时，**不要用依赖缩进的 awk 正则**（`^\t+\t+` 之类），
本项目里标签层级经常与预期差一层。应改用 Python 解析大括号配对（见
`tools/map_our_ldos.sh` 里内嵌的 python 片段）。

---

# 附录：第二十三轮 —— ADSP 启动成功（重要基础设施打通）

## A. 方法：从 NON-HLOS.bin 提取 DSP 固件并用符号链接骗过加载器

`NON-HLOS.bin`（FAT 镜像）里藏着完整的 DSP 固件分片：

```
adsp.mdt + 35 个 adsp.bNN     （ADSP 固件）
cdsp.mdt + 10 个 cdsp.bNN     （CDSP 固件）
modem.mdt + 21 个 modem.bNN   （modem）
```

提取：`sudo mount -o loop,ro NON-HLOS.bin /mnt/nh` → `/mnt/nh/image/*`
脚本：`tools/stage_dsp_fw.sh`

**关键技巧**：DT 里 `firmware-name = ".../adsp.mbn"`，而厂商给的是分片格式
（`.mdt` + `.bNN`）。主线 `qcom_q6v5_pas` 只按 DT 名字请求，**不会自动回退找 .mdt**。
解法：

```sh
ln -sf adsp.mdt adsp.mbn
ln -sf cdsp.mdt cdsp.mbn
```

因为 `adsp.mdt` 本身就是 ELF 头 + 分片索引，伪装成 `.mbn` 后
`qcom_mdt_load` 能正确解析并加载所有分片。

**结果**：
```
remoteproc1: adsp state=running     ← 成功！
remoteproc1: Booting fw image .../adsp.mbn, size 9580
remoteproc1: remote processor adsp is now up
fastrpc compute-cb@3..7 全部创建
```

可以**不重启**直接启动：`echo start > /sys/class/remoteproc/remoteproc1/state`

## B. CDSP 仍失败（不影响 WiFi）

```
qcom_q6v5_pas b300000.remoteproc: error -22 reading firmware .../cdsp.mbn metadata
```
`.mdt` 的元数据不被接受（可能 cdsp 的 mdt 格式/偏移不同）。
CDSP 主要给摄像头/音频用，对 WiFi 不是必需。

## C. WiFi 现状

`ath10k_snoc` 绑定成功、ADSP 已 running，但 probe 仍然停在
`Adding to iommu group 7` 之后，没有固件请求、没有 wiphy、没有接口。

**已排除**：固件缺失（`wlanmdsp.mbn`/`bdwlan.*` 都已就位）、稳压器（l9/l16/l17/l23
全部 enabled 且电压正确）、ADSP 未启动（现已 running）。

**下一步怀疑**：
1. `ath10k_qmi` 需要 QRTR 上的 `WLFW` 服务，而该服务可能由 **WLAN 子系统自身**
   或 **CDSP** 提供 → 需要把 CDSP 也弄起来
2. DT 的 `firmware-name = "lenovo-tb128fu"` 会被当作 board name 去拼 BDF 路径，
   实际请求的文件名需要从 dmesg 确认（目前根本没到请求固件那一步）
3. 可能需要 `qcom,wlan-msa-fixed-region` 内存区的正确配置（厂商用 icnss）

## D. 当前系统状态

| 项目 | 状态 |
|---|---|
| 显示 1200x1920 + 背光亮度可调 | ✅ |
| DPU 时钟 384 MHz 锁定 | ✅ |
| GPU（freedreno FD610） | ✅ |
| Niri / USB 串口 / 内核模块 | ✅ |
| **ADSP（远程处理器）** | ✅ **本轮打通** |
| Bluetooth | 🟡 UART/serdev/hci0/引脚/供电/电压全部正确，芯片仍不应答 |
| WiFi | 🟡 驱动绑定、ADSP 就绪，probe 卡住 |
| 触控 | ❌ DLM 写入 CRC 不符 |
| 90Hz | ⬜ 未切换 |

**镜像**：`boot_b` = `boot_wifi2.img`，`vendor_boot_b` = `vb_l17.img`

**固件资产**（都在 SD 卡 `fwtest/` 和 PC `firmware/`）：
```
wifi/    wlanmdsp.mbn + 34 个 bdwlan.*
bt/      crbtfw21.tlv, crnv21.bin
dsp/     adsp.mdt + 35 分片, cdsp.mdt + 10 分片
modules-6.14.tar.gz   676 个 .ko
```

## E. 蓝牙的进展盘点（本轮全部验证过）

| 检查项 | 结果 |
|---|---|
| UART 实例 | ✅ `4a8c000`（与 Android 一致） |
| UART 引脚 | ✅ gpio8-11 / 功能 qup3（与厂商 DT 一致） |
| serdev / hci0 | ✅ 已创建 |
| 4 路稳压器 | ✅ l9/l16/l17/l23 全部 enabled |
| 电压 | ✅ l9=1.8V l16=1.7V l17=1.304V(已修正) l23=3.2V |
| GPIO 87 | 是状态反馈脚，非使能脚（已排除） |
| 芯片响应 | ❌ 仍 `command 0xfc00 tx timeout` |

**结论**：软件侧能查的都正确了。剩下只能在硬件/固件层排查
（例如用示波器看 UART 波形，或对照 Android 的 geni UART 寄存器配置）。
