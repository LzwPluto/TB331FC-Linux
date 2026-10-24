#!/bin/bash
# Generate unified diffs (git-applyable, a/ b/ prefixes) between the pristine
# kernel zip and our modified tree.
set +e

ZIP="/mnt/c/Users/Pluto/Desktop/linux-next-tb128fu-hx83102-panel-port.zip"
TREE="$HOME/kbuild/linux-next-tb128fu-hx83102-panel-port"
ORIG=/tmp/korig
OUT=/mnt/d/TB331FCLinux/release/patches

mkdir -p "$OUT"
rm -f "$OUT"/*.patch

if [ ! -d "$ORIG" ]; then
    echo "extracting pristine tree..."
    mkdir -p "$ORIG"
    unzip -q "$ZIP" -d "$ORIG"
fi
BASE=$(find "$ORIG" -maxdepth 1 -mindepth 1 -type d | head -1)
echo "pristine base: $BASE"

FILES="
drivers/gpu/drm/panel/panel-himax-hx83102.c
drivers/gpu/drm/msm/dsi/dsi_host.c
drivers/gpu/drm/msm/msm_mdss.c
drivers/input/touchscreen/nt36523_ts.c
drivers/input/touchscreen/nt36523.h
"

n=1
for f in $FILES; do
    a="$BASE/$f"
    b="$TREE/$f"
    [ -f "$a" ] || { echo "  SKIP (missing in pristine): $f"; continue; }
    [ -f "$b" ] || { echo "  SKIP (missing in tree): $f"; continue; }
    if diff -q "$a" "$b" >/dev/null 2>&1; then
        echo "  unchanged: $f"
        continue
    fi
    name=$(basename "$f" .c)
    name=$(basename "$name" .h)
    out="$OUT/000${n}-${name}.patch"
    diff -u --label "a/$f" --label "b/$f" "$a" "$b" > "$out"
    echo "  $(basename "$out")  ($(wc -l < "$out") lines)  <- $f"
    n=$((n+1))
done

echo
echo "=== patches ==="
ls -l "$OUT"
echo
echo "=== verify they apply cleanly (dry run) ==="
cd "$BASE" || exit 1
for p in "$OUT"/*.patch; do
    if patch -p1 --dry-run -s -f < "$p" >/dev/null 2>&1; then
        echo "  OK   $(basename "$p")"
    else
        echo "  FAIL $(basename "$p")"
    fi
done
