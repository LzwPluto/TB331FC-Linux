#!/usr/bin/env python3
"""add_pps.py - send the standard DSC PPS to the panel before sleep-out.

The reference DSC panels (e.g. panel-raydium-rm692e5.c) pack the PPS from
drm_dsc_config and push it with mipi_dsi_picture_parameter_set(), then enable
DSI compression mode.  We never did that; the panel's decoder therefore ran
with whatever the vendor register writes left behind -> garbled output.

Order matters: PPS goes in after the register init but *before* 0x11 (sleep out)
and 0x29 (display on), so the replay is split at the sleep-in packet.
"""
import os
import re
import sys

P = os.path.expanduser(
    '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/gpu/drm/panel/panel-himax-hx83102.c')
s = open(P, encoding='utf-8').read()

if 'p255_inx_replay_range' in s:
    print('already patched')
    sys.exit(0)

start = s.index('static int p255_inx_replay(')
end = s.index('static const struct drm_display_mode lenovo_p255_inx_mode')

new_block = r'''/*
 * Replay part of the vendor command buffer.
 * *pos is updated to the offset we stopped at.  When stop_at_sleep_in is set we
 * stop right before the DCS 0x11 (sleep out) packet so the caller can insert the
 * DSC PPS, which must be programmed before the panel leaves sleep.
 */
static int p255_inx_replay_range(struct hx83102 *ctx, const u8 *buf, size_t n,
				 size_t *pos, bool stop_at_sleep_in)
{
	struct mipi_dsi_device *dsi = ctx->dsi;
	size_t i = *pos;

	while (i + 7 <= n) {
		u8 dtype = buf[i];
		u8 wait = buf[i + 4];
		u16 len = (buf[i + 5] << 8) | buf[i + 6];
		const u8 *p = &buf[i + 7];
		int ret = 0;

		if (i + 7 + len > n)
			break;

		if (stop_at_sleep_in && len >= 1 && p[0] == 0x11 &&
		    (dtype == 0x05 || dtype == 0x15)) {
			*pos = i;
			return 0;
		}

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

	*pos = i;
	return 0;
}

static int lenovo_p255_inx_init(struct hx83102 *ctx)
{
	struct drm_dsc_picture_parameter_set pps;
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi };
	size_t pos = 0;
	int ret;

	if (ctx->desc->has_dsc) {
		/* register init, stopping before sleep-out */
		ret = p255_inx_replay_range(ctx, p255_inx_on_seq,
					    sizeof(p255_inx_on_seq), &pos, true);
		if (ret)
			return ret;

		/* tell the panel decoder our compression parameters */
		drm_dsc_pps_payload_pack(&pps, &ctx->dsc);
		mipi_dsi_picture_parameter_set_multi(&dsi_ctx, &pps);
		mipi_dsi_compression_mode_ext_multi(&dsi_ctx, true,
						    MIPI_DSI_COMPRESSION_DSC, 0);
		if (dsi_ctx.accum_err) {
			dev_err(ctx->base.dev, "p255_inx: PPS/compression failed: %d\n",
				dsi_ctx.accum_err);
			return dsi_ctx.accum_err;
		}
	}

	/* sleep out + display on (+ anything after) */
	return p255_inx_replay_range(ctx, p255_inx_on_seq,
				     sizeof(p255_inx_on_seq), &pos, false);
}

'''

s = s[:start] + new_block + s[end:]

# re-enable DSC and keep our own init
s = s.replace('''	.has_dcs_backlight = true,
	.has_dsc = false,
	.init = lenovo_p255_inx_init,''',
              '''	.has_dcs_backlight = true,
	.has_dsc = true,
	.init = lenovo_p255_inx_init,''')

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched: split replay at sleep-in, send PPS + compression mode, DSC on')
