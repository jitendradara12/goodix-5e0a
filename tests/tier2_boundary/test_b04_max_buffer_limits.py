"""
Tier 2 - Boundary 4: Max Buffer Limits
Tests buffer allocations up to 64KB (EP_IN_MAX_BUF_SIZE = 0x10000).
"""

import unittest
from tests.test_utils import (
    EP_IN_MAX_BUF_SIZE, encode_pack, decode_pack, FLAGS_TLS_DATA
)

class TestB04MaxBufferLimits(unittest.TestCase):

    def test_max_in_buffer_size_constant(self):
        """Verify maximum EP IN buffer is 64KB (65536 bytes)."""
        self.assertEqual(EP_IN_MAX_BUF_SIZE, 0x10000)

    def test_64kb_payload_encoding_and_decoding(self):
        """Verify pack encoder/decoder handles maximum 64KB data buffer without integer truncation."""
        max_payload = b"\x5a" * 65530
        pkt = encode_pack(FLAGS_TLS_DATA, max_payload, pad_data=False)
        ok, flags, decoded_payload, chk_ok = decode_pack(pkt)
        self.assertTrue(ok)
        self.assertTrue(chk_ok)
        self.assertEqual(len(decoded_payload), 65530)

    def test_single_byte_under_max_limit(self):
        """Verify boundary at 65535 bytes (uint16 max)."""
        payload = b"\x01" * 65535
        pkt = encode_pack(FLAGS_TLS_DATA, payload, pad_data=False)
        ok, flags, decoded_payload, _ = decode_pack(pkt)
        self.assertTrue(ok)
        self.assertEqual(len(decoded_payload), 65535)

    def test_exact_power_of_two_buffers(self):
        """Verify power-of-two buffer chunks (1KB, 2KB, 4KB, 8KB, 16KB, 32KB)."""
        for exp in [10, 11, 12, 13, 14, 15]:
            size = 1 << exp
            pkt = encode_pack(FLAGS_TLS_DATA, b"\x00" * size, pad_data=False)
            ok, _, payload, _ = decode_pack(pkt)
            self.assertTrue(ok)
            self.assertEqual(len(payload), size)

    def test_buffer_boundary_allocation_safety(self):
        """Verify no memory exhaustion on 64KB buffer decoding."""
        data = encode_pack(FLAGS_TLS_DATA, bytes([0xAA] * 64000), pad_data=False)
        ok, flags, payload, chk_ok = decode_pack(data)
        self.assertTrue(ok)
        self.assertEqual(payload[0], 0xAA)

if __name__ == "__main__":
    unittest.main()
