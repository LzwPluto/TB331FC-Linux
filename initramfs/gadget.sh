#!/bin/busybox sh
# USB gadget for the TB331FC mainline port:
#   acm.GS0    -> /dev/ttyGS0   serial console (the only usable console)
#   rndis.usb0 -> usb0          USB networking (share the host's internet)
# Windows binds RNDIS with its inbox driver, so one USB-C cable gives us both a
# COM port and an IP link.
export PATH=/bin:/sbin:/usr/bin:/usr/sbin

G=/sys/kernel/config/usb_gadget/tb331fc

echo "[gadget] setting up CDC-ACM + RNDIS"
mkdir -p /sys/kernel/config 2>/dev/null
mount -t configfs none /sys/kernel/config 2>/dev/null

# tear down a previous instance if present
if [ -d "$G" ]; then
    echo "" > "$G/UDC" 2>/dev/null
    rm -f "$G/configs/c.1/acm.GS0" "$G/configs/c.1/rndis.usb0" 2>/dev/null
    rmdir "$G/functions/acm.GS0" "$G/functions/rndis.usb0" 2>/dev/null
    rmdir "$G/configs/c.1/strings/0x409" "$G/configs/c.1" 2>/dev/null
    rmdir "$G/strings/0x409" 2>/dev/null
    rmdir "$G" 2>/dev/null
fi

mkdir -p "$G"
cd "$G" || exit 1

echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

mkdir -p strings/0x409
echo "TB331FCLINUX0001" > strings/0x409/serialnumber
echo "Lenovo"           > strings/0x409/manufacturer
echo "TB331FC mainline" > strings/0x409/product

mkdir -p configs/c.1
mkdir -p configs/c.1/strings/0x409
echo "CDC ACM + RNDIS" > configs/c.1/strings/0x409/configuration
echo 500 > configs/c.1/MaxPower

# serial console
mkdir -p functions/acm.GS0
ln -sf functions/acm.GS0 configs/c.1/ 2>/dev/null

# USB networking, RNDIS so Windows has an inbox driver for it
mkdir -p functions/rndis.usb0
echo "02:1d:6b:01:04:01" > functions/rndis.usb0/dev_addr  2>/dev/null
echo "02:1d:6b:01:04:02" > functions/rndis.usb0/host_addr 2>/dev/null
ln -sf functions/rndis.usb0 configs/c.1/ 2>/dev/null

UDC=$(ls /sys/class/udc 2>/dev/null | head -1)
if [ -z "$UDC" ]; then
    echo "[gadget] no UDC found - gadget not attached"
    ls /sys/class/udc 2>/dev/null
    exit 1
fi
echo "$UDC" > UDC
echo "[gadget] attached to $UDC"

# wait for the tty to appear
for i in 1 2 3 4 5 6 7 8 9 10; do
    if [ -c /dev/ttyGS0 ]; then
        echo "[gadget] /dev/ttyGS0 ready"
        ls /sys/class/net | grep -q usb && echo "[gadget] usb0 ready"
        exit 0
    fi
    sleep 1
done
echo "[gadget] ttyGS0 did not appear"
ls /dev | grep -i ttyGS
exit 1
