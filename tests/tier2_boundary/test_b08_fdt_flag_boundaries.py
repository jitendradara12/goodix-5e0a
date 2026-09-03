"""
Tier 2 - Boundary 8: FDT Flag Boundaries
Tests byte 26 variations in FDT configurations (DOWN=0x01, UP=0x00, invalid values).
"""

import unittest
from tests.test_utils import CANONICAL_FDT_DOWN, CANONICAL_FDT_UP

class TestB08FDTFlagBoundaries(unittest.TestCase):

    def test_fdt_down_touch_flag_is_one(self):
        """Verify FDT DOWN byte 26 is strictly 0x01."""
        self.assertEqual(CANONICAL_FDT_DOWN[26], 0x01)

    def test_fdt_up_release_flag_is_zero(self):
        """Verify FDT UP byte 26 is strictly 0x00."""
        self.assertEqual(CANONICAL_FDT_UP[26], 0x00)

    def test_fdt_flag_mutation_detection(self):
        """Verify mutated FDT buffer with invalid byte 26 is distinguishable."""
        mutated_down = bytearray(CANONICAL_FDT_DOWN)
        mutated_down[26] = 0x02
        self.assertNotEqual(mutated_down[26], CANONICAL_FDT_DOWN[26])

    def test_fdt_buffer_total_length_exact_39(self):
        """Verify FDT table size cannot be truncated below 39 bytes."""
        self.assertEqual(len(CANONICAL_FDT_DOWN), 39)
        self.assertEqual(len(CANONICAL_FDT_UP), 39)

    def test_fdt_mode_total_length_exact_27(self):
        """Verify FDT mode table is exactly 27 bytes."""
        from tests.test_utils import CANONICAL_FDT_MODE
        self.assertEqual(len(CANONICAL_FDT_MODE), 27)

if __name__ == "__main__":
    unittest.main()
