#!/bin/bash
# BTFM.bin is a FAT16 image holding the Bluetooth firmware partition.
set -u
SRC="/mnt/d/TB331FC_GSI_Kit/08_一键刷机/fw/BTFM.bin"
OUT=/mnt/d/TB331FCLinux/firmware/btfm
MNT=/tmp/btfm

mkdir -p "$OUT" "$MNT"
sudo mount -o loop,ro "$SRC" "$MNT" || { echo "mount failed"; exit 1; }

echo "=== files ==="
sudo find "$MNT" -type f -printf '%10s  %p\n' | head -30
echo
echo "=== copying ==="
sudo cp -rv "$MNT"/* "$OUT"/ 2>/dev/null || true
sudo chown -R "$(id -u):$(id -g)" "$OUT" 2>/dev/null
sudo umount "$MNT" 2>/dev/null
echo
echo "=== extracted ==="
find "$OUT" -type f -printf '%10s  %p\n' | head -20
echo "total: $(find "$OUT" -type f | wc -l) files, $(du -sh "$OUT" | cut -f1)"
