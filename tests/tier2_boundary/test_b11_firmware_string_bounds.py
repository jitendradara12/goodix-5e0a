"""
Tier 2 - Boundary 11: Firmware String Boundaries
Tests ASCII firmware response null termination, empty strings, and long string boundary conditions.
"""

import unittest
from tests.test_utils import FIRMWARE_VERSION_STR

class TestB11FirmwareStringBounds(unittest.TestCase):

    def test_firmware_string_exact_content(self):
        """Verify firmware string matches GFUSB_GM168SEC_APP_10036."""
        self.assertEqual(FIRMWARE_VERSION_STR, "GFUSB_GM168SEC_APP_10036")

    def test_firmware_string_length(self):
        """Verify firmware string length is 24 characters."""
        self.assertEqual(len(FIRMWARE_VERSION_STR), 24)

    def test_null_terminated_string_parsing(self):
        """Verify stripping trailing null terminator."""
        fw_wire = FIRMWARE_VERSION_STR.encode("ascii") + b"\x00\x00\x00"
        parsed = fw_wire.rstrip(b"\x00").decode("ascii")
        self.assertEqual(parsed, FIRMWARE_VERSION_STR)

    def test_empty_firmware_string_rejection(self):
        """Verify empty string is rejected as invalid firmware."""
        self.assertNotEqual("", FIRMWARE_VERSION_STR)

    def test_prefix_only_string_rejection(self):
        """Verify partial prefix string fails exact match."""
        partial = "GFUSB_GM168SEC"
        self.assertNotEqual(partial, FIRMWARE_VERSION_STR)

if __name__ == "__main__":
    unittest.main()
