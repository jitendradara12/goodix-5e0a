"""
Tier 2 Boundary Tests: Milestone 1 Payload & Protocol Boundary Conditions
Stress-tests payload length mismatches, truncated wire buffers, maximum integer bounds,
and buffer encapsulation limits for Goodix 27c6:5e0a.
"""

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
    CMD_MCU_SWITCH_TO_FDT_DOWN,
    CMD_MCU_SWITCH_TO_FDT_UP,
    CMD_MCU_SWITCH_TO_FDT_MODE,
    CMD_WRITE_SENSOR_REGISTER,
    FLAGS_MSG_PROTOCOL,
    EP_OUT_CHUNK_SIZE,
    encode_protocol,
    decode_protocol,
    encode_pack,
    decode_pack,
    calc_protocol_checksum,
    calc_pack_checksum,
)
from tests.tier1_feature.test_m1_payloads import parse_c_array, parse_c_macro

HEADER_PATH = Path("/tmp/libfprint-goodix/libfprint/drivers/goodixtls/goodix5e0a.h")


class TestM1BoundaryConditions(unittest.TestCase):
    """Stress tests boundary conditions for Milestone 1 payloads and wire protocols."""

    @classmethod
    def setUpClass(cls):
        cls.header_content = HEADER_PATH.read_text(encoding="utf-8")
        cls.down_s12 = parse_c_array(cls.header_content, "goodix_5e0a_down_s12")
        cls.up_u01 = parse_c_array(cls.header_content, "goodix_5e0a_up_u01")
        cls.img_payload = parse_c_array(cls.header_content, "goodix_5e0a_img_payload")
        cls.config_table = parse_c_array(cls.header_content, "goodix_5e0a_config")
        cls.psk = parse_c_array(cls.header_content, "goodix_5e0a_psk")

    def test_down_s12_truncation_boundaries(self):
        """Test decoding behavior on all prefix truncations of DOWN S12 packets."""
        encoded = encode_protocol(CMD_MCU_SWITCH_TO_FDT_DOWN, self.down_s12, calc_checksum=True, pad_data=False)
        total_len = len(encoded)

        for trunc_len in range(0, total_len):
            truncated = encoded[:trunc_len]
            ok, cmd, payload, valid_chk, valid_null = decode_protocol(truncated)
            self.assertFalse(ok, f"Truncated packet of length {trunc_len}/{total_len} must fail decoding")

    def test_up_u01_truncation_boundaries(self):
        """Test decoding behavior on all prefix truncations of UP U01 packets."""
        encoded = encode_protocol(CMD_MCU_SWITCH_TO_FDT_UP, self.up_u01, calc_checksum=True, pad_data=False)
        total_len = len(encoded)

        for trunc_len in range(0, total_len):
            truncated = encoded[:trunc_len]
            ok, cmd, payload, valid_chk, valid_null = decode_protocol(truncated)
            self.assertFalse(ok, f"Truncated packet of length {trunc_len}/{total_len} must fail decoding")

    def test_img_payload_truncation_boundaries(self):
        """Test decoding behavior on all prefix truncations of image capture payload packets."""
        encoded = encode_protocol(0x20, self.img_payload, calc_checksum=True, pad_data=False)
        total_len = len(encoded)

        for trunc_len in range(0, total_len):
            truncated = encoded[:trunc_len]
            ok, cmd, payload, valid_chk, valid_null = decode_protocol(truncated)
            self.assertFalse(ok, f"Truncated packet of length {trunc_len}/{total_len} must fail decoding")


    def test_zero_length_payload_boundaries(self):
        """Test wire encoding and decoding with empty/0-length payload."""
        empty_payload = b""
        encoded = encode_protocol(CMD_MCU_SWITCH_TO_FDT_MODE, empty_payload, calc_checksum=True, pad_data=False)
        self.assertEqual(len(encoded), 4)  # 1B cmd + 2B length (1) + 1B chk
        ok, cmd, payload, valid_chk, valid_null = decode_protocol(encoded)
        self.assertTrue(ok)
        self.assertEqual(cmd, CMD_MCU_SWITCH_TO_FDT_MODE)
        self.assertEqual(payload, b"")
        self.assertTrue(valid_chk)

    def test_single_byte_payload_boundary(self):
        """Test wire encoding and decoding with 1-byte payload."""
        payload_1b = b"\x42"
        encoded = encode_protocol(0x70, payload_1b, calc_checksum=True, pad_data=False)
        self.assertEqual(len(encoded), 5)
        ok, cmd, payload, valid_chk, valid_null = decode_protocol(encoded)
        self.assertTrue(ok)
        self.assertEqual(payload, payload_1b)
        self.assertTrue(valid_chk)

    def test_max_uint16_length_overflow_guard(self):
        """Test protocol decoder robustness when length header specifies 0xFFFF (65535)."""
        malicious_hdr = struct.pack("<BH", CMD_MCU_SWITCH_TO_FDT_DOWN, 0xFFFF)
        malicious_packet = malicious_hdr + self.down_s12
        ok, cmd, payload, valid_chk, valid_null = decode_protocol(malicious_packet)
        self.assertFalse(ok, "Decoder must reject buffer when wire length exceeds actual received byte count")

    def test_zero_wire_length_underflow_guard(self):
        """Test protocol decoder robustness when length header specifies 0."""
        malicious_hdr = struct.pack("<BH", CMD_MCU_SWITCH_TO_FDT_DOWN, 0x0000)
        malicious_packet = malicious_hdr + b"\x00" * 10
        ok, cmd, payload, valid_chk, valid_null = decode_protocol(malicious_packet)
        self.assertFalse(ok, "Decoder must reject buffer when wire length is 0")

    def test_pack_padding_64b_boundary(self):
        """Verify 64-byte USB EP OUT boundary chunking for all M1 payloads."""
        for name, payload in [
            ("DOWN_S12", self.down_s12),
            ("UP_U01", self.up_u01),
            ("IMG_PAYLOAD", self.img_payload),
            ("CONFIG_TABLE", self.config_table),
            ("PSK", self.psk),
        ]:
            proto = encode_protocol(0x32, payload, calc_checksum=True, pad_data=False)
            pack = encode_pack(FLAGS_MSG_PROTOCOL, proto, pad_data=True)
            self.assertEqual(
                len(pack) % EP_OUT_CHUNK_SIZE, 0,
                f"Pack for {name} (len {len(pack)}) must be an exact multiple of {EP_OUT_CHUNK_SIZE} bytes"
            )


    def test_register_0x022c_boundary_values(self):
        """Verify register 0x022c gain/exposure bounds and value mappings."""
        reg_addr = parse_c_macro(self.header_content, "GOODIX_5E0A_REG_GAIN_EXPOSURE")
        val_default = parse_c_macro(self.header_content, "GOODIX_5E0A_REG_GAIN_EXPOSURE_VAL")
        val_calib = parse_c_macro(self.header_content, "GOODIX_5E0A_REG_GAIN_EXPOSURE_CALIB_VAL")
        val_reset = parse_c_macro(self.header_content, "GOODIX_5E0A_REG_GAIN_EXPOSURE_RESET_VAL")

        self.assertEqual(reg_addr, 0x022c)
        self.assertEqual(val_default, 0x0305)  # \x05\x03
        self.assertEqual(val_calib, 0x030a)    # \x0a\x03
        self.assertEqual(val_reset, 0x020a)    # \x0a\x02

        # Verify packed struct representation on wire
        wire_default = struct.pack("<BH", 0, reg_addr) + struct.pack("<H", val_default)
        self.assertEqual(wire_default, bytes([0x00, 0x2c, 0x02, 0x05, 0x03]))


if __name__ == "__main__":
    unittest.main()
