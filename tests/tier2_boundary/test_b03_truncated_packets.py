"""
Tier 2 - Boundary 3: Truncated Packets
Tests decoder resilience against short/partial wire packets.
"""

import unittest
from tests.test_utils import decode_pack, decode_protocol, encode_pack, encode_protocol, FLAGS_MSG_PROTOCOL, CMD_NOP

class TestB03TruncatedPackets(unittest.TestCase):

    def test_decode_pack_empty_buffer(self):
        """Verify decode_pack safely fails on empty 0-byte buffer."""
        ok, flags, payload, valid_chk = decode_pack(b"")
        self.assertFalse(ok)

    def test_decode_pack_short_headers(self):
        """Verify decode_pack fails on 1, 2, or 3 byte inputs (less than 4-byte header)."""
        for length in [1, 2, 3]:
            ok, _, _, _ = decode_pack(b"\xa0\x00\x00"[:length])
            self.assertFalse(ok)

    def test_decode_pack_truncated_payload(self):
        """Verify decode_pack fails when wire length is less than header declared length."""
        # Header specifies length = 10, but provide only 2 payload bytes
        bad_packet = b"\xa0\x0a\x00\xaa\x01\x02"
        ok, _, _, _ = decode_pack(bad_packet)
        self.assertFalse(ok)

    def test_decode_protocol_short_header(self):
        """Verify decode_protocol fails on packets smaller than 4 bytes."""
        for length in [0, 1, 2, 3]:
            ok, _, _, _, _ = decode_protocol(b"\x00\x01\x00"[:length])
            self.assertFalse(ok)

    def test_decode_protocol_truncated_payload(self):
        """Verify decode_protocol fails when wire length < protocol declared length."""
        # cmd=0x00, wire_len=10 (payload_len=9), but only provide 3 bytes total
        bad_proto = b"\x00\x0a\x00\x01\x02"
        ok, _, _, _, _ = decode_protocol(bad_proto)
        self.assertFalse(ok)

if __name__ == "__main__":
    unittest.main()
