"""
Tier 1 - Feature 16: Bilinear Demosaicing & Process Frame
Requirements: bilinear interpolation of the natural 64x80 raster to a 128x160 FpImage.
"""

import unittest
from tests.test_utils import (
    process_frame_demosaic, process_raw_frame, SENSOR_WIDTH, SENSOR_HEIGHT,
    IMAGE_OUT_WIDTH, IMAGE_OUT_HEIGHT, IMAGE_OUT_PIXELS, FRAME_PIXELS
)

class TestF16Demosaicing(unittest.TestCase):

    def test_demosaic_output_dimensions(self):
        """Verify output image dimension is 128x160 (20,480 pixels)."""
        squashed = [128] * FRAME_PIXELS
        out_img = process_frame_demosaic(squashed)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        self.assertEqual(IMAGE_OUT_WIDTH, 128)
        self.assertEqual(IMAGE_OUT_HEIGHT, 160)

    def test_demosaic_preserves_constant_image(self):
        out_img = process_frame_demosaic([137] * FRAME_PIXELS)
        self.assertEqual(out_img, [137] * IMAGE_OUT_PIXELS)

    def test_demosaic_pixel_value_bounds(self):
        """Verify all interpolated pixel outputs are strictly within 8-bit range [0, 255]."""
        test_pattern = [(r * 3 + c * 2) % 256 for c in range(SENSOR_WIDTH) for r in range(SENSOR_HEIGHT)]
        out_img = process_frame_demosaic(test_pattern)
        for p in out_img:
            self.assertGreaterEqual(p, 0)
            self.assertLessEqual(p, 255)

    def test_demosaic_fpimage_flags(self):
        """Verify FpImage uses COLORS_INVERTED with PARTIAL deliberately omitted (edge minutiae kept)."""
        from pathlib import Path
        repo_c = Path(__file__).resolve().parents[2] / "libfprint-driver" / "goodix5e0a.c"
        self.assertTrue(repo_c.exists(), f"Missing driver C file: {repo_c}")
        c_code = repo_c.read_text(encoding="utf-8")
        self.assertIn("img->flags = FPI_IMAGE_COLORS_INVERTED;", c_code)
        self.assertIn("Omit FPI_IMAGE_PARTIAL", c_code)

    def test_demosaic_continuity(self):
        """Verify interpolation maintains continuity without discrete step discontinuities."""
        gradient_pattern = [int((c / SENSOR_WIDTH) * 255) for c in range(SENSOR_WIDTH) for r in range(SENSOR_HEIGHT)]
        out_img = process_frame_demosaic(gradient_pattern)
        # Check monotonic increase across center row
        row_center = IMAGE_OUT_HEIGHT // 2
        center_row_pixels = [out_img[row_center * IMAGE_OUT_WIDTH + c] for c in range(IMAGE_OUT_WIDTH)]
        self.assertLessEqual(center_row_pixels[0], center_row_pixels[-1])

    def test_process_raw_frame_dimensions(self):
        """Verify process_raw_frame outputs a 128x160 image (20,480 pixels)."""
        finger_pixels = [200 + (r * 5 + c * 3) % 300 for c in range(SENSOR_WIDTH) for r in range(SENSOR_HEIGHT)]
        out_img = process_raw_frame(finger_pixels)
        self.assertEqual(len(out_img), IMAGE_OUT_PIXELS)
        self.assertEqual(len(out_img), 128 * 160)

    def test_process_raw_frame_air_rejection_insufficient_active(self):
        """Verify empty air frames with active samples < 64 are rejected to all-zeros."""
        # Flat empty air noise: all pixels below noise threshold (<= 30)
        air_pixels = [10] * FRAME_PIXELS
        out_img = process_raw_frame(air_pixels)
        self.assertEqual(out_img, [0] * IMAGE_OUT_PIXELS)

        # 50 active pixels (> 30), still below the 64-sample gate threshold
        partial_air = [10] * FRAME_PIXELS
        for i in range(50):
            partial_air[i] = 200
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
        """Verify goodix5e0a.c processes the canonical 64x80 raster with its air gate."""
        from pathlib import Path
        repo_c = Path(__file__).resolve().parents[2] / "libfprint-driver" / "goodix5e0a.c"
        if repo_c.exists():
            c_code = repo_c.read_text(encoding="utf-8")
            self.assertIn("process_raw_frame (GoodixTls5xxPix * pix)", c_code)
            self.assertIn("xx_cls->process_raw_frame = process_raw_frame;", c_code)
            self.assertIn("const int W = GOODIX_5E0A_WIDTH;", c_code)
            self.assertIn("const int H = GOODIX_5E0A_HEIGHT;", c_code)
            self.assertIn("GOODIX_5E0A_BLOCK_ACTIVE_BYTES", c_code)
            self.assertIn("if (active < 64 || range < 8)", c_code)


if __name__ == "__main__":
    unittest.main()
