"""
Tier 2 - Boundary 5: Zero-Length Payloads
Tests framing and command behaviors on empty payloads.
"""

import unittest
from tests.test_utils import (
    encode_pack, decode_pack, encode_protocol, decode_protocol,
    FLAGS_MSG_PROTOCOL, FLAGS_TLS, CMD_NOP
)

class TestB05ZeroPayloads(unittest.TestCase):

    def test_zero_byte_pack_payload(self):
        """Verify encode and decode with 0-byte payload."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, b"", pad_data=False)
        self.assertEqual(len(pkt), 4)  # 3B header + 1B checksum
        ok, flags, payload, valid_chk = decode_pack(pkt)
        self.assertTrue(ok)
        self.assertTrue(valid_chk)
        self.assertEqual(payload, b"")

    def test_zero_byte_protocol_payload(self):
        """Verify protocol message with 0-byte payload (e.g. NOP)."""
        proto_pkt = encode_protocol(CMD_NOP, b"", pad_data=False)
        self.assertEqual(len(proto_pkt), 4)  # 1B cmd + 2B len + 0B payload + 1B chk
        p_ok, cmd, payload, valid_chk, _ = decode_protocol(proto_pkt)
        self.assertTrue(p_ok)
        self.assertTrue(valid_chk)
        self.assertEqual(payload, b"")

    def test_zero_byte_nested_pack_and_protocol(self):
        """Verify nested pack wrapping empty protocol message."""
        proto = encode_protocol(CMD_NOP, b"", pad_data=False)
        pack = encode_pack(FLAGS_MSG_PROTOCOL, proto, pad_data=False)
        ok, flags, body, _ = decode_pack(pack)
        self.assertTrue(ok)
        p_ok, cmd, p_body, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_NOP)
        self.assertEqual(p_body, b"")

    def test_empty_tls_flag_pack(self):
        """Verify empty TLS control message."""
        pkt = encode_pack(FLAGS_TLS, b"", pad_data=False)
        ok, flags, payload, _ = decode_pack(pkt)
        self.assertTrue(ok)
        self.assertEqual(flags, FLAGS_TLS)
        self.assertEqual(payload, b"")

    def test_zero_byte_payload_checksum_correctness(self):
        """Verify checksum for 0-byte NOP packet."""
        proto = encode_protocol(CMD_NOP, b"", calc_checksum=True, pad_data=False)
        # cmd=0x00, len=0x0001 (1, 0). sum = 0 + 1 + 0 = 1. chk = 0xAA - 1 = 0xA9 (169)
        self.assertEqual(proto[3], 0xA9)

if __name__ == "__main__":
    unittest.main()
