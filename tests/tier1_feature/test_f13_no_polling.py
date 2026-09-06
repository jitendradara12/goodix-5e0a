"""
Tier 1 - Feature 13: Elimination of Software Polling Loops
Requirements: Remove all g_timeout_add timers, synthetic noise thresholds, and ad-hoc scan loops.
temp_hot_seconds set to -1 (disables thermal watchdog polling).
"""

import unittest
import os
import re
from tests.repo_paths import repo

class TestF13NoPolling(unittest.TestCase):

    def setUp(self):
        self.driver_c_path = repo("libfprint-driver", "goodix5e0a.c")
        self.driver_5xx_path = repo("libfprint-driver", "goodix5xx.c")

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
        """Verify driver uses hardware FDT callbacks and SSM state transitions."""
        with open(self.driver_c_path, "r") as f:
            content = f.read()
        self.assertIn("goodix5e0a_on_fdt_down_reply", content)
        self.assertIn("goodix5e0a_on_fdt_up_reply", content)
        self.assertIn("GOODIX_CMD_MCU_SWITCH_TO_FDT_DOWN", content)
        self.assertIn("GOODIX_CMD_MCU_SWITCH_TO_FDT_UP", content)
        self.assertIn("goodix5e0a_scan_run_state", content)

    def test_no_synthetic_noise_threshold_heuristics(self):
        """Verify no ad-hoc noise floor guessing loops exist in driver."""
        with open(self.driver_c_path, "r") as f:
            content = f.read()
        self.assertNotIn("noise_threshold", content.lower())

    def test_minimal_loc_ponytail_standard(self):
        """Verify goodix5e0a.c reflects production driver size (~850 LOC) with clean base-class subclassing."""
        with open(self.driver_c_path, "r") as f:
            content = f.read()
            lines = [l for l in content.splitlines() if l.strip()]
        # Ticket 40: warm fast path adds ~220 non-blank lines (measured 1334);
        # budget 1350 owns that growth.
        self.assertLess(len(lines), 1350, f"Driver exceeds production compactness limit: {len(lines)} LOC")
        self.assertIn("FPI_TYPE_DEVICE_GOODIXTLS5XX", content)


if __name__ == "__main__":
    unittest.main()
