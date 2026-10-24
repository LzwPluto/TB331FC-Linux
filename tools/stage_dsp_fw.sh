#!/bin/bash
set +u
SRC="/mnt/d/TB331FC_GSI_Kit/08_一键刷机/fw/NON-HLOS.bin"
MNT=/tmp/nh
OUT=/mnt/d/TB331FCLinux/firmware/nonhlos

if ! mountpoint -q "$MNT" 2>/dev/null; then
    mkdir -p "$MNT"
    sudo mount -o loop,ro "$SRC" "$MNT" || { echo "mount failed"; exit 1; }
fi

echo "=== main files (mdt/mbn) for adsp/cdsp/modem ==="
ls "$MNT/image" | grep -iE "^(adsp|cdsp|modem)\.(mdt|mbn)$" | head
echo
echo "=== counts ==="
echo "  adsp.bNN : $(ls "$MNT/image" | grep -cE '^adsp\.b[0-9]+$')"
echo "  cdsp.bNN : $(ls "$MNT/image" | grep -cE '^cdsp\.b[0-9]+$')"
echo "  modem.bNN: $(ls "$MNT/image" | grep -cE '^modem\.b[0-9]+$')"

echo
echo "=== copy adsp + cdsp entire sets ==="
sudo cp "$MNT"/image/adsp.*  "$OUT"/ 2>/dev/null
sudo cp "$MNT"/image/cdsp.*  "$OUT"/ 2>/dev/null
sudo chown -R "$(id -u):$(id -g)" "$OUT" 2>/dev/null
sudo umount "$MNT" 2>/dev/null

echo "=== staged ==="
echo "  adsp.* : $(ls "$OUT" | grep -cE '^adsp\.')"
echo "  cdsp.* : $(ls "$OUT" | grep -cE '^cdsp\.')"
du -sh "$OUT"
