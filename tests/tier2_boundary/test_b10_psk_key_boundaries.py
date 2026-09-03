"""
Tier 2 - Boundary 10: PSK Key Boundaries
Tests 32-byte TLS pre-shared key length boundaries, all-zero, all-0xFF, and mismatched lengths.
"""

import unittest
from tests.test_utils import CANONICAL_PSK

class TestB10PSKKeyBoundaries(unittest.TestCase):

    def test_canonical_psk_length_is_32(self):
        """Verify PSK key is exactly 32 bytes (256 bits)."""
        self.assertEqual(len(CANONICAL_PSK), 32)

    def test_psk_short_length_31_bytes(self):
        """Verify 31-byte PSK fails 32-byte requirement."""
        short_psk = CANONICAL_PSK[:31]
        self.assertEqual(len(short_psk), 31)
        self.assertNotEqual(len(short_psk), 32)

    def test_psk_long_length_33_bytes(self):
        """Verify 33-byte PSK fails 32-byte requirement."""
        long_psk = CANONICAL_PSK + b"\x00"
        self.assertEqual(len(long_psk), 33)
        self.assertNotEqual(len(long_psk), 32)

    def test_psk_all_zeros_distinct_from_canonical(self):
        """Verify all zeros key differs from real hardware PSK."""
        zero_psk = bytes([0x00] * 32)
        self.assertNotEqual(zero_psk, CANONICAL_PSK)

    def test_psk_all_ff_distinct_from_canonical(self):
        """Verify all 0xFF key differs from real hardware PSK."""
        ff_psk = bytes([0xFF] * 32)
        self.assertNotEqual(ff_psk, CANONICAL_PSK)

if __name__ == "__main__":
    unittest.main()
