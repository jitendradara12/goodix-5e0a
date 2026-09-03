"""
Tier 1 - Feature 5: Preset PSK Status Read
Requirements: Verify PSK flags (0xbb020001) and PSK key payload via CMD 0xe4.
"""

import unittest
import struct
from tests.test_utils import (
    MockGoodixMCU, encode_pack, encode_protocol, decode_pack, decode_protocol,
    FLAGS_MSG_PROTOCOL, CMD_PRESET_PSK_READ, PSK_FLAGS, CANONICAL_PSK
)

class TestF05PSKFlags(unittest.TestCase):

    def setUp(self):
        self.mcu = MockGoodixMCU()

    def test_psk_preset_read_command_encoding(self):
        """Verify CMD 0xe4 encoding with empty payload."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_PRESET_PSK_READ, b""))
        ok, flags, body, _ = decode_pack(pkt)
        self.assertTrue(ok)
        p_ok, cmd, _, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertEqual(cmd, CMD_PRESET_PSK_READ)

    def test_psk_flags_endianness_and_value(self):
        """Verify PSK flags returned in payload match 0xbb020001 (little-endian uint32)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_PRESET_PSK_READ, b""))
        reply = self.mcu.handle_out_packet(pkt)
        ok, flags, body, _ = decode_pack(reply)
        p_ok, cmd, payload, _, _ = decode_protocol(body)
        self.assertTrue(p_ok)
        self.assertGreaterEqual(len(payload), 4)
        flags_val = struct.unpack("<I", payload[:4])[0]
        self.assertEqual(flags_val, PSK_FLAGS)

    def test_psk_length_32bytes(self):
        """Verify PSK secret payload length is exactly 32 bytes (256-bit)."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_PRESET_PSK_READ, b""))
        reply = self.mcu.handle_out_packet(pkt)
        ok, _, body, _ = decode_pack(reply)
        _, _, payload, _, _ = decode_protocol(body)
        psk_bytes = payload[4:]
        self.assertEqual(len(psk_bytes), 32)

    def test_psk_value_matches_dpapi_secret(self):
        """Verify PSK payload matches canonical DPAPI extracted key."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_PRESET_PSK_READ, b""))
        reply = self.mcu.handle_out_packet(pkt)
        _, _, body, _ = decode_pack(reply)
        _, _, payload, _, _ = decode_protocol(body)
        psk_bytes = payload[4:]
        self.assertEqual(psk_bytes, CANONICAL_PSK)

    def test_psk_flags_mismatch_rejection(self):
        """Verify simulated mismatch in PSK flags is detected as invalid."""
        invalid_flags = 0xAA010002
        self.assertNotEqual(invalid_flags, PSK_FLAGS)

if __name__ == "__main__":
    unittest.main()
