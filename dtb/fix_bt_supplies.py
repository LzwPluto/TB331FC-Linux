#!/usr/bin/env python3
"""fix_bt_supplies.py

hci_qca's qca_soc_data_wcn3990 declares four supplies:
    vddio, vddxo, vddrf, vddch0
The DTB only provides vddio and vddxo, so the BT part never gets its RF/PA rails
and the firmware handshake times out ("command 0xfc00 tx timeout").

Map the missing rails to the same regulators the WiFi node uses for the
equivalent functions:
    vddrf  -> vdd-1.3-rfa  (1.3 V RF)
    vddch0 -> vdd-3.3-ch0  (3.3 V PA/chain 0)
"""
import re
import sys

P = '/mnt/d/TB331FCLinux/build/CANONICAL.dts'
t = open(P, encoding='utf-8').read()

if 'vddrf-supply' in t and 'vddch0-supply' in t:
    print('BT supplies already present')
    sys.exit(0)

# find the wifi node rails for reference
i = t.find('wifi@c800000 {')
if i < 0:
    sys.exit('wifi node not found')
j = t.index('{', i); depth = 0; k = j
while k < len(t):
    if t[k] == '{':
        depth += 1
    elif t[k] == '}':
        depth -= 1
        if depth == 0:
            break
    k += 1
wifi = t[j + 1:k]

def phandle(prop):
    m = re.search(r'\b' + prop + r'-supply = <(0x[0-9a-f]+)>;', wifi)
    return m.group(1) if m else None

rf  = phandle('vdd-1.3-rfa')
ch0 = phandle('vdd-3.3-ch0')
print(f'wifi rails: vdd-1.3-rfa={rf} vdd-3.3-ch0={ch0}')
if not rf or not ch0:
    sys.exit('could not find wifi rails to copy')

# patch the bluetooth node
b = t.find('compatible = "qcom,wcn3990-bt";')
if b < 0:
    sys.exit('bluetooth node not found')
start = t.rfind('{', 0, b)
depth = 0; end = start
while end < len(t):
    if t[end] == '{':
        depth += 1
    elif t[end] == '}':
        depth -= 1
        if depth == 0:
            break
    end += 1
body = t[start + 1:end]

m = re.search(r'(\s*)(vddxo-supply = <0x[0-9a-f]+>;)', body)
if not m:
    sys.exit('vddxo-supply not found in bluetooth node')

add = m.group(1) + 'vddrf-supply = <' + rf + '>;' + \
      m.group(1) + 'vddch0-supply = <' + ch0 + '>;'
body = body.replace(m.group(0), m.group(0) + add, 1)
t = t[:start + 1] + body + t[end:]

open(P, 'w', encoding='utf-8', newline='\n').write(t)
print('added vddrf + vddch0 to the bluetooth node')
