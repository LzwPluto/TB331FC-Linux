#!/usr/bin/env python3
"""fix_aliases_path.py

The aliases in the DTB point at /soc@0/... but the real node lives under
/soc/... (the decompiled vendor DTB kept the old unit-address name).  So
of_alias_get_id() cannot resolve them and qcom_geni_serial reports
"Invalid line -19" for the Bluetooth UART.

Rewrite the alias paths to the real ones.
"""
import re
import sys

P = '/mnt/d/TB331FCLinux/build/CANONICAL.dts'
t = open(P, encoding='utf-8').read()

if '/soc@0/' not in t:
    print('aliases already use /soc/ - nothing to do')
    sys.exit(0)

n = t.count('/soc@0/')
t = t.replace('/soc@0/', '/soc/')
open(P, 'w', encoding='utf-8', newline='\n').write(t)

print(f'fixed {n} alias path(s): /soc@0/ -> /soc/')
for m in re.finditer(r'\n(\s*(?:mmc0|serial0|serial1) = "[^"]+";)', t):
    print('  ' + m.group(1).strip())
