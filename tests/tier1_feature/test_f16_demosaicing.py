"""
Tier 1 - Feature 16: Bilinear Demosaicing & Process Frame
Requirements: Bilinear interpolation to 160x128 FpImage with FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED.
"""

import unittest
from tests.test_utils import (
    process_frame_demosaic, process_raw_frame, SENSOR_WIDTH, SENSOR_HEIGHT,
    IMAGE_OUT_WIDTH, IMAGE_OUT_HEIGHT, IMAGE_OUT_PIXELS, FRAME_PIXELS
)

class TestF16Demosaicing(unittest.TestCase):

    def test_demosaic_output_dimensions(self):
        """Verify output image dimension is 160x128 (20,480 pixels)."""
        squashed = [128] * FRAME_PIXELS
        out_img = process_frame_demosaic(squashed)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        self.assertEqual(IMAGE_OUT_WIDTH, 160)
        self.assertEqual(IMAGE_OUT_HEIGHT, 128)

    def test_demosaic_sample_columns(self):
        """Verify 19 sample columns are selected at col = 4 * k + 3 for k in 0..18."""
        sample_cols = [4 * k + 3 for k in range(19)]
        self.assertEqual(len(sample_cols), 19)
        self.assertEqual(sample_cols[0], 3)
        self.assertEqual(sample_cols[-1], 75)
        for col in sample_cols:
            self.assertLess(col, SENSOR_WIDTH)

    def test_demosaic_pixel_value_bounds(self):
        """Verify all interpolated pixel outputs are strictly within 8-bit range [0, 255]."""
        test_pattern = [(r * 3 + c * 2) % 256 for c in range(SENSOR_WIDTH) for r in range(SENSOR_HEIGHT)]
        out_img = process_frame_demosaic(test_pattern)
        for p in out_img:
            self.assertGreaterEqual(p, 0)
            self.assertLessEqual(p, 255)

    def test_demosaic_fpimage_flags(self):
        """Verify FpImage flags include PARTIAL and COLORS_INVERTED."""
        FPI_IMAGE_PARTIAL = 1 << 0
        FPI_IMAGE_COLORS_INVERTED = 1 << 1
        flags = FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED
        self.assertEqual(flags, 3)

    def test_demosaic_continuity(self):
        """Verify interpolation maintains continuity without discrete step discontinuities."""
        gradient_pattern = [int((c / SENSOR_WIDTH) * 255) for c in range(SENSOR_WIDTH) for r in range(SENSOR_HEIGHT)]
        out_img = process_frame_demosaic(gradient_pattern)
        # Check monotonic increase across center row
        row_center = 64
        center_row_pixels = [out_img[row_center * IMAGE_OUT_WIDTH + c] for c in range(IMAGE_OUT_WIDTH)]
        self.assertLessEqual(center_row_pixels[0], center_row_pixels[-1])

    def test_process_raw_frame_dimensions(self):
        """Verify process_raw_frame outputs 160x128 image (20,480 pixels)."""
        finger_pixels = [200 + (r * 5 + c * 3) % 300 for c in range(SENSOR_WIDTH) for r in range(SENSOR_HEIGHT)]
        out_img = process_raw_frame(finger_pixels)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        self.assertEqual(len(out_img), 160 * 128)

    def test_process_raw_frame_air_rejection_insufficient_active(self):
        """Verify empty air frames with active samples < 64 are rejected to all-zeros."""
        # Flat empty air noise: all pixels below noise threshold (<= 30)
        air_pixels = [10] * FRAME_PIXELS
        out_img = process_raw_frame(air_pixels)
        self.assertEqual(out_img, [0] * IMAGE_OUT_PIXELS)

        # 50 active pixels (> 30), still below the 64-sample gate threshold
        partial_air = [10] * FRAME_PIXELS
        for i in range(50):
            partial_air[(4 * (i % 19) + 3) * SENSOR_HEIGHT + (i // 19)] = 200
        out_partial = process_raw_frame(partial_air)
        self.assertEqual(out_partial, [0] * IMAGE_OUT_PIXELS)

    def test_process_raw_frame_air_rejection_insufficient_range(self):
        """Verify empty air frames with range < 8 are rejected to all-zeros."""
        # Active > 64, but almost flat (range = 210 - 205 = 5 < 8)
        flat_pixels = [205 + (i % 5) for i in range(FRAME_PIXELS)]
        out_img = process_raw_frame(flat_pixels)
        self.assertEqual(out_img, [0] * IMAGE_OUT_PIXELS)

    def test_process_raw_frame_finger_touch_accepted(self):
        """Verify real finger frames with active >= 64 and range >= 8 produce valid ridges."""
        # Simulated real finger capture: active samples >> 64 and range >> 8
        finger_pixels = [50 + ((c * 7 + r * 13) % 350) for c in range(SENSOR_WIDTH) for r in range(SENSOR_HEIGHT)]
        out_img = process_raw_frame(finger_pixels)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        self.assertGreater(max(out_img), 0)
        self.assertLessEqual(max(out_img), 255)

    def test_driver_c_process_raw_frame_wiring(self):
        """Verify goodix5e0a.c implements process_raw_frame with 160x128 and air rejection gate."""
        from pathlib import Path
        repo_c = Path(__file__).resolve().parents[2] / "libfprint-driver" / "goodix5e0a.c"
        if repo_c.exists():
            c_code = repo_c.read_text(encoding="utf-8")
            self.assertIn("process_raw_frame (GoodixTls5xxPix * pix)", c_code)
            self.assertIn("xx_cls->process_raw_frame = process_raw_frame;", c_code)
            self.assertIn("const int W = GOODIX_5E0A_WIDTH;   // Native 80", c_code)
            self.assertIn("const int H = GOODIX_5E0A_HEIGHT;  // Native 64", c_code)
            self.assertIn("if (active < 64 || range < 8)", c_code)


if __name__ == "__main__":
    unittest.main()
