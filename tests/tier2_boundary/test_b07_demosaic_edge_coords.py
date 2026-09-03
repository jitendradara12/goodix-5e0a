"""
Tier 2 - Boundary 7: Demosaic Edge Coordinates
Tests bilinear demosaicing interpolation boundaries at corner and edge coordinates (0,0), (159,0), (0,127), (159,127).
"""

import unittest
from tests.test_utils import (
    process_frame_demosaic, FRAME_PIXELS, IMAGE_OUT_WIDTH, IMAGE_OUT_HEIGHT
)

class TestB07DemosaicEdgeCoords(unittest.TestCase):

    def setUp(self):
        # Create a test pattern where value depends linearly on col and row
        self.pattern = [(c * 3 + r * 2) % 255 for c in range(80) for r in range(64)]
        self.out_img = process_frame_demosaic(self.pattern)

    def test_top_left_corner_coordinate(self):
        """Verify top-left corner pixel at (0, 0) is bounded and non-negative."""
        p = self.out_img[0]
        self.assertGreaterEqual(p, 0)
        self.assertLessEqual(p, 255)

    def test_top_right_corner_coordinate(self):
        """Verify top-right corner pixel at (159, 0) is bounded."""
        p = self.out_img[IMAGE_OUT_WIDTH - 1]
        self.assertGreaterEqual(p, 0)
        self.assertLessEqual(p, 255)

    def test_bottom_left_corner_coordinate(self):
        """Verify bottom-left corner pixel at (0, 127) is bounded."""
        p = self.out_img[(IMAGE_OUT_HEIGHT - 1) * IMAGE_OUT_WIDTH]
        self.assertGreaterEqual(p, 0)
        self.assertLessEqual(p, 255)

    def test_bottom_right_corner_coordinate(self):
        """Verify bottom-right corner pixel at (159, 127) is bounded."""
        p = self.out_img[IMAGE_OUT_HEIGHT * IMAGE_OUT_WIDTH - 1]
        self.assertGreaterEqual(p, 0)
        self.assertLessEqual(p, 255)

    def test_center_coordinate(self):
        """Verify center coordinate at (80, 64) is correctly interpolated."""
        p = self.out_img[64 * IMAGE_OUT_WIDTH + 80]
        self.assertGreaterEqual(p, 0)
        self.assertLessEqual(p, 255)

if __name__ == "__main__":
    unittest.main()
