#!/bin/bash
# Build WiFi (ath10k + WCN3990) and Bluetooth (hci_qca) into the kernel instead
# of modules: the Alpine rootfs on this tablet has no /lib/modules at all.
set -e
cd ~/kbuild/linux-next-tb128fu-hx83102-panel-port

./scripts/config --file .config \
    --enable CFG80211 \
    --enable MAC80211 \
    --enable RFKILL \
    --enable ATH10K \
    --enable ATH10K_SNOC \
    --enable CRYPTO_CCM --enable CRYPTO_GCM \
    --enable BT --enable BT_HCIUART --enable BT_HCIUART_QCA --enable BT_QCA \
    --enable BT_QCA_QCA6174 2>/dev/null || true

make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j10 olddefconfig >/dev/null 2>&1

echo "=== resulting config ==="
for o in CFG80211 MAC80211 RFKILL ATH10K ATH10K_SNOC BT BT_HCIUART BT_HCIUART_QCA BT_QCA; do
    v=$(grep -E "^CONFIG_${o}=" .config)
    if [ -z "$v" ]; then printf "  %-20s NOT SET\n" "$o"; else printf "  %-20s %s\n" "$o" "$v"; fi
done

echo
echo "=== building ==="
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j10 Image 2>&1 | grep -E "error|Error|warning: .*ath10k" | head -10
cp arch/arm64/boot/Image /mnt/d/TB331FCLinux/build/Image-wifi
echo "BUILD_OK  $(ls -l /mnt/d/TB331FCLinux/build/Image-wifi | awk '{print $5}') bytes"
