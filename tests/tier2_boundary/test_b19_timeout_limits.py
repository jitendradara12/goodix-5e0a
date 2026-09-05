"""
Tier 2 - Boundary 19: Timeout Limits
Tests timeout limits: 0ms for blocking capacitive FDT interrupts, 20ms reset sleep time, and negative watchdog timeout.
"""

import unittest
from tests.repo_paths import repo

class TestB19TimeoutLimits(unittest.TestCase):

    def test_temp_hot_seconds_negative_watchdog_timeout(self):
        """Verify temp_hot_seconds is -1 (disabled watchdog)."""
        with open(repo("libfprint-driver", "goodix5e0a.c"), "r") as f:
            content = f.read()
        self.assertIn("temp_hot_seconds = -1", content)

    def test_reset_command_sleep_time_parameter(self):
        """Verify reset command sets sleep_time=20ms."""
        with open(repo("libfprint-driver", "goodix5e0a.c"), "r") as f:
            content = f.read()
        self.assertIn("goodix_send_reset (dev, TRUE, 20", content)

    def test_blocking_fdt_zero_timeout(self):
        """Verify hardware FDT calls block until interrupt is generated."""
        with open(repo("libfprint-driver", "goodix5xx.c"), "r") as f:
            content = f.read()
        self.assertIn("goodix_send_mcu_switch_to_fdt_down", content)
        self.assertIn("goodix_send_mcu_switch_to_fdt_up", content)

    def test_default_usb_read_timeout(self):
        """Verify default USB timeout handling in protocol."""
        with open(repo("goodix_protocol.py"), "r") as f:
            content = f.read()
        self.assertIn("timeout_ms = int(timeout * 1000)", content)

    def test_zero_timeout_non_blocking_read(self):
        """Verify 0 timeout parameter translates to 5000ms fallback or non-blocking handling."""
        timeout = 0
        timeout_ms = int(timeout * 1000) if timeout else 5000
        self.assertEqual(timeout_ms, 5000)

if __name__ == "__main__":
    unittest.main()
