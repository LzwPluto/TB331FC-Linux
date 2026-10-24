#!/usr/bin/env python3
"""fix_dpu_opp.py

The display-controller OPP table (phandle 0x72) in the vendor-derived DTB lists
200/300/383/470/560 MHz, but dispcc's ftbl_disp_cc_mdss_mdp_clk_src only offers
19.2/192/256/307.2/384 MHz.  dev_pm_opp_set_rate() therefore fails with -EINVAL
("failed to set core clock rate 200000000") and the DPU core clock stays at the
19.2 MHz minimum, which cannot sustain 1200x1920@60 full-frame updates.  That is
why static fbcon text looks fine while a compositor redrawing every frame
produces garbage.

Rewrite the OPP frequencies to the rates dispcc actually supports, keeping the
existing required-opps links.
"""
import re
import sys

SRC = '/mnt/d/TB331FCLinux/build/ref_nvt3.dts'
DST = '/mnt/d/TB331FCLinux/build/ref_mdpclk.dts'

# old opp-hz (hex) -> new opp-hz (hex)
FREQ_MAP = {
    '0xbebc200':  '0xb700000',   # 200000000   -> 192000000
    '0x11e1a300': '0xf424000',   # 300000000   -> 256000000
    '0x16d41dc0': '0x12500000',  # 383000000   -> 307200000
    '0x1c03a180': '0x16e36000',  # 470000000   -> 384000000
}

t = open(SRC, encoding='utf-8').read()

# locate the DPU opp-table (phandle 0x72)
start = t.find('phandle = <0x72>;')
if start < 0:
    sys.exit('dpu opp-table phandle 0x72 not found')
# the block ends at the first "\n\t\t\t\t};" after start
end = t.find('\n\t\t\t\t};', start)
if end < 0:
    sys.exit('opp-table end not found')
block = t[start:end]

before = block

# drop the 560 MHz entry (beyond what dispcc can produce)
block = re.sub(
    r'\n\t+opp-560000000 \{\n\t+opp-hz = <0x00 0x2160ec00>;\n'
    r'\t+required-opps = <0x6e>;\n\t+\};\n', '\n', block)

for old, new in FREQ_MAP.items():
    block = block.replace(f'opp-hz = <0x00 {old}>', f'opp-hz = <0x00 {new}>')

# rename the nodes so the DTS stays readable
renames = {
    'opp-200000000': 'opp-192000000',
    'opp-300000000': 'opp-256000000',
    'opp-383000000': 'opp-307200000',
    'opp-470000000': 'opp-384000000',
}
for old, new in renames.items():
    block = block.replace(f'{old} {{', f'{new} {{')

if block == before:
    sys.exit('nothing changed')

t = t[:start] + block + t[end:]
open(DST, 'w', encoding='utf-8', newline='\n').write(t)

print('new OPP entries:')
for m in re.finditer(r'opp-(\d+) \{\s*\n\s*opp-hz = <0x00 (0x[0-9a-f]+)>', block):
    print(f'  {m.group(1):>10} Hz  ({int(m.group(2), 16)} Hz)')
print(f'wrote {DST}')
