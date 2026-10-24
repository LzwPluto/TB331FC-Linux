# 从你自己的设备提取厂商固件

本仓库**不附带任何厂商固件**（版权原因）。下面是从你自己的 TB331FC 上
提取所需固件的完整方法。

前提：设备能启动 Android（A 槽原系统），电脑有 `adb`。

---

## 1. 从 Android 的 `/vendor/firmware` 直接拉取（最简单）

```sh
adb pull /vendor/firmware/ ./vendor-firmware/
```

需要的文件：

| 用途 | 文件名 |
|---|---|
| GPU SQE | `a630_sqe.fw` |
| GPU ZAP | `a610_zap.mdt` + `a610_zap.b00` + `a610_zap.b01` + `a610_zap.b02` |
| 触控 | `novatek_ts_fw.bin`（INX 面板用这个） |
| 触控备选 | `novatek_ts_mp.bin` / `novatek_ts_fw_csot.bin` / `novatek_ts_mp_csot.bin` |
| 手写笔 | `Himax_firmware.bin` |

放置位置（Alpine/Debian 根文件系统内）：

```
/lib/firmware/qcom/a630_sqe.fw
/lib/firmware/qcom/sm6225/LENOVO/TB128FU/a610_zap.mdt
/lib/firmware/qcom/sm6225/LENOVO/TB128FU/a610_zap.b00 .. b02
/lib/firmware/novatek_ts_fw.bin
/lib/firmware/Himax_firmware.bin
```

> 注意：`a610_zap.*` 的路径来自 DTB 里 `zap-shader { firmware-name = ... }`，
> 如果你的 DTB 用别的路径，按 DTB 来。

---

## 2. WiFi 固件：在 `NON-HLOS.bin` 里（FAT 镜像）

`NON-HLOS.bin` 是一个 FAT 文件系统镜像，里面有 WLAN 固件和 DSP 固件。

```sh
mkdir -p /mnt/nh
sudo mount -o loop,ro NON-HLOS.bin /mnt/nh
ls /mnt/nh/image/            # 里面是 adsp.* / cdsp.* / modem.* / wlanmdsp.mbn / bdwlan.*
sudo cp /mnt/nh/image/wlanmdsp.mbn  /mnt/nh/image/bdwlan.*  ./wifi/
sudo cp /mnt/nh/image/adsp.* ./dsp/
sudo cp /mnt/nh/image/cdsp.* ./dsp/
sudo umount /mnt/nh
```

`NON-HLOS.bin` 通常在官方的刷机包（fastboot ROM）里。

放置位置：

```
/lib/firmware/qcom/wlanmdsp.mbn
/lib/firmware/lenovo-tb128fu/bdwlan.*        （DT 里 firmware-name = "lenovo-tb128fu"）
/lib/firmware/qcom/sm6225/LENOVO/TB128FU/adsp.mdt + adsp.bNN
/lib/firmware/qcom/sm6225/LENOVO/TB128FU/cdsp.mdt + cdsp.bNN
```

**关键技巧**：DT 里写的是 `adsp.mbn`，而厂商给的是 `.mdt` + 分片。
`qcom_q6v5_pas` 不会自动回退，所以建符号链接：

```sh
cd /lib/firmware/qcom/sm6225/LENOVO/TB128FU
ln -sf adsp.mdt adsp.mbn
ln -sf cdsp.mdt cdsp.mbn
```

然后可以在**不重启**的情况下启动 ADSP：

```sh
echo start > /sys/class/remoteproc/remoteproc1/state
cat /sys/class/remoteproc/remoteproc1/state      # 应为 running
```

---

## 3. 蓝牙固件：在 `BTFM.bin` 里（FAT16 镜像）

```sh
mkdir -p /mnt/btfm
sudo mount -o loop,ro BTFM.bin /mnt/btfm
ls /mnt/btfm/image/          # crbtfw21.tlv crnv21.bin（WCN3990 用这两个）
sudo cp /mnt/btfm/image/crbtfw21.tlv /mnt/btfm/image/crnv21.bin ./bt/
sudo umount /mnt/btfm
```

放置位置（`btqca.c` 里写死的路径）：

```
/lib/firmware/qca/crbtfw21.tlv
/lib/firmware/qca/crnv21.bin
```

---

## 4. 内核模块（如果用 `=m` 编译）

蓝牙可以编进内核，但 WiFi 的 `ath10k_snoc` 依赖链里
`QCOM_RPROC_COMMON` 是隐藏符号、只能跟随 Q6V5 系列为 `=m`，所以 WiFi 只能走模块。

```sh
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
     INSTALL_MOD_PATH=./modroot modules_install
# 把 modroot/lib/modules/<ver>/ 整个拷贝到设备的 /lib/modules/
```

设备上：

```sh
depmod -a
modprobe ath10k_snoc
```

---

## 5. 交叉验证用的原始数据（可选）

想对照 Android 侧的真实配置时，这些最有价值：

```sh
adb pull /sys/firmware/fdt ./vendor.fdt          # 厂商运行时完整设备树！
dtc -f -I dtb -O dts -o vendor.dts vendor.fdt

# 稳压器实际电压
adb shell 'for d in /sys/class/regulator/*; do n=$(cat $d/name); echo "$n $(cat $d/microvolts) $(cat $d/state)"; done'

# 蓝牙 / WiFi 初始化日志
adb shell 'dmesg | grep -iE "qca|icnss|wlan|4a8c000"'
```

`/sys/firmware/fdt` 是**最权威的参照** —— 它包含 ABL 打完补丁后的最终设备树，
比从原厂 `boot.img` 里反编译出来的更准确。
