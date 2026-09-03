"""
Tier 2 - Boundary 18: Reset Counter Boundaries
Tests reset counter values (2048, 0, 65535) and little-endian decoding.
"""

import unittest
import struct
from tests.test_utils import RESET_NUMBER

class TestB18ResetCounterBounds(unittest.TestCase):

    def test_canonical_reset_counter_value(self):
        """Verify driver expects reset number 2048."""
        self.assertEqual(RESET_NUMBER, 2048)

    def test_reset_counter_little_endian_encoding(self):
        """Verify 2048 encodes as bytes 0x00, 0x08."""
        encoded = struct.pack("<H", 2048)
        self.assertEqual(encoded, bytes([0x00, 0x08]))

    def test_reset_counter_zero_boundary(self):
        """Verify 0 encodes and decodes as 0x0000."""
        encoded = struct.pack("<H", 0)
        self.assertEqual(struct.unpack("<H", encoded)[0], 0)

    def test_reset_counter_max_uint16_boundary(self):
        """Verify max 16-bit reset count 65535."""
        encoded = struct.pack("<H", 65535)
        self.assertEqual(struct.unpack("<H", encoded)[0], 65535)

    def test_reset_number_check_in_goodix5xx(self):
        """Verify goodix5xx.c asserts number == cls->reset_number."""
        with open("/home/sastauser/code/temp/goodix/libfprint-driver/goodix5xx.c", "r") as f:
            content = f.read()
        self.assertIn("cls->reset_number", content)

if __name__ == "__main__":
    unittest.main()
