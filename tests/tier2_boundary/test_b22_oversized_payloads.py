"""
Tier 2 - Boundary 22: Oversized Payloads
Tests rejection of oversized packets that exceed buffer limits.
"""

import unittest
from tests.test_utils import (
    decode_pack, decode_protocol, encode_pack, encode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_NOP
)

class TestB22OversizedPayloads(unittest.TestCase):

    def test_pack_length_exceeding_buffer(self):
        """Verify pack header claiming length 60000 on a 10-byte buffer fails decode."""
        hdr = b"\xa0\x60\xea\x8a"  # length = 60000
        ok, _, _, _ = decode_pack(hdr + b"\x00" * 6)
        self.assertFalse(ok)

    def test_protocol_length_exceeding_buffer(self):
        """Verify protocol header claiming length 50000 on a 5-byte buffer fails decode."""
        proto = b"\x00\x50\xc3\x01\x02"  # wire_len = 50000
        ok, _, _, _, _ = decode_protocol(proto)
        self.assertFalse(ok)

    def test_nested_oversized_payload(self):
        """Verify nested protocol length mismatch inside pack."""
        bad_proto = b"\x00\x00\x10\x01\x02\x03\x04"
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, bad_proto, pad_data=False)
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, _, _, _, _ = decode_protocol(body)
        self.assertFalse(p_ok)

    def test_max_uint16_declared_length_rejection(self):
        """Verify 0xFFFF declared length with small buffer is cleanly rejected."""
        hdr = b"\xa0\xff\xff\x9e\x01\x02"
        ok, _, _, _ = decode_pack(hdr)
        self.assertFalse(ok)

    def test_zero_wire_len_in_protocol(self):
        """Verify protocol with wire_len=0 (which would underflow wire_len - 1) is rejected."""
        bad_proto = b"\x00\x00\x00\x00"  # cmd=0, wire_len=0
        ok, _, _, _, _ = decode_protocol(bad_proto)
        self.assertFalse(ok)

if __name__ == "__main__":
    unittest.main()
