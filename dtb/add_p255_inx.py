#!/usr/bin/env python3
"""add_p255_inx.py - add a lenovo,p255-inx panel entry to panel-himax-hx83102.c

Uses a faithful replay of the vendor DSI command buffer instead of hand
translating 309 register writes.
"""
import os
import re
import shutil
import sys

DRV = os.path.expanduser(
    '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/gpu/drm/panel/panel-himax-hx83102.c')
HDR_SRC = r'/mnt/d/TB331FCLinux/build/p255_inx_init.h'
HDR_DST = os.path.join(os.path.dirname(DRV), 'p255_inx_init.h')

if not os.path.exists(DRV):
    sys.exit(f'driver not found: {DRV}')

shutil.copy(HDR_SRC, HDR_DST)
print(f'copied header -> {HDR_DST}')

src = open(DRV, encoding='utf-8').read()
if 'lenovo,p255-inx' in src:
    print('already patched, nothing to do')
    sys.exit(0)

# 1) include the generated arrays
anchor = '#include <video/mipi_display.h>'
if anchor not in src:
    sys.exit('include anchor not found')
src = src.replace(anchor, anchor + '\n\n#include "p255_inx_init.h"', 1)

# 2) insert the panel implementation before the of_match table
block = r'''
/*
 * Lenovo p255_inx -- INX glass, 1200x1920, 90 Hz, Himax HX83102 TDDI.
 *
 * The vendor device tree stores the init sequence as a raw Qualcomm DSI
 * command buffer:
 *     [dtype][last][vc][ack][wait_ms][len_hi][len_lo][payload ...]
 * with dtype 0x39 = generic long write, 0x15 = DCS write + 1 param,
 * 0x05 = DCS write without parameters.  Replaying it verbatim keeps all
 * 309 register writes intact instead of risking translation mistakes.
 */
static int p255_inx_replay(struct hx83102 *ctx, const u8 *buf, size_t n)
{
	struct mipi_dsi_device *dsi = ctx->dsi;
	size_t i = 0;

	while (i + 7 <= n) {
		u8 dtype = buf[i];
		u8 wait = buf[i + 4];
		u16 len = (buf[i + 5] << 8) | buf[i + 6];
		const u8 *p = &buf[i + 7];
		int ret = 0;

		if (i + 7 + len > n)
			break;

		switch (dtype) {
		case 0x39:
			ret = mipi_dsi_generic_write(dsi, p, len);
			break;
		case 0x15:
			ret = mipi_dsi_dcs_write(dsi, p[0],
						 len > 1 ? &p[1] : NULL, len - 1);
			break;
		case 0x05:
			ret = mipi_dsi_dcs_write(dsi, p[0], NULL, 0);
			break;
		default:
			break;
		}
		if (ret < 0) {
			dev_err(ctx->base.dev, "p255_inx cmd failed at %zu: %d\n", i, ret);
			return ret;
		}
		if (wait)
			msleep(wait);
		i += 7 + len;
	}
	return 0;
}

static int lenovo_p255_inx_init(struct hx83102 *ctx)
{
	/* the vendor tail already sends 0x11 (120 ms) and 0x29 */
	return p255_inx_replay(ctx, p255_inx_on_seq, sizeof(p255_inx_on_seq));
}

static const struct drm_display_mode lenovo_p255_inx_mode = {
	/* 1396 x 2226 x 90 Hz */
	.clock = 279675,
	.hdisplay = 1200,
	.hsync_start = 1296,
	.hsync_end = 1300,
	.htotal = 1396,
	.vdisplay = 1920,
	.vsync_start = 1976,
	.vsync_end = 1978,
	.vtotal = 2226,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static const struct hx83102_panel_desc lenovo_p255_inx_desc = {
	.modes = &lenovo_p255_inx_mode,
	.size = {
		.width_mm = 147,
		.height_mm = 235,
	},
	.has_dcs_backlight = true,
	.init = lenovo_p255_inx_init,
};

'''
anchor2 = 'static const struct of_device_id hx83102_of_match[] = {'
if anchor2 not in src:
    sys.exit('of_match anchor not found')
src = src.replace(anchor2, block + anchor2, 1)

# 3) add the compatible
entry = '''	{ .compatible = "lenovo,p255-inx",
	  .data = &lenovo_p255_inx_desc
	},
'''
sentinel = '\t{ /* sentinel */ }'
src = src.replace(sentinel, entry + sentinel, 1)

open(DRV, 'w', encoding='utf-8', newline='\n').write(src)
print('driver patched: lenovo,p255-inx added')
print('  - include + replay helper + init + mode + desc + of_match')
