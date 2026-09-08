#!/usr/bin/env python3
"""Decode Goodix pack stream from USBPcap capture. Phase 2: command sequence."""
import struct, sys
from parse_win import read_pcapng, read_pcap, usb_info

CMD_NAMES = {
    0x00: 'NOP', 0x20: 'GET_IMAGE', 0x32: 'FDT_DOWN', 0x34: 'FDT_UP',
    0x36: 'FDT_MODE', 0x50: 'NAV_0', 0x70: 'IDLE', 0x80: 'WRITE_REG',
    0x82: 'READ_REG', 0x90: 'UPLOAD_CONFIG', 0x94: 'PWRDOWN_FREQ',
    0x96: 'ENABLE_CHIP', 0xa2: 'RESET', 0xa6: 'READ_OTP', 0xa8: 'FW_VER',
    0xac: 'POV_CONFIG', 0xae: 'QUERY_STATE', 0xb0: 'ACK', 0xc4: 'SET_DRV_STATE',
    0xd0: 'REQ_TLS', 0xd2: 'GET_POV_IMAGE', 0xd4: 'TLS_ESTABLISHED',
    0xe0: 'PSK_WRITE', 0xe4: 'PSK_READ',
}

def decode_packs(stream, label):
    """Yield (off, flags, payload) with checksum validation."""
    off, out = 0, []
    while off + 4 <= len(stream):
        flags = stream[off]
        if flags not in (0xa0, 0xb0, 0xb2):
            off += 1
            continue
        plen = struct.unpack_from('<H', stream, off + 1)[0]
        cks = stream[off + 3]
        if sum(stream[off:off + 3]) & 0xFF != cks:
            off += 1
            continue
        end = off + 4 + plen
        if end > len(stream):
            break
        out.append((off, flags, bytes(stream[off + 4:end])))
        off = end
    return out

def main(path, bus=2, dev=1, maxcmd=120):
    magic = open(path, 'rb').read(4)
    pkts = read_pcapng(path) if magic == b'\x0a\x0d\x0d\x0a' else read_pcap(path)
    streams = {}
    for p in pkts:
        u = usb_info(p)
        if not u or (u['bus'], u['dev']) != (bus, dev):
            continue
        if u['ep'] not in (0x01, 0x83) or u['transfer'] != 3:
            continue
        # data: OUT ep01 from SUBMIT(info 0), IN ep83 from COMPLETE(info 1)
        if (u['ep'] == 0x01 and u['info'] == 0) or (u['ep'] == 0x83 and u['info'] == 1):
            if u['dlen']:
                streams.setdefault(u['ep'], bytearray()).extend(u['payload'][:u['dlen']])
    for ep in (0x01, 0x83):
        s = streams.get(ep, bytearray())
        print('--- ep=%02x stream bytes: %d' % (ep, len(s)))
        n = 0
        for off, flags, pay in decode_packs(s, ep):
            if n >= maxcmd:
                print('  ... truncated'); break
            n += 1
            if flags == 0xa0 and len(pay) >= 3:
                cmd = pay[0]
                ln = struct.unpack_from('<H', pay, 1)[0]
                body = pay[3:3 + ln - 1] if ln >= 1 else b''
                print('  [%3d] off=%6d PROTO cmd=0x%02x %-14s len=%3d body=%s' % (
                    n, off, cmd, CMD_NAMES.get(cmd, '?'), len(body), body[:48].hex()))
            else:
                tag = 'TLS' if flags in (0xb0, 0xb2) else '?'
                print('  [%3d] off=%6d %s flags=0x%02x len=%5d head=%s' % (
                    n, off, tag, flags, len(pay), pay[:32].hex()))

if __name__ == '__main__':
    main(sys.argv[1])
