#!/usr/bin/env python3
"""del_prop.py <in.dts> <out.dts> <node-header> <prop> [prop...]

Delete one or more properties from a specific node, so we can drop optional
dependencies (e.g. dmas/dma-names) that are blocking a driver probe.
"""
import re, sys

src, dst, header = sys.argv[1], sys.argv[2], sys.argv[3]
props = sys.argv[4:]

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
for p in props:
    pat = re.compile(r'^[ \t]*' + re.escape(p) + r' = <[^;]*>;\n', re.M)
    pat2 = re.compile(r'^[ \t]*' + re.escape(p) + r' = "[^"]*";\n', re.M)
    n1 = len(pat.findall(body))
    n2 = len(pat2.findall(body))
    body = pat.sub('', body)
    body = pat2.sub('', body)
    print(f'  {p}: removed {n1 + n2}')

t = t[:j + 1] + body + t[k:]
open(dst, 'w', encoding='utf-8', newline='\n').write(t)
print(f'wrote {dst}')
