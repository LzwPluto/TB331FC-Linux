#!/usr/bin/env python3
"""add_spi_selftest.py

Without a logic analyser, the next best thing is to characterise the SPI reads
from inside the kernel: read the same register (project ID) 20 times in a row
and print every value.

  * 20 different values in a single boot  -> the SPI transfer itself is
    unreliable (mode / CS / clock / wiring / dummy-byte count), because the
    register cannot change that fast.
  * 20 identical values (but a different one after each boot) -> SPI is fine and
    the chip state is what changes (it is rebooting or the area is volatile).
"""
import os
import sys

P = os.path.expanduser(
    '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/input/touchscreen/nt36523_ts.c')
s = open(P, encoding='utf-8').read()

if 'nvt_spi_selftest' in s:
    print('already patched')
    sys.exit(0)

FUNC = r'''
/*
 * TB331FC SPI read consistency self test: sample the project-ID register
 * N times in a row.  A real register does not change at this rate, so
 * differing values mean the SPI transfer itself is unreliable.
 */
#define NVT_SELFTEST_READS	20
static void nvt_spi_selftest(void)
{
	uint8_t buf[4];
	uint16_t val[NVT_SELFTEST_READS];
	int32_t distinct = 0;
	int32_t i, j;

	for (i = 0; i < NVT_SELFTEST_READS; i++) {
		memset(buf, 0, sizeof(buf));
		nvt_set_page(ts->mmap->EVENT_BUF_ADDR | EVENT_MAP_PROJECTID);
		buf[0] = EVENT_MAP_PROJECTID;
		buf[1] = 0x00;
		buf[2] = 0x00;
		if (CTP_SPI_READ(ts->client, buf, 3)) {
			NVT_ERR("selftest read %d failed\n", i);
			return;
		}
		val[i] = (buf[2] << 8) + buf[1];
	}

	for (i = 0; i < NVT_SELFTEST_READS; i++) {
		int dup = 0;
		for (j = 0; j < i; j++)
			if (val[j] == val[i])
				dup = 1;
		if (!dup)
			distinct++;
	}

	NVT_ERR("selftest: %d reads, %d distinct values\n",
		NVT_SELFTEST_READS, (int)distinct);
	for (i = 0; i < NVT_SELFTEST_READS; i += 10) {
		NVT_ERR("selftest[%02d..%02d]: %04X %04X %04X %04X %04X %04X %04X %04X %04X %04X\n",
			i, i + 9, val[i+0], val[i+1], val[i+2], val[i+3], val[i+4],
			val[i+5], val[i+6], val[i+7], val[i+8], val[i+9]);
	}

	nvt_set_page(ts->mmap->EVENT_BUF_ADDR);
}

'''

anchor = 'static int32_t nvt_ts_probe(struct spi_device *client)'
if anchor not in s:
    sys.exit('probe anchor not found')
s = s.replace(anchor, FUNC + anchor, 1)

call_anchor = '\tnvt_stop_crc_reboot();\n'
if call_anchor not in s:
    sys.exit('crc call anchor not found')
s = s.replace(call_anchor,
              call_anchor + '\tnvt_spi_selftest();\n', 1)

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched: nvt_spi_selftest() added, called after the CRC check')
