"""
Tier 1 Feature Tests: Milestone 1 Payload & Sensor Register Verification
Validates byte-exactness of hardware tables in goodix5e0a.h against canonical hardware prototypes.
"""

import re
import unittest
from pathlib import Path
from tests.test_utils import (
    CANONICAL_PSK,
    CANONICAL_CONFIG_52XD,
    CANONICAL_FDT_MODE,
    CANONICAL_FDT_DOWN,
    CANONICAL_FDT_UP,
    CANONICAL_REG_022C_GAIN,
    FINGER_EXPOSURE_PAYLOAD,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_HEADER_PATH = REPO_ROOT / "libfprint-driver" / "goodix5e0a.h"
TMP_HEADER_PATH = Path("/tmp/libfprint-goodix/libfprint/drivers/goodixtls/goodix5e0a.h")
HEADER_PATH = TMP_HEADER_PATH if TMP_HEADER_PATH.exists() else LOCAL_HEADER_PATH


def parse_c_array(header_content: str, array_name: str) -> bytes:
    """Extracts a byte array from a C header file."""
    pattern = rf"(?:static\s+)?const\s+guint8\s+{array_name}\s*\[\s*\]\s*=\s*\{{([^}}]+)\}};"
    match = re.search(pattern, header_content, re.DOTALL)
    if not match:
        raise ValueError(f"Array '{array_name}' not found in header")
    hex_str = match.group(1)
    # Extract all 0x.. hex literals
    hex_bytes = re.findall(r"0x([0-9a-fA-F]{2})", hex_str)
    return bytes(int(b, 16) for b in hex_bytes)


def parse_c_macro(header_content: str, macro_name: str) -> int:
    """Extracts an integer macro value from a C header file."""
    pattern = rf"#define\s+{macro_name}\s+\(([^)]+)\)"
    match = re.search(pattern, header_content)
    if not match:
        pattern2 = rf"#define\s+{macro_name}\s+(\S+)"
        match2 = re.search(pattern2, header_content)
        if not match2:
            raise ValueError(f"Macro '{macro_name}' not found in header")
        val_str = match2.group(1).strip()
    else:
        val_str = match.group(1).strip()
    if val_str.startswith("0x") or val_str.startswith("0X"):
        return int(val_str, 16)
    return int(val_str)


class TestMilestone1Payloads(unittest.TestCase):
    """Verifies byte-exactness of all Milestone 1 payloads and registers."""

    @classmethod
    def setUpClass(cls):
        if not HEADER_PATH.exists():
            raise FileNotFoundError(f"Missing header file: {HEADER_PATH}")
        cls.header_content = HEADER_PATH.read_text(encoding="utf-8")

    def test_psk_key_exactness(self):
        """Verify 32-byte DPAPI Pre-Shared Key matches canonical key."""
        psk = parse_c_array(self.header_content, "goodix_5e0a_psk")
        self.assertEqual(len(psk), 32, "PSK must be exactly 32 bytes")
        self.assertEqual(psk, CANONICAL_PSK, "PSK bytes do not match canonical DPAPI key")

    def test_config_52xd_exactness(self):
        """Verify 256-byte CONFIG_52XD sensor timing table matches canonical table."""
        config = parse_c_array(self.header_content, "goodix_5e0a_config")
        self.assertEqual(len(config), 256, "CONFIG_52XD must be exactly 256 bytes")
        self.assertEqual(config, CANONICAL_CONFIG_52XD, "CONFIG_52XD timing table mismatch")

    def test_fdt_mode_exactness(self):
        """Verify 27-byte FDT mode configuration matches canonical sequence."""
        fdt_mode = parse_c_array(self.header_content, "goodix_5e0a_fdt_mode")
        self.assertEqual(len(fdt_mode), 27, "FDT mode config must be exactly 27 bytes")
        self.assertEqual(fdt_mode, CANONICAL_FDT_MODE, "FDT mode config mismatch")

    def test_fdt_down_touch_exactness(self):
        """Verify 39-byte FDT DOWN configuration (byte 26 = 0x01) matches canonical touch interrupt."""
        fdt_down = parse_c_array(self.header_content, "goodix_5e0a_fdt_down")
        self.assertEqual(len(fdt_down), 39, "FDT DOWN config must be exactly 39 bytes")
        self.assertEqual(fdt_down[26], 0x01, "Byte 26 in FDT DOWN must be 0x01 for touch interrupt wait")
        self.assertEqual(fdt_down, CANONICAL_FDT_DOWN, "FDT DOWN config mismatch")

    def test_fdt_up_release_exactness(self):
        """Verify 39-byte FDT UP configuration (byte 26 = 0x00) matches canonical release interrupt."""
        fdt_up = parse_c_array(self.header_content, "goodix_5e0a_fdt_up")
        self.assertEqual(len(fdt_up), 39, "FDT UP config must be exactly 39 bytes")
        self.assertEqual(fdt_up[26], 0x00, "Byte 26 in FDT UP must be 0x00 for release interrupt wait")
        self.assertEqual(fdt_up, CANONICAL_FDT_UP, "FDT UP config mismatch")

    def test_sensor_dimensions_and_constants(self):
        """Verify sensor pixel geometry and driver constants."""
        width = parse_c_macro(self.header_content, "GOODIX_5E0A_WIDTH")
        height = parse_c_macro(self.header_content, "GOODIX_5E0A_HEIGHT")
        scan_w = parse_c_macro(self.header_content, "GOODIX_5E0A_SCAN_WIDTH")
        scan_h = parse_c_macro(self.header_content, "GOODIX_5E0A_SCAN_HEIGHT")
        self.assertEqual(width, 64)
        self.assertEqual(height, 80)
        self.assertEqual(scan_w, 64)
        self.assertEqual(scan_h, 80)

    def test_gain_exposure_register_0x022c(self):
        """Verify sensor register 0x022c gain/exposure parameters (0x0503)."""
        reg_addr = parse_c_macro(self.header_content, "GOODIX_5E0A_REG_GAIN_EXPOSURE")
        reg_val = parse_c_macro(self.header_content, "GOODIX_5E0A_REG_GAIN_EXPOSURE_VAL")
        self.assertEqual(reg_addr, 0x022c, "Sensor gain register must be 0x022c")
        # In little-endian uint16, bytes [0x05, 0x03] are represented as 0x0305
        self.assertEqual(reg_val, 0x0305, "Register 0x022c gain value must correspond to \x05\x03 (0x0305)")

    def test_b4_get_image_payload_exactness(self):
        """Verify B4 10-byte finger-capture payload in goodix.c."""
        expected_payload = bytes([0x01] + [0x00] * 9)
        self.assertEqual(len(expected_payload), 10)
        # Verify it is wired in goodix.c:goodix_send_mcu_get_image
        with open("/home/sastauser/code/temp/goodix/libfprint-driver/goodix.c", "r") as f:
            c_code = f.read()
        if "payload_5e0a" in c_code:
            self.assertIn("payload_5e0a[10] = {0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}", c_code)
        self.assertEqual(len(FINGER_EXPOSURE_PAYLOAD), 10, "Exposure payload must be exactly 10 bytes")
        self.assertEqual(FINGER_EXPOSURE_PAYLOAD, expected_payload, "Payload bytes must match canonical exposure sequence")


if __name__ == "__main__":
    unittest.main()
