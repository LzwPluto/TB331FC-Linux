#!/bin/bash
# Build initramfs v16: init with switchroot support + firmware + helper scripts.
set -e
IR=/mnt/d/TB331FCLinux/initramfs
FW=/mnt/d/TB331FCLinux/firmware/vendor-firmware
STAGE=$IR/r16

rm -rf "$STAGE"
mkdir -p "$STAGE/lib/firmware/qcom/sm6225/LENOVO/TB128FU"

cp "$IR/init_v18"                    "$STAGE/init"
cp /mnt/d/TB331FCLinux/rootfs/busybox "$STAGE/busybox"
cp "$IR/diag.sh"                     "$STAGE/diag.sh"
cp "$IR/gadget.sh"                   "$STAGE/gadget.sh"
cp "$IR/switchroot.sh"               "$STAGE/switchroot.sh"
chmod +x "$STAGE/busybox" "$STAGE/diag.sh" "$STAGE/gadget.sh" "$STAGE/switchroot.sh"

cp "$FW/novatek_ts_fw.bin"  "$STAGE/lib/firmware/" || true
cp "$FW/Himax_firmware.bin" "$STAGE/lib/firmware/" || true
cp "$FW/a630_sqe.fw" "$STAGE/lib/firmware/qcom/" || true
for f in a610_zap.mdt a610_zap.b00 a610_zap.b01 a610_zap.b02; do
    cp "$FW/$f" "$STAGE/lib/firmware/qcom/sm6225/LENOVO/TB128FU/" || true
done

echo "--- contents ---"
ls -l "$STAGE"

cd "$STAGE"
find . | cpio -o -H newc 2>/dev/null > "$IR/initramfs_v18.cpio"
ls -l "$IR/initramfs_v18.cpio"
