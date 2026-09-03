"""
Tier 2 - Boundary 2: Checksum Boundaries
Tests arithmetic wrap-around, boundary complements, and null checksum verification.
"""

import unittest
from tests.test_utils import (
    calc_pack_checksum, calc_protocol_checksum,
    NULL_CHECKSUM
)

class TestB02ChecksumBoundaries(unittest.TestCase):

    def test_pack_checksum_overflow_wrap_around(self):
        """Verify pack checksum performs uint8 modulo addition."""
        data = bytes([0xFF, 0xFF, 0x02])  # 255 + 255 + 2 = 512 = 0x00
        chk = calc_pack_checksum(data, len(data))
        self.assertEqual(chk, 0x00)

    def test_protocol_checksum_exact_0xaa(self):
        """Verify protocol checksum when sum(data) is 0 yields 0xAA."""
        data = bytes([0x00, 0x00, 0x00])
        chk = calc_protocol_checksum(data, len(data))
        self.assertEqual(chk, 0xAA)

    def test_protocol_checksum_negative_wrap_around(self):
        """Verify protocol checksum when sum(data) > 0xAA wraps around uint8."""
        data = bytes([0xAB])  # 0xAA - 0xAB = -1 = 0xFF (255)
        chk = calc_protocol_checksum(data, len(data))
        self.assertEqual(chk, 0xFF)

    def test_null_checksum_constant(self):
        """Verify canonical NULL_CHECKSUM is 0x88."""
        self.assertEqual(NULL_CHECKSUM, 0x88)

    def test_checksum_boundary_all_0xff_bytes(self):
        """Verify checksum calculation on high-entropy sequence of 0xFF bytes."""
        data = bytes([0xFF] * 256)
        chk = calc_pack_checksum(data, len(data))
        self.assertEqual(chk, (256 * 255) & 0xFF)  # 65280 & 0xFF = 0x00

if __name__ == "__main__":
    unittest.main()
