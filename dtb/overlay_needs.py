#!/usr/bin/env python3
"""overlay_needs.py - what does a vendor dtbo overlay require from the base DTB?

For each selected entry it reports:
  * every symbol needed via __fixups__   (fragment used  target = <&symbol>)
  * every target-path string             (fragment used  target-path = "...")
  * whether __local_fixups__ is present

That determines whether a stub-DTB (dummy labelled nodes) can satisfy ABL.
"""
import struct, sys

FDT = struct.pack('>I', 0xd00dfeed)
T_BEGIN, T_END_NODE, T_PROP, T_NOP, T_END = 1, 2, 3, 4, 9


def walk(blob):
    """return (root_props, {child: {prop: value}}) for a 2-level FDT"""
    off_struct = struct.unpack_from('>I', blob, 8)[0]
    off_strings = struct.unpack_from('>I', blob, 12)[0]
    p = off_struct
    assert struct.unpack_from('>I', blob, p)[0] == T_BEGIN
    p += 4
    while blob[p] != 0:
        p += 1
    p = (p + 4) & ~3
    root = {}
    kids = {}
    depth = 1
    cur = None
    while p + 4 <= len(blob):
        t = struct.unpack_from('>I', blob, p)[0]; p += 4
        if t == T_BEGIN:
            e = blob.find(b'\0', p)
            nm = blob[p:e].decode('ascii', 'replace'); p = (e + 4) & ~3
            if depth == 1:
                cur = nm
                kids[nm] = {}
            depth += 1
        elif t == T_END_NODE:
            depth -= 1
            if depth == 0:
                break
        elif t == T_PROP:
            ln, no = struct.unpack_from('>II', blob, p); p += 8
            v = blob[p:p + ln]; p = (p + ln + 3) & ~3
            e = blob.find(b'\0', off_strings + no)
            name = blob[off_strings + no:e].decode('ascii', 'replace')
            if depth == 1:
                root[name] = v
            elif depth == 2 and cur:
                kids[cur][name] = v
        elif t == T_END:
            break
    return root, kids


def cstr(v):
    return v.split(b'\0')[0].decode('ascii', 'replace')


def analyse(blob, label):
    root, kids = walk(blob)
    fix = kids.get('__fixups__', {})
    loc = kids.get('__local_fixups__', {})
    print(f'\n===== {label}')
    print(f'  model={cstr(root.get("model", b"?"))}')
    print(f'  __fixups__ symbols: {len(fix)}')
    print(f'  __local_fixups__: {"yes" if loc else "no"}')

    sym = sorted(fix.keys())
    print(f'  symbols ({len(sym)}):')
    for i in range(0, len(sym), 6):
        print('     ' + '  '.join(f'{s:<28}' for s in sym[i:i + 6]))

    frags = [k for k in kids if k.startswith('fragment')]
    tpath = []
    tsym = 0
    tnone = 0
    for f in frags:
        d = kids[f]
        if 'target-path' in d:
            tpath.append(cstr(d['target-path']))
        elif 'target' in d:
            v = d['target']
            if v == b'\xff\xff\xff\xff':
                tsym += 1
            else:
                tnone += 1
        else:
            tnone += 1
    print(f'  fragments: {len(frags)}   by-symbol={tsym}  by-path={len(tpath)}  other={tnone}')
    if tpath:
        print('  target-path 列表（这些路径必须在基础 DTB 里真实存在）：')
        for s in sorted(set(tpath)):
            print(f'     {s}')
    return set(sym), set(tpath)


if __name__ == '__main__':
    src = r'D:\TB331FC_GSI_Kit\08_一键刷机\fw\dtbo.img'
    d = open(src, 'rb').read()
    magic, total, hdrsz, eoff, cnt, esz = struct.unpack_from('>6I', d, 0)
    allsym, allpath = set(), set()
    for n in (0, 2):
        b = eoff + n * esz
        sz, off = struct.unpack_from('>2I', d, b)
        s, t = analyse(d[off:off + sz], f'dtbo entry #{n}  ({sz} bytes)')
        allsym |= s
        allpath |= t
    print('\n' + '=' * 70)
    print(f'合计需要符号 {len(allsym)} 个，target-path {len(allpath)} 个')
    out = r'D:\TB331FCLinux\dump\overlay_needs.txt'
    with open(out, 'w', encoding='utf-8') as f:
        f.write('# symbols needed by dtbo entries 0 and 2\n')
        for s in sorted(allsym):
            f.write(s + '\n')
        f.write('\n# target-paths needed\n')
        for s in sorted(allpath):
            f.write(s + '\n')
    print(f'已写入 {out}')
