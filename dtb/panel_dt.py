#!/usr/bin/env python3
"""panel_dt.py - enable mdss/dispcc and point the panel at lenovo,p255-inx."""
import re
import sys

src = sys.argv[1]
dst = sys.argv[2]
t = open(src, encoding='utf-8').read()


def set_status_okay(text, header):
    b = text.find(header)
    if b < 0:
        print(f'  !! node not found: {header}')
        return text
    j = text.index('{', b)
    # only look at the immediate body of this node
    depth = 0
    k = j
    while k < len(text):
        if text[k] == '{':
            depth += 1
        elif text[k] == '}':
            depth -= 1
            if depth == 0:
                break
        k += 1
    body = text[j + 1:k]
    m = re.search(r'status = "[^"]*";', body)
    if not m:
        body = '\n\t\t\tstatus = "okay";' + body
        print(f'  {header}: inserted status=okay')
    else:
        body = body[:m.start()] + 'status = "okay";' + body[m.end():]
        print(f'  {header}: status -> okay')
    return text[:j + 1] + body + text[k:]


t = set_status_okay(t, 'display-subsystem@5e00000 {')
t = set_status_okay(t, 'clock-controller@5f00000 {')

n = t.count('compatible = "boe,hx83102p-2k";')
print(f'  panel compatible occurrences: {n}')
if n == 1:
    t = t.replace('compatible = "boe,hx83102p-2k";',
                  'compatible = "lenovo,p255-inx";')
    print('  panel compatible -> lenovo,p255-inx')
else:
    print('  !! unexpected count, not changing compatible')

open(dst, 'w', encoding='utf-8', newline='\n').write(t)
print(f'wrote {dst}')
