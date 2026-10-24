#!/bin/bash
# The BT USB transports (btusb/btbcm/btmtk...) built as modules conflict with the
# built-in btqca symbols (modpost: "btbcm_setup_apple" undefined). We only need
# the QCA UART transport for WCN3990, so turn the USB ones off entirely.
set +e
cd ~/kbuild/linux-next-tb128fu-hx83102-panel-port

./scripts/config --file .config \
    --disable BT_HCIBTUSB \
    --disable BT_HCIBTUSB_AUTOSUSPEND \
    --disable BT_HCIBTUSB_BCM \
    --disable BT_HCIBTUSB_MTK \
    --disable BT_HCIBTUSB_POLL_SYNC \
    --disable BT_HCIBTUSB_RTL \
    --disable BT_HCIBTSDIO \
    --disable BT_HCIBTQCOMSMD \
    --disable BT_HCIUART_3WIRE \
    --disable BT_HCIUART_ATH3K \
    --disable BT_HCIUART_BCM \
    --disable BT_HCIUART_INTEL \
    --disable BT_HCIUART_LL \
    --disable BT_HCIUART_MRVL \
    --disable BT_HCIUART_H4 \
    --disable BT_HCIUART_BCSP

make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j10 olddefconfig >/dev/null 2>&1

echo "=== config ==="
for o in BT BT_HCIUART BT_HCIUART_QCA BT_QCA BT_HCIBTUSB BT_HCIBTQCOMSMD \
         ATH10K ATH10K_SNOC QCOM_QMI_HELPERS; do
    v=$(grep -E "^CONFIG_${o}=" .config || true)
    if [ -z "$v" ]; then printf "  %-22s NOT SET\n" "$o"; else printf "  %-22s %s\n" "$o" "$v"; fi
done

echo
echo "=== building modules ==="
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j10 modules 2>&1 | grep -E "ERROR|Error 1" | head -8 || true
n=$(find . -name '*.ko' | wc -l)
echo "  .ko built: $n"
if [ "$n" -gt 0 ]; then
    rm -rf /mnt/d/TB331FCLinux/build/modroot
    make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
        INSTALL_MOD_PATH=/mnt/d/TB331FCLinux/build/modroot modules_install 2>&1 | tail -3
    echo "  installed: $(find /mnt/d/TB331FCLinux/build/modroot -name '*.ko' | wc -l) .ko"
fi
