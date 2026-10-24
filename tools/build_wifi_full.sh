#!/bin/bash
# Rebuild in the right order: vmlinux first (so Module.symvers has the built-in
# symbols), then modules, then install them to a staging tree.
cd ~/kbuild/linux-next-tb128fu-hx83102-panel-port || exit 1

echo "=== 1/3 Image (vmlinux) ==="
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j10 Image 2>&1 | grep -E "Error|error:" | head -5
ls -l arch/arm64/boot/Image | awk '{print "  Image:", $5, "bytes"}'

echo "=== 2/3 modules ==="
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j10 modules 2>&1 | grep -E "Error|ERROR" | head -8
n=$(find . -name '*.ko' | wc -l)
echo "  .ko built: $n"
if [ "$n" -eq 0 ]; then echo "NO MODULES BUILT"; exit 1; fi

echo "=== 3/3 modules_install ==="
rm -rf /mnt/d/TB331FCLinux/build/modroot
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
     INSTALL_MOD_PATH=/mnt/d/TB331FCLinux/build/modroot modules_install 2>&1 | tail -3
echo "  installed: $(find /mnt/d/TB331FCLinux/build/modroot -name '*.ko' | wc -l) .ko"

cp arch/arm64/boot/Image /mnt/d/TB331FCLinux/build/Image-wifi2
echo "DONE"
