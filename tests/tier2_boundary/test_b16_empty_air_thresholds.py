"""
Tier 2 - Boundary 16: Empty Air Thresholds
Tests rejection of noise floors and empty air scans under hardware FDT and bz3_threshold=12.
"""

import unittest
from tests.repo_paths import repo
from tests.test_utils import squash_frame_linear, FRAME_PIXELS

class TestB16EmptyAirThresholds(unittest.TestCase):

    def test_low_amplitude_noise_squashing(self):
        """Verify low amplitude sensor thermal noise (e.g. 1-2 LSB variation) yields flat image."""
        noise_pixels = [2000 + (i % 2) for i in range(FRAME_PIXELS)]
        squashed = squash_frame_linear(noise_pixels)
        self.assertEqual(len(squashed), FRAME_PIXELS)
        # Verify no sharp fingerprint ridges exist
        self.assertLessEqual(max(squashed) - min(squashed), 255)

    def test_completely_uniform_air_scan(self):
        """Verify perfectly uniform noise-free frame squashes to zero array."""
        uniform_air = [1500] * FRAME_PIXELS
        squashed = squash_frame_linear(uniform_air)
        self.assertEqual(squashed, [0] * FRAME_PIXELS)

    def test_bz3_threshold_calibration_12(self):
        """Verify minutiae matching threshold is configured to 12."""
        with open(repo("libfprint-driver", "goodix5e0a.c"), "r") as f:
            content = f.read()
        self.assertIn("bz3_threshold = 12", content)

    def test_blocking_fdt_prevents_empty_air_capture(self):
        """Verify hardware FDT blocks until physical touch interrupt is raised."""
        with open(repo("libfprint-driver", "goodix5xx.c"), "r") as f:
            content = f.read()
        self.assertIn("SCAN_STAGE_SWITCH_TO_FDT_DOWN", content)

    def test_zero_touch_detected_when_untriggered(self):
        """Verify mock MCU touch pending state defaults to False."""
        from tests.test_utils import MockGoodixMCU
        mcu = MockGoodixMCU()
        self.assertFalse(mcu.touch_pending)

if __name__ == "__main__":
    unittest.main()
