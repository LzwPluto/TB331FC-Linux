#!/usr/bin/env python3
"""fix_bt_uart_pins.py

The DTB already contains a qup3 pin state (gpio8/gpio9, function "qup3",
phandle 0x56) but serial@4a8c000 never references it, so the Bluetooth UART pins
stay unmuxed and every HCI command times out ("command 0xfc00 tx timeout").

Wire that pin state into the node.
"""
import re
import sys

P = '/mnt/d/TB331FCLinux/build/CANONICAL.dts'
t = open(P, encoding='utf-8').read()

# locate serial@4a8c000 node
i = t.find('serial@4a8c000 {')
if i < 0:
    sys.exit('serial@4a8c000 not found')
j = t.index('{', i)
depth = 0; k = j
while k < len(t):
    if t[k] == '{':
        depth += 1
    elif t[k] == '}':
        depth -= 1
        if depth == 0:
            break
    k += 1
body = t[j + 1:k]

if 'pinctrl-0' in body:
    print('serial@4a8c000 already has pinctrl')
    sys.exit(0)

# find the qup3 pin state phandle (pins gpio8/gpio9, function qup3)
m = re.search(
    r'\{[^{}]*pins = "gpio8\\0gpio9";\s*\n\s*function = "qup3";[^{}]*phandle = <(0x[0-9a-f]+)>;',
    t, re.S)
if not m:
    sys.exit('qup3 pin state node not found')
ph = m.group(1)
print(f'qup3 pin state phandle = {ph}')

ins = f'\n\t\t\t\tpinctrl-names = "default";\n\t\t\t\tpinctrl-0 = <{ph}>;\n'
# insert right after the status property inside the node
sm = re.search(r'\n(\s*)status = "okay";', body)
if sm:
    body = body.replace(sm.group(0), ins + sm.group(0), 1)
else:
    body = ins + body

t = t[:j + 1] + body + t[k:]
open(P, 'w', encoding='utf-8', newline='\n').write(t)
print('wired the qup3 pin state into serial@4a8c000')
