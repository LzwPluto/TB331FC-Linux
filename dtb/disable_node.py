#!/usr/bin/env python3
"""disable_node.py <dts-in> <dts-out> <node-header-substring>

Sets status = "disabled" inside the given node so the mainline driver for it
won't bind (e.g. mdss, which otherwise steals the framebuffer from simpledrm).
"""
import re, sys

src, dst, header = sys.argv[1], sys.argv[2], sys.argv[3]
t = open(src, encoding='utf-8').read()

b = t.find(header)
if b < 0:
    print(f'!! node not found: {header}')
    sys.exit(1)

j = t.index('{', b)
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
if re.search(r'status\s*=', body):
    body2 = re.sub(r'status\s*=\s*"[^"]*";', 'status = "disabled";', body, count=1)
    print('[ok] replaced existing status')
else:
    body2 = '\n\t\t\tstatus = "disabled";' + body
    print('[ok] inserted status = "disabled"')

t = t[:j + 1] + body2 + t[k:]
open(dst, 'w', encoding='utf-8', newline='\n').write(t)
print(f'wrote {dst}')
