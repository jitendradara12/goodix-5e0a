"""
Tier 2 - Boundary 23: Zero Division Guard
Tests arithmetic safety against zero-range normalization in squashing and demosaicing.
"""

import unittest
from tests.test_utils import (
    squash_frame_linear, process_frame_demosaic, FRAME_PIXELS
)

class TestB23ZeroDivisionGuard(unittest.TestCase):

    def test_squash_all_zeros_no_division_by_zero(self):
        """Verify squashing array of all 0s produces 0s without zero-division exception."""
        pixels = [0] * FRAME_PIXELS
        squashed = squash_frame_linear(pixels)
        self.assertEqual(len(squashed), FRAME_PIXELS)
        self.assertEqual(squashed, [0] * FRAME_PIXELS)

    def test_squash_all_identical_large_values(self):
        """Verify squashing array of all 3500s produces 0s without zero-division exception."""
        pixels = [3500] * FRAME_PIXELS
        squashed = squash_frame_linear(pixels)
        self.assertEqual(squashed, [0] * FRAME_PIXELS)

    def test_demosaic_all_zeros_no_division_by_zero(self):
        """Verify demosaicing all 0s produces all 0s without zero-division exception."""
        squashed = [0] * FRAME_PIXELS
        out_img = process_frame_demosaic(squashed)
        self.assertEqual(len(out_img), 20480)
        self.assertEqual(out_img, [0] * 20480)

    def test_demosaic_all_255s_no_division_by_zero(self):
        """Verify demosaicing all 255s produces safe output without zero-division exception."""
        squashed = [255] * FRAME_PIXELS
        out_img = process_frame_demosaic(squashed)
        self.assertEqual(len(out_img), 20480)

    def test_single_value_difference_range_one(self):
        """Verify squashing with range=1 (max-min=1) scales cleanly."""
        pixels = [1000] * FRAME_PIXELS
        pixels[0] = 1001
        squashed = squash_frame_linear(pixels)
        self.assertEqual(squashed[0], 255)
        self.assertEqual(squashed[1], 0)

if __name__ == "__main__":
    unittest.main()
