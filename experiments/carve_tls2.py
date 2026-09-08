#!/usr/bin/env python3
"""Per-pack TLS carve: each 0xb2 pack = 8B inner hdr + TLS records + 1B trail."""
import struct, sys, collections
from parse_win import read_pcapng, read_pcap, usb_info
from decode_win import decode_packs

HS_NAMES = {0: 'HelloRequest', 1: 'ClientHello', 2: 'ServerHello',
            11: 'Certificate', 12: 'ServerKeyExchange', 13: 'CertificateRequest',
            14: 'ServerHelloDone', 15: 'CertificateVerify', 16: 'ClientKeyExchange',
            20: 'Finished'}
REC_NAMES = {20: 'ChangeCipherSpec', 21: 'Alert', 22: 'Handshake', 23: 'AppData'}

def main(path, bus, dev):
    magic = open(path, 'rb').read(4)
    pkts = read_pcapng(path) if magic == b'\x0a\x0d\x0d\x0a' else read_pcap(path)
    streams = {}
    for p in pkts:
        u = usb_info(p)
        if not u or (u['bus'], u['dev']) != (bus, dev) or u['transfer'] != 3:
            continue
        if (u['ep'] == 0x01 and u['info'] == 0) or (u['ep'] == 0x83 and u['info'] == 1):
            if u['dlen']:
                streams.setdefault(u['ep'], bytearray()).extend(u['payload'][:u['dlen']])
    for ep in (0x01, 0x83):
        s = streams.get(ep, bytearray())
        packs = [p for p in decode_packs(s, ep) if p[1] in (0xb0, 0xb2)]
        direction = 'HOST->DEV' if ep == 0x01 else 'DEV->HOST'
        print('--- %s: %d TLS packs' % (direction, len(packs)))
        hdrs = collections.Counter()
        rectypes = collections.Counter()
        hs_detail = []
        bad = 0
        for off, flags, pay in packs:
            if len(pay) < 14:
                bad += 1
                continue
            hdrs[pay[:8].hex()] += 1
            body = pay[9:]
            # walk records inside pack; last byte may be trailing checksum
            o = 0
            ok = True
            while o + 5 <= len(body):
                typ = body[o]
                if typ not in REC_NAMES:
                    ok = False
                    break
                ver = struct.unpack_from('>H', body, o + 1)[0]
                ln = struct.unpack_from('>H', body, o + 3)[0]
                if ver not in (0x0301, 0x0302, 0x0303):
                    ok = False
                    break
                frag = body[o + 5:o + 5 + ln]
                if len(frag) != ln:
                    ok = False
                    break
                rectypes[REC_NAMES[typ]] += 1
                if typ == 22 and len(frag) >= 4:
                    htype = frag[0]
                    hlen = struct.unpack_from('>I', b'\x00' + frag[1:4])[0]
                    extra = ''
                    if htype == 16 and len(frag) >= 6:
                        ilen = struct.unpack_from('>H', frag, 4)[0]
                        ident = frag[6:6 + ilen] if 0 <= ilen <= len(frag) - 6 else b''
                        extra = ' identity=%s' % ident.hex()
                    if htype == 12 and len(frag) >= 6:
                        hl = struct.unpack_from('>H', frag, 4)[0]
                        hint = frag[6:6 + hl] if 0 <= hl <= len(frag) - 6 else b''
                        try:
                            extra = ' hint=%r' % hint.decode('ascii')
                        except Exception:
                            extra = ' hint=%s' % hint.hex()
                    hs_detail.append((off, HS_NAMES.get(htype, htype), hlen, extra))
                o += 5 + ln
                if o == len(body) - 1:
                    break  # 1 trailing byte
                if o >= len(body):
                    break
            if not ok:
                bad += 1
        print('    inner-hdrs:', dict(hdrs.most_common(5)))
        print('    records:', dict(rectypes), 'unpackable-packs:', bad)
        for off, name, hlen, extra in hs_detail[:30]:
            print('    packoff=%d HS %s len=%d%s' % (off, name, hlen, extra))

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
