#!/usr/bin/env python3
"""enable_novatek.py - switch the touch from Himax (wrong chip) to Novatek.

Android reports: NVT-ts, NT36523, SPI, mode 0, 10 MHz, firmware novatek_ts_fw.bin.
Our DTB already carries a fully configured reset novatek,nt36523-spi node as
touchscreen@1 -- it is simply disabled. Enable it, point the firmware name at the
file we pulled from /vendor/firmware, and disable the Himax node on CS0.
"""
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
t = open(src, encoding='utf-8').read()

# 1) enable touchscreen@1
i = t.find('\t\t\t\ttouchscreen@1 {')
if i < 0:
    sys.exit('touchscreen@1 not found')
j = t.index('{', i)
depth = 0
k = j
while k < len(t):
    if t[k] == '{':
        depth += 1
    elif t[k] == '}':
        depth -= 1
        if depth == 0:
            break
    k += 1
body = t[j + 1:k]
body = body.replace('status = "disabled";', 'status = "okay";')
body = body.replace('firmware-name = "qcom/sm6225/LENOVO/TB128FU/nt36523.bin";',
                    'firmware-name = "novatek_ts_fw.bin";')
if 'status = "okay"' not in body:
    body = '\n\t\t\t\t\tstatus = "okay";' + body
t = t[:j + 1] + body + t[k:]
print('touchscreen@1 -> okay, firmware-name -> novatek_ts_fw.bin')

# 2) disable touchscreen@0 (Himax on CS0; wrong chip, it only spams errors)
i = t.find('\t\t\t\ttouchscreen@0 {')
if i >= 0:
    j = t.index('{', i)
    depth = 0
    k = j
    while k < len(t):
        if t[k] == '{':
            depth += 1
        elif t[k] == '}':
            depth -= 1
            if depth == 0:
                break
        k += 1
    body = t[j + 1:k]
    if 'status =' in body:
        body = re.sub(r'status = "[^"]*";', 'status = "disabled";', body, count=1)
    else:
        body = '\n\t\t\t\t\tstatus = "disabled";' + body
    t = t[:j + 1] + body + t[k:]
    print('touchscreen@0 -> disabled')
else:
    print('touchscreen@0 not found (ok)')

open(dst, 'w', encoding='utf-8', newline='\n').write(t)
print(f'wrote {dst}')
