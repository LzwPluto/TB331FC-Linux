#!/usr/bin/env python3
"""use_bt_uart_4pin_state.py

The BT serial node was wired to qup-i2c3-default-state (phandle 0x56), which only
muxes gpio8/gpio9.  The four-pin qup3 state is qup-spi3-default-state
(phandle 0x57) covering gpio8..gpio11 - the same four pins the GENI UART needs
for TX/RX/CTS/RTS.  Switch to it.
"""
import sys

P = '/mnt/d/TB331FCLinux/build/CANONICAL.dts'
t = open(P, encoding='utf-8').read()

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

if 'pinctrl-0 = <0x57>;' in body:
    print('already using the 4-pin state')
    sys.exit(0)

if 'pinctrl-0 = <0x56>;' not in body:
    sys.exit('pinctrl-0 = <0x56> not found in the BT serial node')

body = body.replace('pinctrl-0 = <0x56>;', 'pinctrl-0 = <0x57>;', 1)
t = t[:j + 1] + body + t[k:]
open(P, 'w', encoding='utf-8', newline='\n').write(t)
print('BT UART now uses the 4-pin qup3 state (0x57)')
