#!/usr/bin/env python3
"""add_dsc.py - teach the hx83102 panel driver about DSC compression.

The p255_inx panel is a DSC panel (vendor DT: qcom,compression-mode = "dsc",
8 bpp, slice 600x20, slice-per-pkt 2).  Without host-side compression the panel
decodes garbage, which shows up as a rolling / torn image.
"""
import os
import sys

DRV = os.path.expanduser(
    '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/gpu/drm/panel/panel-himax-hx83102.c')
src = open(DRV, encoding='utf-8').read()

if 'dsc_version_major' in src:
    print('already has DSC support')
    sys.exit(0)

# 1) includes
anchor = '#include <video/mipi_display.h>'
src = src.replace(anchor, anchor + '''
#include <drm/display/drm_dsc.h>
#include <drm/display/drm_dsc_helper.h>''', 1)

# 2) struct member
anchor = '''	struct backlight_device *backlight;
};'''
src = src.replace(anchor, '''	struct backlight_device *backlight;
	struct drm_dsc_config dsc;
};''', 1)

# 3) desc flag
anchor = '''	bool has_dcs_backlight;
'''
src = src.replace(anchor, '''	bool has_dcs_backlight;
	bool has_dsc;
''', 1)

# 4) enable in probe
anchor = '''	ret = hx83102_panel_add(ctx);
	if (ret < 0)
		return ret;
'''
src = src.replace(anchor, '''	ret = hx83102_panel_add(ctx);
	if (ret < 0)
		return ret;

	if (desc->has_dsc) {
		/*
		 * Vendor DT: qcom,compression-mode = "dsc", 8 bits per pixel,
		 * 8 bits per component, slice 600x20, slice-per-pkt 2, DSC 1.1.
		 */
		ctx->dsc.dsc_version_major = 1;
		ctx->dsc.dsc_version_minor = 1;
		ctx->dsc.bits_per_component = 8;
		ctx->dsc.bits_per_pixel = 8 << 4;
		ctx->dsc.line_buf_depth = 9;
		ctx->dsc.convert_rgb = true;
		ctx->dsc.slice_width = 600;
		ctx->dsc.slice_height = 20;
		ctx->dsc.slice_count = 2;
		ctx->dsc.block_pred_enable = false;
		dsi->dsc = &ctx->dsc;
		dev_info(&dsi->dev, "DSC enabled: %ux%u slices, %u bpp\\n",
			 ctx->dsc.slice_width, ctx->dsc.slice_height,
			 ctx->dsc.bits_per_pixel >> 4);
	}
''', 1)

# 5) set the flag on our panel
src = src.replace('''	.has_dcs_backlight = true,
	.init = lenovo_p255_inx_init,''',
                  '''	.has_dcs_backlight = true,
	.has_dsc = true,
	.init = lenovo_p255_inx_init,''', 1)

open(DRV, 'w', encoding='utf-8', newline='\n').write(src)
print('DSC support added')
