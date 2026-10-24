#!/usr/bin/env python3
"""Extract DT match keys (msm-id / board-id / pmic-id / ddr-id / model) from any
FDT blob or from a Qualcomm dtbo/dt table container."""
import struct, sys

FDT_MAGIC = 0xd00dfeed


def parse_props(blob):
    if len(blob) < 40 or struct.unpack_from('>I', blob, 0)[0] != FDT_MAGIC:
        return None
    off_struct = struct.unpack_from('>I', blob, 8)[0]
    off_strings = struct.unpack_from('>I', blob, 12)[0]
    p = off_struct
    tag = struct.unpack_from('>I', blob, p)[0]
    if tag != 1:
        return None
    p += 4
    while blob[p] != 0:
        p += 1
    p = (p + 4) & ~3
    props = {}
    depth = 0
    while p + 4 <= len(blob):
        tag = struct.unpack_from('>I', blob, p)[0]; p += 4
        if tag == 1:
            depth += 1
            while blob[p] != 0:
                p += 1
            p = (p + 4) & ~3
            if depth == 1:
                break          # stop at first child node
            continue
        if tag == 2:
            break
        if tag == 4:
            continue
        if tag == 9:
            break
        if tag == 3:
            ln, nameoff = struct.unpack_from('>II', blob, p); p += 8
            val = blob[p:p + ln]; p = (p + ln + 3) & ~3
            end = blob.find(b'\0', off_strings + nameoff)
            name = blob[off_strings + nameoff:end].decode('ascii', 'replace')
            props[name] = val
    return props


def as_u32s(v):
    if len(v) % 4:
        return None
    return struct.unpack(f'>{len(v)//4}I', v)


def show(blob, label):
    props = parse_props(blob)
    if props is None:
        print(f'  {label}: NOT a valid FDT')
        return
    print(f'  {label}:')
    for k in ('model', 'compatible'):
        if k in props:
            print(f'      {k:16s} = {props[k].split(bchr)[0].decode("ascii","replace") if False else props[k].split(bytes([0]))[0].decode("ascii","replace")}')
    for k in ('qcom,msm-id', 'qcom,board-id', 'qcom,pmic-id', 'qcom,ddr-id',
              'qcom,platform-id', 'qcom,board-subtype', 'qcom,msm-name'):
        if k in props:
            u = as_u32s(props[k])
            if u is not None:
                pairs = ' '.join(f'<0x{x:x} 0x{y:x}>' if False else f'0x{x:x}' for x in u)
                print(f'      {k:16s} = {pairs}   (raw {len(u)} u32)')
            else:
                print(f'      {k:16s} = {props[k].hex()}')
        else:
            print(f'      {k:16s} = <absent>')


bchr = bytes([0])


def scan_fdts(data, label):
    """find all FDT blobs in a container"""
    idx = 0
    pos = 0
    while True:
        i = data.find(struct.pack('>I', FDT_MAGIC), pos)
        if i < 0:
            break
        if i + 8 > len(data):
            break
        tot = struct.unpack_from('>I', data, i + 4)[0]
        if 40 <= tot <= 4 * 1024 * 1024 and i + tot <= len(data):
            show(data[i:i + tot], f'{label} FDT#{idx} @0x{i:x} (tot=0x{tot:x})')
            idx += 1
            pos = i + tot
        else:
            pos = i + 4


def dtbo_table(data, label):
    """Qualcomm dtbo container: magic 0xd7b7ab1e, then dt_entry table"""
    if len(data) < 32:
        return False
    magic, total, hdrsz, entry_off, entry_count, entry_size = struct.unpack_from('>6I', data, 0)
    if magic != 0xd7b7ab1e:
        return False
    print(f'  {label}: dtbo container magic OK total=0x{total:x} hdrsz=0x{hdrsz:x} '
          f'entry_off=0x{entry_off:x} count={entry_count} entry_size=0x{entry_size:x}')
    for n in range(entry_count):
        base = entry_off + n * entry_size
        sz, off, mid, bid, pmic, dbi = struct.unpack_from('>6I', data, base)
        print(f'    entry {n}: size=0x{sz:x} off=0x{off:x} msm-id=0x{mid:x} '
              f'board-id=0x{bid:x} pmic-id(mask?)=0x{pmic:x} 0x{dbi:x}')
        if off + sz <= len(data):
            props = parse_props(data[off:off + sz])
            if props:
                model = props.get('model', b'').split(bytes([0]))[0].decode('ascii', 'replace')
                u = as_u32s(props.get('qcom,board-id', b''))
                m = as_u32s(props.get('qcom,msm-id', b''))
                p = as_u32s(props.get('qcom,pmic-id', b''))
                print(f'             model="{model}" msm-id={[hex(x) for x in m] if m else None} '
                      f'board-id={[hex(x) for x in u] if u else None} '
                      f'pmic-id={[hex(x) for x in p] if p else None}')
    return True


for path in sys.argv[1:]:
    data = open(path, 'rb').read()
    print('=' * 78)
    print(f'FILE {path} size=0x{len(data):x}')
    if not dtbo_table(data, path):
        if data[:4] == struct.pack('>I', FDT_MAGIC):
            show(data, path)
        else:
            scan_fdts(data, path)
    print()
