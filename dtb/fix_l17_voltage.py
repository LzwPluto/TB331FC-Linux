#!/usr/bin/env python3
"""fix_l17_voltage.py

The WCN3990 BT core rail (pm6125_l17) must be exactly 1.304 V - that is what the
vendor DT specifies (qca,bt-vdd-core-voltage-level = <0x13e5c0 0x13e5c0>) and what
Android actually programs.

Our regulators-0 entry allows 1220000..1304000, so the regulator framework picks
the *minimum* (1.22 V), which is below what the BT core needs - a very plausible
reason the chip never answers on the UART.

Pin the range to exactly 1304000 uV.
"""
import re
import sys

P = '/mnt/d/TB331FCLinux/build/CANONICAL.dts'
t = open(P, encoding='utf-8').read()

# locate the l17 node inside regulators-0
start = t.find('regulators-0 {')
if start < 0:
    sys.exit('regulators-0 not found')
brace = t.index('{', start)
depth = 0; k = brace
while k < len(t):
    if t[k] == '{':
        depth += 1
    elif t[k] == '}':
        depth -= 1
        if depth == 0:
            break
    k += 1
block = t[brace + 1:k]

m = re.search(r'(l17 \{)(.*?)(\n\t+\};)', block, re.S)
if not m:
    sys.exit('l17 node not found')
body = m.group(2)
orig = body
body = re.sub(r'regulator-min-microvolt = <0x[0-9a-f]+>;',
              'regulator-min-microvolt = <0x13e5c0>;', body)
body = re.sub(r'regulator-max-microvolt = <0x[0-9a-f]+>;',
              'regulator-max-microvolt = <0x13e5c0>;', body)
if body == orig:
    print('l17 already pinned')
    sys.exit(0)

block = block[:m.start(2)] + body + block[m.end(2):]
t = t[:brace + 1] + block + t[k:]
open(P, 'w', encoding='utf-8', newline='\n').write(t)

print('l17 pinned to 1304000 uV (0x13e5c0), matching the vendor/Android value')
for line in body.strip().split('\n'):
    if 'microvolt' in line:
        print('   ' + line.strip())
