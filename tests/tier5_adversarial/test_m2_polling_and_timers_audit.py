"""
Tier 5 Adversarial Stress Test: Polling Loops & Timers Elimination Audit
Audits goodix5e0a.c and goodix5e0a.h for any remaining polling loops, timers,
sleep statements, or synthetic noise heuristics.
"""

import unittest
import re
from tests.repo_paths import repo

class TestM2PollingAndTimersAudit(unittest.TestCase):

    def setUp(self):
        self.driver_c_path = repo("libfprint-driver", "goodix5e0a.c")
        self.driver_h_path = repo("libfprint-driver", "goodix5e0a.h")

        with open(self.driver_c_path, "r") as f:
            self.c_code = f.read()
        with open(self.driver_h_path, "r") as f:
            self.h_code = f.read()

    def test_no_glib_timeout_functions(self):
        """Verify zero GLib timer or timeout functions are invoked in goodix5e0a.c."""
        banned_glib_symbols = [
            "g_timeout_add",
            "g_timeout_add_seconds",
            "g_timeout_add_full",
            "g_timeout_source_new",
            "g_source_attach",
            "g_idle_add",
        ]
        for sym in banned_glib_symbols:
            self.assertNotIn(sym, self.c_code, f"Banned timer symbol '{sym}' found in driver!")
            self.assertNotIn(sym, self.h_code, f"Banned timer symbol '{sym}' found in header!")

    def test_no_blocking_sleep_calls(self):
        """Verify zero sleep/delay functions are invoked."""
        banned_sleep_symbols = [
            "usleep",
            "nanosleep",
            "g_usleep",
            "sleep(",
            "poll(",
            "select(",
        ]
        for sym in banned_sleep_symbols:
            self.assertNotIn(sym, self.c_code, f"Banned sleep symbol '{sym}' found in driver!")
            self.assertNotIn(sym, self.h_code, f"Banned sleep symbol '{sym}' found in header!")

    def test_thermal_watchdog_explicitly_disabled(self):
        """Verify dev_class->temp_hot_seconds is set to -1 to disable internal thermal polling."""
        self.assertIn("dev_class->temp_hot_seconds = -1;", self.c_code)

    def test_no_synthetic_software_noise_thresholds(self):
        """Verify no ad-hoc noise/pixel sum heuristics exist in goodix5e0a.c."""
        banned_noise_heuristics = [
            "noise_threshold",
            "noise_sum",
            "pixel_sum",
            "is_noise",
            "noise_level",
        ]
        for term in banned_noise_heuristics:
            self.assertNotIn(term.lower(), self.c_code.lower(), f"Suspicious noise heuristic '{term}' found!")

    def test_event_driven_activation_ssm(self):
        """Verify activation SSM transitions are strictly callback-driven with no timers."""
        # 5 states in SSM:
        # ACTIVATE_READ_AND_NOP -> goodix_send_nop -> goodixtls5xx_check_none
        # ACTIVATE_RESET -> goodix_send_reset -> goodixtls5xx_check_reset
        # ACTIVATE_READ_CHIP_ID -> goodix_send_read_sensor_register -> goodixtls5xx_check_none_cmd
        # ACTIVATE_READ_OTP -> goodix_send_read_otp -> goodixtls5xx_check_none_cmd
        # ACTIVATE_CHECK_FW_VER -> goodix_send_query_firmware_version -> goodixtls5xx_check_firmware_version
        self.assertIn("goodix_send_nop (dev, goodixtls5xx_check_none, ssm);", self.c_code)
        self.assertIn("goodix_send_reset (dev, TRUE, 20, goodixtls5xx_check_reset, ssm);", self.c_code)
        self.assertIn("goodix_send_read_sensor_register (dev, 0x0000, 4, goodixtls5xx_check_none_cmd, ssm);", self.c_code)
        self.assertIn("goodix_send_read_otp (dev, goodixtls5xx_check_none_cmd, ssm);", self.c_code)
        self.assertIn("goodix_send_query_firmware_version (dev, goodixtls5xx_check_firmware_version, ssm);", self.c_code)

if __name__ == "__main__":
    unittest.main()
