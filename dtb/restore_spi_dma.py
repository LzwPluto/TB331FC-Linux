#!/usr/bin/env python3
"""restore_spi_dma.py - put the DMA properties back on spi@4a80000.

They were removed early on to stop the SPI controller deferring while the GPI
DMA driver was still deferred.  That worked for small transfers, but the
Novatek firmware download writes a large DLM block and fails the read-back CRC
without DMA ("dlm: bin crc == golden, result differs").
"""
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
t = open(src, encoding='utf-8').read()

i = t.find('spi@4a80000 {')
if i < 0:
    sys.exit('spi@4a80000 not found')

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

if 'dmas =' in body:
    print('dmas already present, nothing to do')
    open(dst, 'w', encoding='utf-8', newline='\n').write(t)
    sys.exit(0)

# insert right after the interrupts line
m = re.search(r'^(\s*)interrupts = <[^;]*>;\n', body, re.M)
if not m:
    sys.exit('interrupts anchor not found')
indent = m.group(1)
ins = (f'{indent}dmas = <0x46 0x00 0x00 0x01 0x46 0x01 0x00 0x01>;\n'
       f'{indent}dma-names = "tx", "rx";\n')
body = body[:m.end()] + ins + body[m.end():]

t = t[:j + 1] + body + t[k:]
open(dst, 'w', encoding='utf-8', newline='\n').write(t)
print('restored dmas/dma-names on spi@4a80000')
