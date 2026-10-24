#!/bin/bash
# Extract the WCN3990 WiFi firmware set (wlanmdsp.mbn + bdwlan.*) from the
# factory NON-HLOS.bin into a staging dir.
set -u
SRC="/mnt/d/TB331FC_GSI_Kit/08_一键刷机/fw/NON-HLOS.bin"
OUT=/mnt/d/TB331FCLinux/firmware/nonhlos
MNT=/tmp/nh

mkdir -p "$OUT"
if ! mountpoint -q "$MNT" 2>/dev/null; then
    mkdir -p "$MNT"
    sudo mount -o loop,ro "$SRC" "$MNT" || { echo "mount failed"; exit 1; }
fi

echo "=== bdwlan files in image ==="
ls "$MNT/image" | grep -i bdwlan | head -40
echo
echo "=== copying ==="
sudo cp "$MNT"/image/wlanmdsp.mbn "$OUT"/ 2>/dev/null
sudo cp "$MNT"/image/bdwlan.* "$OUT"/ 2>/dev/null
sudo chown -R "$(id -u):$(id -g)" "$OUT" 2>/dev/null
sudo umount "$MNT" 2>/dev/null
echo
ls -l "$OUT" | head -8
echo "total: $(ls -1 "$OUT" | wc -l) files, $(du -sh "$OUT" | cut -f1)"
