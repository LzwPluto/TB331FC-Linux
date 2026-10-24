#!/bin/bash
# Extract the WiFi firmware from the factory NON-HLOS.bin (FAT image).
set -u
SRC="/mnt/d/TB331FC_GSI_Kit/08_一键刷机/fw/NON-HLOS.bin"
OUT=/mnt/d/TB331FCLinux/firmware/nonhlos
MNT=/tmp/nh

if [ ! -f "$SRC" ]; then echo "missing $SRC"; exit 1; fi
mkdir -p "$OUT"

if sudo -n true 2>/dev/null; then
    echo "have root; mounting"
    mkdir -p "$MNT"
    if sudo mount -o loop,ro "$SRC" "$MNT" 2>&1; then
        echo "=== mounted, top level ==="
        ls "$MNT" | head -20
        echo "=== copying firmware-ish files ==="
        sudo find "$MNT" -maxdepth 2 -type f \( -iname '*wlanmdsp*' -o -iname '*bdwlan*' -o -iname '*.mbn' \) | head -20
        sudo cp -v "$MNT"/wlanmdsp.mbn "$OUT"/ 2>/dev/null || true
        sudo find "$MNT" -iname '*wlanmdsp*' -exec cp -v {} "$OUT"/ \;
        sudo umount "$MNT"
        echo "=== extracted ==="
        ls -l "$OUT"
        exit 0
    fi
    echo "mount failed"
else
    echo "no passwordless sudo"
fi

echo "=== fallback: carve wlanmdsp.mbn by searching for its FAT entry ==="
python3 - "$SRC" "$OUT" <<'PYEOF'
import sys, re
src, out = sys.argv[1], sys.argv[2]
data = open(src, 'rb').read()
name = b'WLANMDSPMBN'
idx = data.find(name)
print('FAT entry at', idx if idx >= 0 else 'not found')
if idx >= 0:
    # FAT 8.3 dir entry: name[11], attr[1], ..., cluster_hi[2] at 20, size[4] at 28
    ent = data[idx-0:idx+11]
    raw = data[idx:idx+32]
    size = int.from_bytes(raw[28:32], 'little')
    start = int.from_bytes(raw[26:28], 'little')
    print('size', size, 'start cluster', start)
PYEOF
