"""
Tier 2 - Boundary 1: USB Chunk Boundaries
Tests USB EP OUT chunk padding and alignment across boundary payload sizes.
"""

import unittest
from tests.test_utils import encode_pack, encode_protocol, decode_pack, FLAGS_MSG_PROTOCOL, CMD_NOP, EP_OUT_CHUNK_SIZE

class TestB01USBChunkBoundaries(unittest.TestCase):

    def test_exact_64byte_packet_padding(self):
        """Verify packet already 64 bytes is not extended to 128 bytes unnecessarily."""
        payload = b"\x00" * 56  # 4B pack header + 4B proto header + 56B payload = 64B
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, payload, pad_data=False), pad_data=True)
        self.assertEqual(len(pkt), 64)

    def test_65byte_packet_padded_to_128(self):
        """Verify packet of 65 bytes is padded to 128 bytes (next 64-byte multiple)."""
        payload = b"\x00" * 57
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, payload, pad_data=False), pad_data=True)
        self.assertEqual(len(pkt), 128)

    def test_1byte_payload_padded_to_64(self):
        """Verify minimal 1-byte payload is padded to 64 bytes."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"\x01", pad_data=False), pad_data=True)
        self.assertEqual(len(pkt), 64)

    def test_0byte_payload_padded_to_64(self):
        """Verify 0-byte payload is padded to 64 bytes."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"", pad_data=False), pad_data=True)
        self.assertEqual(len(pkt), 64)

    def test_unpadded_packet_length(self):
        """Verify pad_data=False produces exact unpadded wire length."""
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, encode_protocol(CMD_NOP, b"12345", pad_data=False), pad_data=False)
        # 4B Pack (flags, len, chk) + (1B cmd + 2B len + 5B payload + 1B chk) = 13B
        self.assertEqual(len(pkt), 13)

if __name__ == "__main__":
    unittest.main()
