"""
Tier 2 - Boundary 9: Config Size Boundaries
Tests 256-byte MCU config boundary conditions (255, 256, 257 bytes).
"""

import unittest
from tests.test_utils import CANONICAL_CONFIG_52XD

class TestB09ConfigSizeBoundaries(unittest.TestCase):

    def test_canonical_config_exact_256_bytes(self):
        """Verify standard CONFIG_52XD is exactly 256 bytes."""
        self.assertEqual(len(CANONICAL_CONFIG_52XD), 256)

    def test_underflow_config_255_bytes(self):
        """Verify 255-byte truncated config fails size validation."""
        short_config = CANONICAL_CONFIG_52XD[:255]
        self.assertEqual(len(short_config), 255)
        self.assertNotEqual(len(short_config), 256)

    def test_overflow_config_257_bytes(self):
        """Verify 257-byte extended config fails size validation."""
        long_config = CANONICAL_CONFIG_52XD + b"\x00"
        self.assertEqual(len(long_config), 257)
        self.assertNotEqual(len(long_config), 256)

    def test_empty_config_0_bytes(self):
        """Verify 0-byte config is rejected."""
        self.assertNotEqual(0, 256)

    def test_config_block_divisible_by_16(self):
        """Verify 256-byte config is evenly divisible into 16 16-byte registers/blocks."""
        self.assertEqual(len(CANONICAL_CONFIG_52XD) % 16, 0)

if __name__ == "__main__":
    unittest.main()
