#!/usr/bin/env python3
"""Parse USBPcap pcapng/pcap: list USB transfer mix, then decode Goodix packs."""
import struct, sys, collections

def read_pcapng(path):
    data = open(path, 'rb').read()
    assert struct.unpack('<I', data[:4])[0] == 0x0A0D0D0A, 'not pcapng'
    off, pkts = 0, []
    endian = '<'
    while off + 12 <= len(data):
        blk, blen = struct.unpack_from(endian + 'II', data, off)
        if blk == 0x0A0D0D0A and off > 0:
            # resync not needed; SHB only first
            pass
        if blen < 12 or off + blen > len(data):
            break
        body = data[off+8:off+blen-4]
        if blk == 6:  # EPB
            iface, ts_hi, ts_lo, cap_len, orig_len = struct.unpack_from(endian + 'IIIII', body, 0)
            pkts.append(body[20:20+cap_len])
        elif blk == 3:  # SPB (no iface; assume 0)
            orig_len, = struct.unpack_from(endian + 'I', body, 0)
            pkts.append(body[4:4+orig_len])
        off += blen
    return pkts

def read_pcap(path):
    data = open(path, 'rb').read()
    magic, = struct.unpack_from('<I', data, 0)
    assert magic in (0xA1B2C3D4, 0xA1B23C4D), 'not pcap'
    off, pkts = 24, []
    while off + 16 <= len(data):
        cap_len, orig_len = struct.unpack_from('<II', data, off+8)
        pkts.append(data[off+16:off+16+cap_len])
        off += 16 + cap_len
    return pkts

def usb_info(pkt):
    # USBPcap pseudo-header, 27 bytes
    if len(pkt) < 27:
        return None
    header_len, irp_id, status, function, info, bus, dev, ep, transfer, data_len = \
        struct.unpack_from('<HQIHBHHBBI', pkt, 0)
    return dict(irp=irp_id, status=status, func=function, info=info,
                bus=bus, dev=dev, ep=ep, transfer=transfer,
                dlen=data_len, payload=pkt[header_len:header_len+data_len])

def main(path):
    magic = open(path, 'rb').read(4)
    pkts = read_pcapng(path) if magic == b'\x0a\x0d\x0d\x0a' else read_pcap(path)
    print('packets:', len(pkts))
    mix = collections.Counter()
    devs = collections.Counter()
    for p in pkts:
        u = usb_info(p)
        if not u:
            mix['short'] += 1
            continue
        mix[(u['ep'], u['func'], u['info'], u['transfer'])] += 1
        devs[(u['bus'], u['dev'], u['ep'])] += 1
    print('--- transfer mix (ep, func, info, transfer): count')
    for k, v in mix.most_common(20):
        ep, func, info, tr = k
        print('  ep=%02x func=%04x info=%02x tr=%d : %d' % (ep, func, info, tr, v))
    print('--- top endpoints (bus, dev, ep): count')
    for k, v in devs.most_common(10):
        print('  bus=%d dev=%d ep=%02x : %d' % (k[0], k[1], k[2], v))

if __name__ == '__main__':
    main(sys.argv[1])
