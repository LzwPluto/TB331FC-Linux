#!/bin/busybox sh
# Hand over from the initramfs to the Alpine rootfs on the SD card.
#
# DEBUG build: after mounting, drop into /bin/sh inside the new root instead of
# exec'ing /sbin/init, so we can reproduce the init failure by hand.
export PATH=/bin:/sbin:/usr/bin:/usr/sbin

say() { echo "[switchroot] $*"; }

if [ ! -f /mnt/alpine-rootfs.img ]; then
    say "no /mnt/alpine-rootfs.img"; exit 1
fi

mkdir -p /newroot

LOOP=$(losetup -f 2>/dev/null)
[ -z "$LOOP" ] && { say "no free loop"; exit 1; }

losetup "$LOOP" /mnt/alpine-rootfs.img || { say "losetup failed"; exit 1; }
say "$LOOP -> /mnt/alpine-rootfs.img"

mount -t ext4 "$LOOP" /newroot || { say "ext4 mount failed"; exit 1; }
say "ext4 mounted"

echo "[switchroot] --- diagnostics ---"
echo "  /newroot:      $(ls /newroot | tr '\n' ' ')"
ls -l /newroot/sbin/init 2>/dev/null
ls /newroot/dev 2>/dev/null | head -5 | tr '\n' ' '; echo " <- /newroot/dev before move"

# move the configfs submount too, otherwise the USB gadget configured
# in the initramfs is orphaned and /dev/ttyGS0 disappears
mkdir -p /newroot/sys/kernel/config
mount --move /sys/kernel/config /newroot/sys/kernel/config && echo "  moved configfs"

for d in proc sys dev; do
    if mount --move "/$d" "/newroot/$d"; then
        echo "  moved /$d"
    else
        echo "  FAILED to move /$d"
    fi
done

echo "  /newroot/dev:  $(ls /newroot/dev 2>/dev/null | head -8 | tr '\n' ' ')"

# make sure the console exists even if devtmpfs was not moved
if [ ! -e /newroot/dev/console ]; then
    echo "  /newroot/dev/console missing -> creating"
    mknod /newroot/dev/console c 5 1 2>/dev/null
    mknod /newroot/dev/null    c 1 3 2>/dev/null
    mknod /newroot/dev/tty     c 5 0 2>/dev/null
fi

echo "[switchroot] --- entering /bin/sh in the new root (debug) ---"
echo "[switchroot] try:  /sbin/init   or   /sbin/openrc sysinit"

exec /bin/busybox switch_root /newroot /sbin/init
