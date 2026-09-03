"""
Tier 1 - Feature 13: Elimination of Software Polling Loops
Requirements: Remove all g_timeout_add timers, synthetic noise thresholds, and ad-hoc scan loops.
temp_hot_seconds set to -1 (disables thermal watchdog polling).
"""

import unittest
import os
import re

class TestF13NoPolling(unittest.TestCase):

    def setUp(self):
        self.driver_c_path = "/home/sastauser/code/temp/goodix/libfprint-driver/goodix5e0a.c"
        self.driver_5xx_path = "/home/sastauser/code/temp/goodix/libfprint-driver/goodix5xx.c"

    def test_temp_hot_seconds_disabled(self):
        """Verify dev_class->temp_hot_seconds is explicitly set to -1 in goodix5e0a.c."""
        with open(self.driver_c_path, "r") as f:
            content = f.read()
        self.assertIn("temp_hot_seconds = -1", content)

    def test_no_g_timeout_add_in_driver(self):
        """Verify goodix5e0a.c contains zero g_timeout_add or polling loops."""
        with open(self.driver_c_path, "r") as f:
            content = f.read()
        self.assertNotIn("g_timeout_add", content)
        self.assertNotIn("usleep", content)

    def test_blocking_fdt_interrupt_driven_architecture(self):
        """Verify driver uses hardware FDT callbacks rather than software periodic polling."""
        with open(self.driver_c_path, "r") as f:
            content = f.read()
        self.assertIn("get_fdt_down_cfg", content)
        self.assertIn("get_fdt_up_cfg", content)

    def test_no_synthetic_noise_threshold_heuristics(self):
        """Verify no ad-hoc noise floor guessing loops exist in driver."""
        with open(self.driver_c_path, "r") as f:
            content = f.read()
        self.assertNotIn("noise_threshold", content.lower())

    def test_minimal_loc_ponytail_standard(self):
        """Verify goodix5e0a.c is concise (~290 lines) without duplicated state machines."""
        with open(self.driver_c_path, "r") as f:
            lines = [l for l in f if l.strip()]
        self.assertLess(len(lines), 350, f"Driver exceeds Ponytail compactness goal: {len(lines)} LOC")

if __name__ == "__main__":
    unittest.main()
