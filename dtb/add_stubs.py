#!/usr/bin/env python3
"""add_stubs.py - add a labelled stub subtree so dtc -@ emits a __symbols__ table
that satisfies the vendor dtbo overlays.

Each required symbol gets its own empty node with an explicit, high phandle so
nothing collides with the phandles frozen into the decompiled mainline DTS.
"""
import re, sys

dts = sys.argv[1]
syms_file = sys.argv[2]
out = sys.argv[3]

txt = open(dts, encoding='utf-8').read()

# 1) highest phandle already used
used = [int(x, 16) for x in re.findall(r'phandle = <0x([0-9a-fA-F]+)>', txt)]
base = (max(used) + 0x100) if used else 0x100
print(f'existing phandles: {len(used)}, max=0x{max(used) if used else 0:x}, stub base=0x{base:x}')

# 2) required symbols
syms = []
for line in open(syms_file, encoding='utf-8'):
    s = line.strip()
    if not s or s.startswith('#'):
        continue
    syms.append(s)
# de-dup, keep order
seen = set()
syms = [s for s in syms if not (s in seen or seen.add(s))]
print(f'symbols to stub: {len(syms)}')

# 3) build the stub subtree
lines = ['\tabl-stubs {', '\t\tcompatible = "abl-stubs";', '']
for i, s in enumerate(syms):
    ph = base + i
    # dtc label syntax:  label: node-name { };
    lines.append(f'\t\t{s}: {s} {{')
    lines.append(f'\t\t\tphandle = <0x{ph:x}>;')
    lines.append('\t\t};')
lines.append('\t};')
block = '\n'.join(lines) + '\n'

# 4) insert just before the final root closing brace
i = txt.rstrip().rfind('};')
assert i > 0, 'cannot find root closing brace'
head = txt[:i]
tail = txt[i:]
new = head + block + tail

open(out, 'w', encoding='utf-8', newline='\n').write(new)
print(f'wrote {out}  ({len(txt)} -> {len(new)} chars)')
print(f'stub phandle range: 0x{base:x} .. 0x{base+len(syms)-1:x}')
