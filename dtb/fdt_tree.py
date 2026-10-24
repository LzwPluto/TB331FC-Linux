#!/usr/bin/env python3
"""Correct depth-aware FDT root-node lister (for comparing accepted vs rejected DTs)."""
import struct, sys

FDT = struct.pack('>I', 0xd00dfeed)
T_BEGIN, T_END_NODE, T_PROP, T_NOP, T_END = 1, 2, 3, 4, 9


def parse(blob):
    if len(blob) < 40 or blob[:4] != FDT:
        return None
    total = struct.unpack_from('>I', blob, 4)[0]
    off_struct = struct.unpack_from('>I', blob, 8)[0]
    off_strings = struct.unpack_from('>I', blob, 12)[0]
    ver = struct.unpack_from('>I', blob, 20)[0]
    p = off_struct
    tag = struct.unpack_from('>I', blob, p)[0]
    assert tag == T_BEGIN, 'no root BEGIN_NODE'
    p += 4
    while blob[p] != 0:
        p += 1
    p = (p + 4) & ~3

    root_props = {}
    children = []
    child_prop_counts = {}
    depth = 1
    cur = None
    while p + 4 <= len(blob):
        tag = struct.unpack_from('>I', blob, p)[0]
        p += 4
        if tag == T_BEGIN:
            e = blob.find(b'\0', p)
            name = blob[p:e].decode('ascii', 'replace')
            p = (e + 4) & ~3
            if depth == 1:
                children.append(name)
                cur = name
                child_prop_counts[name] = 0
            depth += 1
        elif tag == T_END_NODE:
            depth -= 1
            if depth == 0:
                break
        elif tag == T_PROP:
            ln, no = struct.unpack_from('>II', blob, p); p += 8
            v = blob[p:p + ln]
            p = (p + ln + 3) & ~3
            e = blob.find(b'\0', off_strings + no)
            name = blob[off_strings + no:e].decode('ascii', 'replace')
            if depth == 1:
                root_props[name] = v
            elif depth == 2 and cur:
                child_prop_counts[cur] += 1
        elif tag == T_NOP:
            continue
        elif tag == T_END:
            break
    return dict(total=total, ver=ver, props=root_props, children=children,
                counts=child_prop_counts)


def show(label, blob):
    r = parse(blob)
    if not r:
        print(f'===== {label}: NOT a valid FDT')
        return
    print(f'===== {label}   totalsize={r["total"]}  ver={r["ver"]}')
    for k in ('model', 'compatible', 'qcom,msm-id', 'qcom,board-id', 'qcom,pmic-id'):
        if k in r['props']:
            v = r['props'][k]
            if k in ('model', 'compatible'):
                print(f'   {k:<14} {v.split(bytes([0]))[0].decode("ascii","replace")}')
            elif len(v) % 4 == 0:
                print(f'   {k:<14} {[hex(x) for x in struct.unpack(">%dI" % (len(v)//4), v)]}')
    print(f'   root children ({len(r["children"])}):')
    for c in r['children']:
        print(f'      {c:<40} ({r["counts"].get(c,0)} props)')


if __name__ == '__main__':
    fw = open(r'D:\TB331FC_GSI_Kit\08_一键刷机\fw\vendor_boot.img', 'rb').read()
    # the accepted dtb section starts at 0xB19000 and holds several FDTs
    sec = fw[0xB19000:0xB19000 + 0x13B1C2]
    pos = 0
    n = 0
    while True:
        i = sec.find(FDT, pos)
        if i < 0:
            break
        tot = struct.unpack_from('>I', sec, i + 4)[0]
        if 40 <= tot and i + tot <= len(sec) and struct.unpack_from('>I', sec, i + 20)[0] == 17:
            n += 1
            show(f'factory dtb FDT#{n} @sec+0x{i:x}', sec[i:i + tot])
            pos = i + tot
        else:
            pos = i + 4
    print()
    show('ours: ref_pmic.dtb', open(r'D:\TB331FCLinux\build\ref_pmic.dtb', 'rb').read())
    show('device own: tb331fc_stock.dtb', open(r'C:\Users\Pluto\Desktop\tb331fc_stock.dtb', 'rb').read())
