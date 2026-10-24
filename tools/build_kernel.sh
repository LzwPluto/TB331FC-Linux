#!/bin/bash
# Build a TB331FC-friendly kernel from the tb128fu linux-next tree.
#
# The shipped TB128FU kernel has the drivers we need compiled as MODULES
# (CONFIG_SPI_QCOM_GENI=m, CONFIG_INPUT_HIMAX_V3_MMI=m) and we have no modules
# in the initramfs, so those peripherals never come up.  Build them in (=y).
set -e

SRC=~/kbuild/linux-next-tb128fu-hx83102-panel-port
cd "$SRC"

export ARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb331fc
export KBUILD_BUILD_HOST=build
JOBS=${JOBS:-10}

echo "=== defconfig ==="
make -s tb128fu_defconfig

echo "=== config deltas ==="
CFG=./scripts/config
# built-in instead of modules: these are what block touch / SPI / backlight
$CFG --file .config --enable  SPI_QCOM_GENI
$CFG --file .config --enable  INPUT_HIMAX_V3_MMI
$CFG --file .config --enable  BACKLIGHT_PWM
$CFG --file .config --enable  INPUT_TOUCHSCREEN
# filesystems we need to mount the SD card (were modules)
$CFG --file .config --enable  VFAT_FS
$CFG --file .config --enable  MSDOS_FS
$CFG --file .config --enable  EXFAT_FS
$CFG --file .config --enable  NLS_CODEPAGE_437
$CFG --file .config --enable  NLS_ISO8859_1
# USB serial gadget (handy for a serial console over USB-C)
$CFG --file .config --enable  USB_CONFIGFS
$CFG --file .config --enable  USB_CONFIGFS_ACM
# keep the build lean and avoid needing pahole for BTF
$CFG --file .config --disable DEBUG_INFO_BTF
$CFG --file .config --disable DEBUG_INFO
$CFG --file .config --disable DEBUG_INFO_DWARF5
$CFG --file .config --disable DEBUG_INFO_DWARF4
$CFG --file .config --disable DEBUG_INFO_NONE

echo "=== olddefconfig ==="
make -s olddefconfig

echo "=== verify key options ==="
for o in SPI_QCOM_GENI INPUT_HIMAX_V3_MMI BACKLIGHT_PWM DRM_MSM DRM_PANEL_HIMAX_HX83102 TYPEC_RT1711H; do
    grep -E "^CONFIG_${o}=" .config || echo "CONFIG_${o} is not set"
done

echo "=== build Image (-j$JOBS) ==="
time make -j"$JOBS" Image

echo "=== result ==="
ls -l arch/arm64/boot/Image
cp arch/arm64/boot/Image ~/kbuild/Image-tb331fc
ls -l ~/kbuild/Image-tb331fc
echo "BUILD OK"
