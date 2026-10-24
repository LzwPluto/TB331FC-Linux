#!/usr/bin/env python3
"""slice_per_pkt_2_correct.py

The vendor panel wants 2 DSC slices per DSI packet with slice_count = 2 slices
per line, i.e. exactly ONE packet per line.

The previous attempt wrongly set pkt_per_line = slice_per_intf * 2 (= 4), which
told the DSI to send 4 packets per line and broke the stream completely.
pkt_per_line is log2-encoded (>>1), so 1 packet/line is the right value here.
"""
import os
import sys

P = os.path.expanduser(
    '~/kbuild/linux-next-tb128fu-hx83102-panel-port/drivers/gpu/drm/msm/dsi/dsi_host.c')
s = open(P, encoding='utf-8').read()

if 'p255_inx spp2 (corrected)' in s:
    print('already patched')
    sys.exit(0)

a = 'bytes_per_pkt = dsc->slice_chunk_size;'
if a not in s:
    sys.exit('bytes_per_pkt anchor not found')
s = s.replace(a, '/* p255_inx spp2 (corrected): 2 slices per packet */\n'
                 '\tbytes_per_pkt = dsc->slice_chunk_size * 2;', 1)

b = '\tpkt_per_line = slice_per_intf;'
if b not in s:
    sys.exit('pkt_per_line anchor not found')
s = s.replace(b, '\t/* p255_inx spp2 (corrected): slice_per_pkt = 2 -> 1 pkt/line */\n'
                 '\tpkt_per_line = slice_per_intf / 2;', 1)

c = 'wc = msm_host->dsc->slice_chunk_size + 1;'
if c in s:
    s = s.replace(c, 'wc = msm_host->dsc->slice_chunk_size * 2 + 1;', 1)

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('patched: bytes_per_pkt = chunk*2, pkt_per_line = slice_per_intf/2 (=1)')
