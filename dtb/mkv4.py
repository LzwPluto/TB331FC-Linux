#!/usr/bin/env python3
"""mkv4.py - build Android GKI boot / init_boot / vendor_boot images (header v4).

Layouts (all little-endian, sections page-aligned):

  boot_img_hdr_v4 (1584 bytes)
    0x000 magic[8] = "ANDROID!"
    0x008 kernel_size u32
    0x00c ramdisk_size u32
    0x010 os_version u32
    0x014 header_size u32 = 1584
    0x018 reserved[4]
    0x028 header_version u32 = 4
    0x02c cmdline[1536]
    -> kernel, ramdisk at page-aligned offsets

  vendor_boot_img_hdr_v4 (2128 bytes)
    0x000 magic[8] = "VNDRBOOT"
    0x008 header_version u32 = 4
    0x00c page_size u32
    0x010 kernel_addr u32
    0x014 ramdisk_addr u32
    0x018 vendor_ramdisk_size u32
    0x01c cmdline[2048]
    0x81c tags_addr u32
    0x820 name[16]
    0x830 header_size u32 = 2128
    0x834 dtb_size u32
    0x838 dtb_addr u64
    0x840 vendor_ramdisk_table_size u32
    0x844 vendor_ramdisk_table_entry_num u32
    0x848 vendor_ramdisk_table_entry_size u32 = 108
    0x84c bootconfig_size u32
    -> vendor_ramdisk, vendor_ramdisk_table, dtb, bootconfig at page offsets

  vendor_ramdisk_table_entry_v4 (108 bytes)
    0x00 ramdisk_size u32
    0x04 ramdisk_offset u32
    0x08 ramdisk_type u32   (0=PLATFORM 1=RECOVERY 2=NONE)
    0x0c ramdisk_name[32]
    0x2c board_id[16] u32   (0xffffffff = match any)
"""
import argparse, struct, os

PAGE = 4096


def align(n, p=PAGE):
    return (n + p - 1) // p * p


def pad(buf):
    return buf + b'\0' * (align(len(buf)) - len(buf))


def write(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    open(path, 'wb').write(data)
    print(f'  {path}: {len(data)} bytes (0x{len(data):x})')


def mk_boot(kernel=b'', ramdisk=b'', cmdline='', host_os=None, out='boot.img'):
    hdr = bytearray(1584)
    hdr[0:8] = b'ANDROID!'
    struct.pack_into('<I', hdr, 0x008, len(kernel))
    struct.pack_into('<I', hdr, 0x00c, len(ramdisk))
    struct.pack_into('<I', hdr, 0x010, host_os or 0)
    struct.pack_into('<I', hdr, 0x014, 1584)
    struct.pack_into('<I', hdr, 0x028, 4)
    cb = cmdline.encode()[:1535]
    hdr[0x02c:0x02c + len(cb)] = cb
    buf = pad(bytes(hdr))
    if kernel:
        buf += pad(kernel)
    if ramdisk:
        buf += pad(ramdisk)
    write(out, buf)
    return buf


def mk_init_boot(ramdisk, out='init_boot.img'):
    return mk_boot(kernel=b'', ramdisk=ramdisk, cmdline='', out=out)


def mk_vendor_boot(vendor_ramdisk=b'', dtb=b'', cmdline='', bootconfig=b'',
                   dtb_addr=0x01F00000, kernel_addr=0x00008000,
                   ramdisk_addr=0x01000000, tags_addr=0x00000100,
                   out='vendor_boot.img'):
    hdr = bytearray(2128)
    hdr[0:8] = b'VNDRBOOT'
    struct.pack_into('<I', hdr, 0x008, 4)
    struct.pack_into('<I', hdr, 0x00c, PAGE)
    struct.pack_into('<I', hdr, 0x010, kernel_addr)
    struct.pack_into('<I', hdr, 0x014, ramdisk_addr)
    struct.pack_into('<I', hdr, 0x018, len(vendor_ramdisk))
    cb = cmdline.encode()[:2047]
    hdr[0x01c:0x01c + len(cb)] = cb
    struct.pack_into('<I', hdr, 0x81c, tags_addr)
    struct.pack_into('<I', hdr, 0x830, 2128)
    struct.pack_into('<I', hdr, 0x834, len(dtb))
    struct.pack_into('<Q', hdr, 0x838, dtb_addr)
    struct.pack_into('<I', hdr, 0x848, 108)

    # Section order per AOSP bootimg.h v4, and *verified* against the factory
    # image byte-for-byte:   vendor_ramdisk | dtb | vendor_ramdisk_table | bootconfig
    # (the table comes AFTER the dtb -- getting this backwards makes ABL read the
    #  table bytes as if they were the DTB and hard-fail immediately)
    off_vr = align(2128)
    off_dtb = off_vr + align(len(vendor_ramdisk))
    off_tbl = off_dtb + align(len(dtb))
    off_bc = off_tbl + align(108)
    total = off_bc + align(len(bootconfig))

    # entry mirrors the factory one exactly:
    #   size = whole vendor_ramdisk, offset 0, type 1, empty name, board_id all 0
    entry = bytearray(108)
    struct.pack_into('<I', entry, 0x00, len(vendor_ramdisk))
    struct.pack_into('<I', entry, 0x04, 0)          # offset within vendor_ramdisk
    struct.pack_into('<I', entry, 0x08, 1)          # type 1 (same as factory)

    struct.pack_into('<I', hdr, 0x840, 108)
    struct.pack_into('<I', hdr, 0x844, 1)
    struct.pack_into('<I', hdr, 0x84c, len(bootconfig))

    buf = bytearray(total)
    buf[0:2128] = hdr
    buf[off_vr:off_vr + len(vendor_ramdisk)] = vendor_ramdisk
    buf[off_dtb:off_dtb + len(dtb)] = dtb
    buf[off_tbl:off_tbl + 108] = bytes(entry)
    if bootconfig:
        buf[off_bc:off_bc + len(bootconfig)] = bootconfig
    print(f'    vendor_ramdisk @0x{off_vr:x}  dtb @0x{off_dtb:x}  '
          f'table @0x{off_tbl:x}  bootconfig @0x{off_bc:x}')
    write(out, bytes(buf))
    return bytes(buf)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', required=True, choices=['boot', 'init_boot', 'vendor_boot'])
    ap.add_argument('--kernel', default='')
    ap.add_argument('--ramdisk', default='')
    ap.add_argument('--vendor-ramdisk', default='')
    ap.add_argument('--dtb', default='')
    ap.add_argument('--cmdline', default='')
    ap.add_argument('--bootconfig', default='')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    def rd(p):
        return open(p, 'rb').read() if p else b''

    if a.mode == 'boot':
        mk_boot(rd(a.kernel), rd(a.ramdisk), a.cmdline, out=a.out)
    elif a.mode == 'init_boot':
        mk_init_boot(rd(a.ramdisk), out=a.out)
    else:
        mk_vendor_boot(rd(a.vendor_ramdisk), rd(a.dtb), a.cmdline,
                       a.bootconfig.encode() if a.bootconfig else b'', out=a.out)
