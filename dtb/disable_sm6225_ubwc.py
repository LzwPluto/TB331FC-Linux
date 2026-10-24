#!/usr/bin/env python3
"""disable_sm6225_ubwc.py

The DPU advertises UBWC support through msm_mdss_data, and compositors (niri)
then allocate DRM_FORMAT_MOD_QCOM_COMPRESSED framebuffers.  The mainline UBWC
parameters for sm6225 (inherited from sm6115_data: enc 1.0 / dec 2.0,
swizzle 7) do not match this part, so scanout of compressed buffers decodes to
a blue/green grid.  Linear framebuffers work perfectly (the fbcon framebuffer
uses modifier 0x0).

Give sm6225 its own mdss data with UBWC disabled: the DPU then only accepts
linear modifiers and every compositor falls back to linear allocation.
Bandwidth check: 1200x1920x4B x 60Hz = 553 MB/s, fine for LPDDR4X.
"""
import sys

P = '/root/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/gpu/drm/msm/msm_mdss.c'
import os
if not os.path.exists(P):
    P = os.path.expanduser(
        '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/gpu/drm/msm/msm_mdss.c')

s = open(P, encoding='utf-8').read()

if 'sm6225_data' in s:
    print('already patched')
    sys.exit(0)

ANCHOR = 'static const struct msm_mdss_data sm6125_data = {'
NEW = '''/*
 * sm6225 (TB331FC): UBWC intentionally disabled.  The inherited sm6115 UBWC
 * parameters (enc 1.0 / dec 2.0, swizzle 7) do not match this part and scanout
 * of DRM_FORMAT_MOD_QCOM_COMPRESSED buffers decodes to a blue/green grid.
 * Linear buffers work correctly and 1200x1920@60 only needs ~553 MB/s.
 */
static const struct msm_mdss_data sm6225_data = {
	.highest_bank_bit = 0x1,
	.reg_bus_bw = 76800,
};

'''
if ANCHOR not in s:
    sys.exit('anchor not found')

s = s.replace(ANCHOR, NEW + ANCHOR, 1)
s = s.replace('{ .compatible = "qcom,sm6225-mdss", .data = &sm6115_data },',
              '{ .compatible = "qcom,sm6225-mdss", .data = &sm6225_data },')
if '&sm6225_data' not in s:
    sys.exit('failed to remap sm6225-mdss')

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched: sm6225 gets its own mdss data with UBWC disabled')
