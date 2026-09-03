"""
Tier 2 - Boundary 14: Framing Pad Boundaries
Tests 64-byte padding boundaries, unpadded framing, and trailing zero tolerances.
"""

import unittest
from tests.test_utils import (
    encode_pack, decode_pack, FLAGS_MSG_PROTOCOL
)

class TestB14FramingPadBounds(unittest.TestCase):

    def test_pad_boundary_63_bytes(self):
        """Verify 63-byte packet is padded by 1 byte to 64."""
        data = b"\x11" * 59  # 4B header + 59B data = 63B
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, data, pad_data=True)
        self.assertEqual(len(pkt), 64)

    def test_pad_boundary_64_bytes(self):
        """Verify 64-byte packet is not padded."""
        data = b"\x11" * 60  # 4B header + 60B data = 64B
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, data, pad_data=True)
        self.assertEqual(len(pkt), 64)

    def test_pad_boundary_65_bytes(self):
        """Verify 65-byte packet is padded by 63 bytes to 128."""
        data = b"\x11" * 61  # 4B header + 61B data = 65B
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, data, pad_data=True)
        self.assertEqual(len(pkt), 128)

    def test_pad_boundary_128_bytes(self):
        """Verify 128-byte packet is not padded."""
        data = b"\x11" * 124  # 4B header + 124B data = 128B
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, data, pad_data=True)
        self.assertEqual(len(pkt), 128)

    def test_decoder_ignores_trailing_padding_zeros(self):
        """Verify decode_pack extracts only the declared payload length and ignores trailing pad zeros."""
        data = b"\x11" * 10
        pkt = encode_pack(FLAGS_MSG_PROTOCOL, data, pad_data=True)  # Padded to 64B
        ok, flags, payload, _ = decode_pack(pkt)
        self.assertTrue(ok)
        self.assertEqual(payload, data)
        self.assertEqual(len(payload), 10)

if __name__ == "__main__":
    unittest.main()
