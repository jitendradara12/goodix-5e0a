"""
Tier 5 Adversarial Stress Test: Bilinear Demosaicing Edge Cases & Fuzzing
Tests the numerical stability, bounds enforcement, normalization, and memory safety
of the process_frame bilinear interpolation algorithm under synthetic edge cases.
"""

import unittest
import random
import math
from tests.test_utils import (
    process_frame_demosaic,
    process_raw_frame,
    SENSOR_WIDTH,
    SENSOR_HEIGHT,
    FRAME_PIXELS,
    IMAGE_OUT_WIDTH,
    IMAGE_OUT_HEIGHT,
    IMAGE_OUT_PIXELS,
)

class TestM2AdversarialDemosaic(unittest.TestCase):

    def test_edge_case_all_zeros(self):
        """Synthetic edge case: all 5120 input pixels are 0x00."""
        squashed = [0] * FRAME_PIXELS
        out_img = process_frame_demosaic(squashed)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        self.assertEqual(out_img, [0] * IMAGE_OUT_PIXELS)

    def test_edge_case_all_0xff(self):
        """Synthetic edge case: all 5120 input pixels are 0xFF (255)."""
        squashed = [255] * FRAME_PIXELS
        out_img = process_frame_demosaic(squashed)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        self.assertEqual(out_img, [255] * IMAGE_OUT_PIXELS)

    def test_edge_case_constant_intermediate(self):
        """Synthetic edge case: constant intermediate values (1, 128, 254)."""
        for val in [1, 42, 128, 200, 254]:
            squashed = [val] * FRAME_PIXELS
            # Direct bilinear demosaicing preserves constant value
            out_img = process_frame_demosaic(squashed)
            self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
            self.assertEqual(out_img, [val] * IMAGE_OUT_PIXELS)
            # 3x3 local contrast flattening suppresses uniform zero contrast to 0
            raw_out = process_raw_frame(squashed)
            self.assertEqual(raw_out, [0] * IMAGE_OUT_PIXELS)

    def test_edge_case_horizontal_gradient(self):
        """Synthetic edge case: linear horizontal gradient 0 -> 255 across row-major columns."""
        squashed = [0] * FRAME_PIXELS
        for r in range(SENSOR_HEIGHT):
            for c in range(SENSOR_WIDTH):
                val = int((c / (SENSOR_WIDTH - 1)) * 255)
                squashed[r * SENSOR_WIDTH + c] = val
        out_img = process_frame_demosaic(squashed)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        for r in range(IMAGE_OUT_HEIGHT):
            row_pixels = [out_img[r * IMAGE_OUT_WIDTH + c] for c in range(IMAGE_OUT_WIDTH)]
            # Monotonically non-decreasing
            for i in range(len(row_pixels) - 1):
                self.assertLessEqual(row_pixels[i], row_pixels[i + 1])

    def test_edge_case_vertical_gradient(self):
        """Synthetic edge case: linear vertical gradient 0 -> 255 down row-major rows."""
        squashed = [0] * FRAME_PIXELS
        for r in range(SENSOR_HEIGHT):
            val = int((r / (SENSOR_HEIGHT - 1)) * 255)
            for c in range(SENSOR_WIDTH):
                squashed[r * SENSOR_WIDTH + c] = val
        out_img = process_frame_demosaic(squashed)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        for c in range(IMAGE_OUT_WIDTH):
            col_pixels = [out_img[r * IMAGE_OUT_WIDTH + c] for r in range(IMAGE_OUT_HEIGHT)]
            # Monotonically non-decreasing down the column
            for i in range(len(col_pixels) - 1):
                self.assertLessEqual(col_pixels[i], col_pixels[i + 1])

    def test_edge_case_extreme_aspect_ratios_clamping(self):
        """Synthetic edge case: boundary clamping at left and right edges in 64x80 raster."""
        squashed = [0] * FRAME_PIXELS
        for r in range(SENSOR_HEIGHT):
            squashed[r * SENSOR_WIDTH + 0] = 50                 # left edge (col 0)
            squashed[r * SENSOR_WIDTH + (SENSOR_WIDTH - 1)] = 200 # right edge (col 63)
        out_img = process_frame_demosaic(squashed)

        # Left boundary pixels at x=0 clamp to column 0 (50)
        for r in range(IMAGE_OUT_HEIGHT):
            p0 = out_img[r * IMAGE_OUT_WIDTH + 0]
            self.assertEqual(p0, 50)

        # Right boundary pixels at x=127 clamp to column 63 (200)
        for r in range(IMAGE_OUT_HEIGHT):
            p_last = out_img[r * IMAGE_OUT_WIDTH + (IMAGE_OUT_WIDTH - 1)]
            self.assertEqual(p_last, 200)



    def test_fuzz_random_frames(self):
        """Fuzz testing: 100 randomized synthetic sensor frames."""
        rng = random.Random(1337)
        for _ in range(100):
            frame = [rng.randint(0, 255) for _ in range(FRAME_PIXELS)]
            out = process_frame_demosaic(frame)
            self.assertEqual(len(out), IMAGE_OUT_PIXELS)
            self.assertTrue(all(0 <= p <= 255 for p in out))


if __name__ == "__main__":
    unittest.main()
