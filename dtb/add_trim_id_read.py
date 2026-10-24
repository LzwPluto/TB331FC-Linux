#!/usr/bin/env python3
"""add_trim_id_read.py

The tree's nvt_ts_check_chip_ver_trim() is a stub: it never reads the chip ID and
always assigns NT36523_memory_map.  Read the 6 trim-ID bytes at the address the
DT passes (0x03F004 on this part, the same value the vendor driver ends up
using) and log them, then keep the existing hardcoded map.

Read sequence follows the vendor driver (nt36xxx.c):
    nvt_bootloader_reset();
    for retry:
        nvt_sw_reset_idle();
        set_page(chip_ver_trim_addr);
        read 7 bytes starting at (addr & 0x7F)   -> ID in bytes 1..6
"""
import os
import sys

P = os.path.expanduser(
    '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/input/touchscreen/nt36523_ts.c')
s = open(P, encoding='utf-8').read()

if 'nvt_trim_id_dumped' in s:
    print('already patched')
    sys.exit(0)

OLD = '''	ts->mmap = &NT36523_memory_map;
	ts->carrier_system = NT36523_hw_info.carrier_system;
	ts->hw_crc = NT36523_hw_info.hw_crc;
	return 0;
}'''

NEW = '''	uint8_t buf[8] = {0};
	int32_t retry;

	/* TB331FC: read the real trim ID so we can tell whether this part really
	 * matches the NT36523 memory map that is hardcoded below. */
	nvt_bootloader_reset();
	for (retry = 5; retry > 0; retry--) {
		nvt_sw_reset_idle();

		if (nvt_set_page(chip_ver_trim_addr))
			continue;

		memset(buf, 0, sizeof(buf));
		buf[0] = chip_ver_trim_addr & 0x7F;
		if (CTP_SPI_READ(ts->client, buf, 7))
			continue;

		NVT_ERR("nvt_trim_id_dumped(0x%06X): %02X %02X %02X %02X %02X %02X\\n",
			chip_ver_trim_addr, buf[1], buf[2], buf[3], buf[4], buf[5], buf[6]);

		if (!(buf[1] == 0xFF && buf[2] == 0xFF && buf[3] == 0xFF))
			break;
		msleep(10);
	}

	ts->mmap = &NT36523_memory_map;
	ts->carrier_system = NT36523_hw_info.carrier_system;
	ts->hw_crc = NT36523_hw_info.hw_crc;
	return 0;
}'''

if OLD not in s:
    sys.exit('stub body not found')
s = s.replace(OLD, NEW, 1)
open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched: trim ID is now read and logged')
