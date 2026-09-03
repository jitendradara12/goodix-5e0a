"""
Tier 2 - Boundary 6: Pixel Extreme Values
Tests unpack, normalization, and squashing on extreme dynamic ranges (all 0, all 4095, single peak).
"""

import unittest
from tests.test_utils import (
    decode_12bit_frame, pack_12bit_frame, squash_frame_linear,
    FRAME_PIXELS
)

class TestB06PixelExtremeValues(unittest.TestCase):

    def test_all_black_pixels_0x000(self):
        """Verify unpack and squashing of all zero 12-bit pixels."""
        all_zeros = [0] * FRAME_PIXELS
        raw_bytes = pack_12bit_frame(all_zeros)
        unpacked = decode_12bit_frame(raw_bytes)
        self.assertEqual(unpacked, all_zeros)
        squashed = squash_frame_linear(unpacked)
        self.assertEqual(squashed, [0] * FRAME_PIXELS)

    def test_all_white_pixels_0xfff(self):
        """Verify unpack and squashing of all 4095 (0xFFF) 12-bit pixels."""
        all_max = [4095] * FRAME_PIXELS
        raw_bytes = pack_12bit_frame(all_max)
        unpacked = decode_12bit_frame(raw_bytes)
        self.assertEqual(unpacked, all_max)
        squashed = squash_frame_linear(unpacked)
        # When all pixels are identical, range is 0 -> squashes safely to 0s
        self.assertEqual(squashed, [0] * FRAME_PIXELS)

    def test_checkerboard_bipolar_extreme_pixels(self):
        """Verify squashing with alternating 0 and 4095 pixels."""
        bipolar = [0 if i % 2 == 0 else 4095 for i in range(FRAME_PIXELS)]
        squashed = squash_frame_linear(bipolar)
        self.assertEqual(squashed[0], 0)
        self.assertEqual(squashed[1], 255)

    def test_single_hot_pixel_spike(self):
        """Verify squashing with one max pixel among zeros."""
        pixels = [0] * FRAME_PIXELS
        pixels[2560] = 4095  # Center pixel spike
        squashed = squash_frame_linear(pixels)
        self.assertEqual(squashed[2560], 255)
        self.assertEqual(squashed[0], 0)
        self.assertEqual(squashed[5000], 0)

    def test_single_cold_pixel_valley(self):
        """Verify squashing with one zero pixel among max values."""
        pixels = [4095] * FRAME_PIXELS
        pixels[100] = 0
        squashed = squash_frame_linear(pixels)
        self.assertEqual(squashed[100], 0)
        self.assertEqual(squashed[0], 255)
        self.assertEqual(squashed[200], 255)

if __name__ == "__main__":
    unittest.main()
