#!/usr/bin/env python3
"""add_crc_reboot_fix.py

The Novatek controller can enter a CRC-failure reboot loop.  While it reboots,
every register read returns 0xFF/0xFC, the reported PID changes on every read,
the firmware download fails its DLM CRC and the IRQ never fires - exactly the
symptoms we see on the TB331FC.

The vendor driver (nova_36525_mmi/nt36xxx.c: nvt_stop_crc_reboot) detects this
by reading the CRC error area and clears the flag to break the loop.  The
mainline nt36523 driver has no such recovery.

Addresses for this part come from the vendor's own log on this tablet:
    chip_ver_trim_addr = 0x03F004
    swrst_sif_addr     = 0x03F0FE
    crc_err_flag_addr  = 0x03F135
"""
import os
import sys

P = os.path.expanduser(
    '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/input/touchscreen/nt36523_ts.c')
s = open(P, encoding='utf-8').read()

if 'nvt_stop_crc_reboot' in s:
    print('already patched')
    sys.exit(0)

FUNC = r'''
/*
 * TB331FC: the controller can get stuck in a CRC-failure reboot loop.  While it
 * reboots every register read returns 0xFF/0xFC, the PID changes on each read,
 * the firmware download fails and the IRQ never fires.  The vendor driver
 * clears the CRC error flag to break out of the loop; the mainline driver has no
 * such recovery.  Addresses come from the vendor map of this part:
 *   chip_ver_trim 0x03F004, swrst_sif 0x03F0FE, crc_err_flag 0x03F135
 */
#define NVT_CRC_ERR_FLAG_ADDR	0x03F135

static void nvt_stop_crc_reboot(void)
{
	uint8_t buf[8] = {0};
	int32_t retry;

	nvt_set_page(NVT_CRC_ERR_FLAG_ADDR);
	buf[0] = 0x4E;
	if (CTP_SPI_READ(ts->client, buf, 4)) {
		NVT_ERR("read crc flag area failed\n");
		return;
	}

	NVT_LOG("crc area buf = 0x%02X 0x%02X 0x%02X 0x%02X\n",
		buf[0], buf[1], buf[2], buf[3]);

	if (!((buf[1] == 0xFC && buf[2] == 0xFC && buf[3] == 0xFC) ||
	      (buf[1] == 0xFF && buf[2] == 0xFF && buf[3] == 0xFF))) {
		NVT_LOG("chip is not in a crc reboot loop\n");
		return;
	}

	NVT_ERR("chip is in a CRC-fail reboot loop, stopping it\n");

	for (retry = 5; retry > 0; retry--) {
		nvt_sw_reset_idle();
		nvt_sw_reset_idle();
		msleep(1);

		nvt_write_addr(NVT_CRC_ERR_FLAG_ADDR, 0xA5);

		nvt_set_page(NVT_CRC_ERR_FLAG_ADDR);
		buf[0] = NVT_CRC_ERR_FLAG_ADDR & 0x7F;
		if (CTP_SPI_READ(ts->client, buf, 2)) {
			NVT_ERR("read back crc flag failed\n");
			return;
		}
		if (buf[1] == 0xA5) {
			NVT_LOG("crc reboot loop stopped (retry %d)\n", retry);
			return;
		}
	}
	NVT_ERR("could not stop crc reboot loop, last=0x%02X\n", buf[1]);
}

'''

# insert the function right before nvt_ts_probe
anchor = 'static int32_t nvt_ts_probe(struct spi_device *client)'
if anchor not in s:
    sys.exit('probe anchor not found')
s = s.replace(anchor, FUNC + anchor, 1)

# call it at the very beginning of probe, before any chip access
old_probe = '''static int32_t nvt_ts_probe(struct spi_device *client)
{'''
new_probe = '''static int32_t nvt_ts_probe(struct spi_device *client)
{
	/* TB331FC: break a CRC-fail reboot loop before touching the chip */
	nvt_stop_crc_reboot();'''
if old_probe not in s:
    sys.exit('probe body anchor not found')
s = s.replace(old_probe, new_probe, 1)

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched: nvt_stop_crc_reboot() added and called at probe entry')
