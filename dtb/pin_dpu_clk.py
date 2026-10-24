#!/usr/bin/env python3
"""pin_dpu_clk.py

Measured behaviour:
  * right after boot dpu_kms_init() picks the highest OPP -> disp_cc_mdss_mdp_clk
    = 384 MHz and niri's first frames (the shortcut overlay) were displayed
    correctly;
  * as soon as dpu_core_perf_crtc_update() tries to drop to a lower OPP it fails
    ("failed to set core clock rate 192000000", -22) and the clock ends up at
    19.2 MHz, which cannot sustain full-frame updates -> garbled output.

So pin the DPU OPP table to the single rate we know works (384 MHz).  With one
entry, find_freq_ceil()/find_freq_floor() can only return 384 MHz and
dev_pm_opp_set_rate() keeps the MDP clock where the hardware is happy.
"""
import re
import sys

SRC = '/mnt/d/TB331FCLinux/build/ref_mdpclk.dts'
DST = '/mnt/d/TB331FCLinux/build/ref_pinned.dts'

t = open(SRC, encoding='utf-8').read()

start = t.find('phandle = <0x72>;')
if start < 0:
    sys.exit('dpu opp-table not found')
end = t.find('\n\t\t\t\t};', start)
if end < 0:
    sys.exit('opp-table end not found')

block = t[start:end]

# keep only the 384 MHz entry (0x16e36000)
m = re.search(r'(\n\t+opp-384000000 \{\n\t+opp-hz = <0x00 0x16e36000>;\n'
              r'\t+required-opps = <0x[0-9a-f]+>;\n\t+\};)', block)
if not m:
    sys.exit('384 MHz entry not found')

keep = m.group(1)
new_block = 'phandle = <0x72>;' + keep + '\n'
t = t[:start] + new_block + t[end:]
open(DST, 'w', encoding='utf-8', newline='\n').write(t)

print('pinned DPU OPP table to:')
for mm in re.finditer(r'opp-(\d+) \{', new_block):
    print(f'  {mm.group(1)} Hz')
