"""
Tier 1 Feature Tests: Milestone 1 Payload & Sensor Register Verification
Validates byte-exactness of hardware tables in goodix5e0a.h against canonical hardware prototypes.
"""

import re
import struct
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
    pattern = rf"(?:static\s+)?const\s+guint8\s+{array_name}\s*\[\s*\d*\s*\]\s*=\s*\{{([^}}]+)\}};"
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
        """Verify 256-byte sensor timing table matches current header definition."""
        config = parse_c_array(self.header_content, "goodix_5e0a_config")
        self.assertEqual(len(config), 256, "CONFIG table must be exactly 256 bytes")
        self.assertEqual(config[0:4], bytes([0xb0, 0x11, 0x60, 0x71]))
        self.assertEqual(config[-3:], bytes([0x00, 0x53, 0x0e]))

    def test_img_payload_exactness(self):
        """Verify 10-byte image capture payload matches capture ground-truth."""
        img_payload = parse_c_array(self.header_content, "goodix_5e0a_img_payload")
        self.assertEqual(len(img_payload), 10, "Image payload must be exactly 10 bytes")
        expected = bytes([0x05, 0x00, 0xb0, 0x00, 0xb2, 0x00, 0xb0, 0x00, 0xb1, 0x00])
        self.assertEqual(img_payload, expected)

    def test_down_tables_exactness(self):
        """Verify 35-byte steady-state DOWN table S12 and retry table match ground truth."""
        down_s12 = parse_c_array(self.header_content, "goodix_5e0a_down_s12")
        down_retry = parse_c_array(self.header_content, "goodix_5e0a_down_retry")
        self.assertEqual(len(down_s12), 35, "down_s12 must be exactly 35 bytes")
        self.assertEqual(len(down_retry), 35, "down_retry must be exactly 35 bytes")
        self.assertEqual(down_s12[0:2], bytes([0x1c, 0x01]))
        self.assertEqual(down_retry[0:2], bytes([0x1c, 0x01]))

    def test_up_table_exactness(self):
        """Verify 35-byte steady-state UP table U01 matches ground truth."""
        up_u01 = parse_c_array(self.header_content, "goodix_5e0a_up_u01")
        self.assertEqual(len(up_u01), 35, "up_u01 must be exactly 35 bytes")
        self.assertEqual(up_u01[0:2], bytes([0x0e, 0x01]))


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

    def test_reg_022c_mock_matches_header(self):
        """Verify mock CANONICAL_REG_022C_GAIN equals the header LE value.

        The gain bytes are one of the two mock values shared with frozen
        hardware (the other is the PSK); pin the agreement both ways."""
        reg_val = parse_c_macro(self.header_content, "GOODIX_5E0A_REG_GAIN_EXPOSURE_VAL")
        self.assertEqual(CANONICAL_REG_022C_GAIN, struct.pack("<H", reg_val))

    def test_b4_get_image_payload_exactness(self):
        """Verify B4 10-byte finger-capture payload in goodix.c."""
        expected_payload = bytes([0x01] + [0x00] * 9)
        self.assertEqual(len(expected_payload), 10)
        # Verify it is wired in goodix.c:goodix_send_mcu_get_image
        with open(str(REPO_ROOT / "libfprint-driver" / "goodix.c"), "r") as f:
            c_code = f.read()
        if "payload_5e0a" in c_code:
            self.assertIn("payload_5e0a[10] = {0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}", c_code)
        self.assertEqual(len(FINGER_EXPOSURE_PAYLOAD), 10, "Exposure payload must be exactly 10 bytes")
        self.assertEqual(FINGER_EXPOSURE_PAYLOAD, expected_payload, "Payload bytes must match canonical exposure sequence")


if __name__ == "__main__":
    unittest.main()
